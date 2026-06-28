"""AI win-probability layer for candlestick pattern backtesting.

Phase 2 of the AI backtester.  A RandomForestClassifier is trained on
in-sample signals and used to estimate the probability that any given
pattern occurrence will be profitable — given the surrounding market context,
not just the shape of the candle.

One model is trained per ``(direction × hold_period)`` combination (6 models
total with default hold periods of 21/42/63 days).  Each model is evaluated
via 5-fold stratified cross-validation on the IS set, then applied to OOS
signals to produce honest forward-test accuracy and per-signal win
probabilities.

Public API::

    result = run_ai_analysis(df, ticker="AAPL")
    for s in result.pattern_stats:
        print(s.pattern, f"OOS acc {s.oos_accuracy:.0%}", f"CV {s.model_cv_accuracy:.0%}")
    for sp in result.signal_probs:
        print(sp.bar, sp.pattern, f"{sp.prob_win:.0%}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import Pipeline
    _SKLEARN_OK = True
except ImportError:  # pragma: no cover
    _SKLEARN_OK = False

from core.pattern_engine import PatternSignal, detect_all, ALL_PATTERN_NAMES
from core.backtest_engine import (
    BacktestResult,
    DEFAULT_HOLD_PERIODS,
    DEFAULT_MIN_SAMPLES,
    IS_RATIO,
    run_backtest,
)

# ── constants ──────────────────────────────────────────────────────────────────

_N_ESTIMATORS = 200
_N_FOLDS = 5
_RF_SEED = 42
_MIN_SAMPLES_LEAF = 5

_PAT_VOCAB: dict[str, int] = {n: i for i, n in enumerate(ALL_PATTERN_NAMES)}
_N_PATS = len(ALL_PATTERN_NAMES)

_NUM_FEAT_NAMES: list[str] = [
    "ret_5", "ret_10", "ret_20",
    "rsi_14",
    "vol_ratio",
    "dist_sma20", "dist_sma50",
    "atr_norm",
    "body_ratio", "uw_ratio", "lw_ratio",
    "range_ratio",
]
FEATURE_NAMES: list[str] = _NUM_FEAT_NAMES + [
    f"pat_{p.replace(' ', '_')}" for p in ALL_PATTERN_NAMES
]


# ── output types ───────────────────────────────────────────────────────────────

@dataclass
class PatternAIStats:
    """AI-augmented stats for one (pattern × direction × hold_period) group.

    Attributes:
        pattern:            Candlestick pattern name.
        direction:          ``"bull"`` or ``"bear"``.
        hold_days:          Hold duration in trading days.
        n_is:               In-sample signal count for this pattern.
        n_oos:              Out-of-sample signal count.
        oos_accuracy:       Fraction of OOS predictions correct (NaN if n_oos==0).
        oos_avg_prob_win:   Mean predicted win-probability for actual winning OOS trades.
        oos_avg_prob_loss:  Mean predicted win-probability for actual losing OOS trades.
                            A wide gap confirms the model is calibrated.
        model_cv_accuracy:  5-fold CV accuracy of the global (direction × hold_period)
                            model on all IS signals — same value shared by all patterns
                            in this group.
        model_cv_std:       Std-dev of the 5 CV fold scores.
        lift:               ``oos_accuracy / 0.5`` — how much better than a coin flip.
    """
    pattern: str
    direction: str
    hold_days: int
    n_is: int
    n_oos: int
    oos_accuracy: float
    oos_avg_prob_win: float
    oos_avg_prob_loss: float
    model_cv_accuracy: float
    model_cv_std: float

    @property
    def lift(self) -> float:
        return self.oos_accuracy / 0.50 if self.oos_accuracy == self.oos_accuracy else 1.0

    @property
    def is_valid(self) -> bool:
        return self.n_is >= DEFAULT_MIN_SAMPLES and self.n_oos >= 5


@dataclass
class SignalPrediction:
    """Model output for one detected signal occurrence.

    Only OOS signals carry reliable ``prob_win`` estimates; IS probabilities
    would be optimistically biased.
    """
    bar: int
    pattern: str
    direction: str
    hold_days: int
    prob_win: float
    in_sample: bool


@dataclass
class AIAnalysisResult:
    """Full output of :func:`run_ai_analysis`.

    Attributes:
        ticker:              Ticker symbol.
        backtest:            Underlying :class:`~core.backtest_engine.BacktestResult`.
        pattern_stats:       Per-pattern AI stats, sorted by OOS accuracy descending.
                             Only entries meeting minimum sample thresholds are included.
        signal_probs:        Win-probability predictions for every OOS signal
                             (all directions, all hold periods).
        feature_importances: Mapping ``feature_name → mean importance`` averaged
                             across all trained models.
        n_models_trained:    Number of (direction × hold_period) models trained.
    """
    ticker: str
    backtest: BacktestResult
    pattern_stats: list[PatternAIStats] = field(default_factory=list)
    signal_probs: list[SignalPrediction] = field(default_factory=list)
    feature_importances: dict[str, float] = field(default_factory=dict)
    n_models_trained: int = 0


# ── feature computation ────────────────────────────────────────────────────────

def _sma(c: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(c).rolling(n, min_periods=n).mean().to_numpy()


def _rsi_array(c: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder RSI — returns array aligned with c; first 'period' values are NaN."""
    n = len(c)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    gains = np.zeros(n)
    losses = np.zeros(n)
    delta = np.diff(c)
    gains[1:] = np.maximum(delta, 0.0)
    losses[1:] = np.maximum(-delta, 0.0)
    avg_g = gains[1:period + 1].mean()
    avg_l = losses[1:period + 1].mean()
    if avg_l > 1e-10:
        out[period] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    else:
        out[period] = 100.0
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        rs = avg_g / avg_l if avg_l > 1e-10 else 1e6
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _atr_array(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 20) -> np.ndarray:
    """Wilder ATR."""
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(
        h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])),
    )
    out = np.full(n, np.nan)
    if n < period:
        return out
    out[period - 1] = tr[:period].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def _build_feature_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Precompute all per-bar feature arrays for the entire DataFrame."""
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    c = df["Close"].to_numpy(dtype=float)
    vol = df.get("Volume", pd.Series(np.ones(len(df)))).to_numpy(dtype=float)
    n = len(c)

    # Candle shape
    rng = np.where((h - l) == 0, 1e-10, h - l)
    body = np.abs(c - o)
    btop = np.maximum(o, c)
    bbot = np.minimum(o, c)

    sma20 = _sma(c, 20)
    sma50 = _sma(c, 50)
    avg_rng10 = _sma(rng, 10)
    vol_sma20 = _sma(vol, 20)
    rsi = _rsi_array(c, 14)
    atr = _atr_array(h, l, c, 20)

    # Prior returns (vectorised)
    ret5 = np.full(n, np.nan)
    ret10 = np.full(n, np.nan)
    ret20 = np.full(n, np.nan)
    safe = lambda x: np.where(x > 0, x, 1e-10)
    ret5[5:] = (c[5:] - c[:-5]) / safe(c[:-5])
    ret10[10:] = (c[10:] - c[:-10]) / safe(c[:-10])
    ret20[20:] = (c[20:] - c[:-20]) / safe(c[:-20])

    return {
        "ret5": ret5,
        "ret10": ret10,
        "ret20": ret20,
        "rsi": rsi,
        "vol_ratio": np.where(vol_sma20 > 0, vol / vol_sma20, np.nan),
        "dist_sma20": np.where(sma20 > 0, (c - sma20) / sma20, np.nan),
        "dist_sma50": np.where(sma50 > 0, (c - sma50) / sma50, np.nan),
        "atr_norm": np.where(c > 0, atr / c, np.nan),
        "body_ratio": body / rng,
        "uw_ratio": (h - btop) / rng,
        "lw_ratio": (bbot - l) / rng,
        "range_ratio": np.where(avg_rng10 > 0, rng / avg_rng10, np.nan),
    }


def _signals_to_X(
    signals: list[PatternSignal],
    feats: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build feature matrix from detected signals.

    Returns:
        X          shape (n_signals, n_features)
        bars       shape (n_signals,)  — bar index of each signal
        patterns   shape (n_signals,)  — pattern name strings
        directions shape (n_signals,)  — 'bull' or 'bear'
    """
    n_sig = len(signals)
    n_num = len(_NUM_FEAT_NAMES)
    n_total_feats = n_num + _N_PATS
    X = np.full((n_sig, n_total_feats), np.nan, dtype=float)

    feat_order = [
        feats["ret5"], feats["ret10"], feats["ret20"],
        feats["rsi"], feats["vol_ratio"],
        feats["dist_sma20"], feats["dist_sma50"],
        feats["atr_norm"],
        feats["body_ratio"], feats["uw_ratio"], feats["lw_ratio"],
        feats["range_ratio"],
    ]

    bars = np.array([s.bar for s in signals], dtype=int)
    patterns = np.array([s.pattern for s in signals])
    directions = np.array([s.direction for s in signals])

    for j, arr in enumerate(feat_order):
        X[:, j] = arr[bars]

    # One-hot encode pattern identity (fixed vocabulary)
    for k, sig in enumerate(signals):
        idx = _PAT_VOCAB.get(sig.pattern)
        if idx is not None:
            X[k, n_num + idx] = 1.0

    return X, bars, patterns, directions


def _make_y(
    bars: np.ndarray,
    close: np.ndarray,
    direction: str,
    hold_days: int,
) -> np.ndarray:
    """Compute binary labels: 1 = profitable trade, 0 = loss, -1 = no exit."""
    n = len(close)
    y = np.full(len(bars), -1, dtype=int)
    for k, b in enumerate(bars):
        eb = b + hold_days
        if eb >= n or close[b] <= 0:
            continue
        ret = (close[eb] - close[b]) / close[b]
        if direction == "bear":
            ret = -ret
        y[k] = 1 if ret > 0 else 0
    return y


# ── model builder ──────────────────────────────────────────────────────────────

def _make_pipeline() -> "Pipeline":
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("rf", RandomForestClassifier(
            n_estimators=_N_ESTIMATORS,
            max_features="sqrt",
            min_samples_leaf=_MIN_SAMPLES_LEAF,
            class_weight="balanced",
            random_state=_RF_SEED,
            n_jobs=-1,
        )),
    ])


# ── public API ─────────────────────────────────────────────────────────────────

def run_ai_analysis(
    df: pd.DataFrame,
    ticker: str,
    hold_periods: list[int] = DEFAULT_HOLD_PERIODS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    n_folds: int = _N_FOLDS,
    progress_cb=None,
) -> AIAnalysisResult:
    """Train RandomForest models and estimate candlestick pattern win probabilities.

    Args:
        df:           Daily OHLCV DataFrame — same data fed to :func:`run_backtest`.
        ticker:       Ticker label.
        hold_periods: Hold durations in trading days (default: 21 / 42 / 63).
        min_samples:  Minimum IS occurrences per pattern to include in output.
        n_folds:      Number of stratified K-fold CV splits.
        progress_cb:  Optional ``callable(step, total_steps)`` for progress updates.

    Returns:
        :class:`AIAnalysisResult` with populated ``pattern_stats``,
        ``signal_probs``, and ``feature_importances``.

    Raises:
        ImportError: If ``scikit-learn`` is not installed.
    """
    if not _SKLEARN_OK:
        raise ImportError(
            "scikit-learn is required for AI analysis. "
            "Install it with:  pip install scikit-learn>=1.4.0"
        )

    n = len(df)
    is_cutoff = int(n * IS_RATIO)
    close = df["Close"].to_numpy(dtype=float)
    total_steps = 3 + len(hold_periods) * 2  # detect + features + (train+predict)×N

    step = 0

    def _tick(label=""):
        nonlocal step
        step += 1
        if progress_cb:
            progress_cb(step, total_steps)

    # ── Step 1: run rule-based backtest (gives IS/OOS split context) ──────────
    backtest = run_backtest(df, ticker, hold_periods, min_samples)
    _tick("backtest done")

    # ── Step 2: detect signals + build feature matrix ─────────────────────────
    signals = detect_all(df)
    if not signals:
        return AIAnalysisResult(ticker=ticker, backtest=backtest)

    feats = _build_feature_arrays(df)
    X, bars, patterns, directions = _signals_to_X(signals, feats)
    _tick("features built")

    # Accumulators
    pat_stats_list: list[PatternAIStats] = []
    sig_preds: list[SignalPrediction] = []
    imp_accumulator: dict[str, list[float]] = {}
    n_models = 0

    # ── Step 3: train one model per (direction × hold_period) ─────────────────
    for dirn in ("bull", "bear"):
        dir_mask = directions == dirn
        if not np.any(dir_mask):
            continue
        X_dir = X[dir_mask]
        bars_dir = bars[dir_mask]
        pats_dir = patterns[dir_mask]

        for hp in hold_periods:
            _tick(f"train {dirn}/{hp}d")

            y_all = _make_y(bars_dir, close, dirn, hp)
            valid = y_all >= 0
            X_v = X_dir[valid]
            y_v = y_all[valid]
            bars_v = bars_dir[valid]
            pats_v = pats_dir[valid]

            is_flag = bars_v < is_cutoff
            X_is, y_is = X_v[is_flag], y_v[is_flag]
            X_oos, y_oos = X_v[~is_flag], y_v[~is_flag]
            bars_oos = bars_v[~is_flag]
            pats_oos = pats_v[~is_flag]

            # Need enough IS data and both classes present
            if len(X_is) < min_samples or len(np.unique(y_is)) < 2:
                continue

            # Build + CV-evaluate pipeline
            pipe = _make_pipeline()
            cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=_RF_SEED)
            cv_scores = cross_val_score(pipe, X_is, y_is, cv=cv, scoring="accuracy")
            cv_acc = float(cv_scores.mean())
            cv_std = float(cv_scores.std())

            # Fit on full IS set
            pipe.fit(X_is, y_is)
            n_models += 1

            # Accumulate feature importances
            rf_imp = pipe.named_steps["rf"].feature_importances_
            for fi, fname in enumerate(FEATURE_NAMES):
                if fi < len(rf_imp):
                    imp_accumulator.setdefault(fname, []).append(float(rf_imp[fi]))

            # OOS predictions
            probs_oos = np.empty(0)
            if len(X_oos) > 0:
                probs_oos = pipe.predict_proba(X_oos)[:, 1]

            _tick(f"predict {dirn}/{hp}d")

            # Per-signal OOS predictions → signal_probs
            for k in range(len(bars_oos)):
                prob = float(probs_oos[k]) if len(probs_oos) > k else 0.5
                sig_preds.append(SignalPrediction(
                    bar=int(bars_oos[k]),
                    pattern=str(pats_oos[k]),
                    direction=dirn,
                    hold_days=hp,
                    prob_win=prob,
                    in_sample=False,
                ))

            # Per-pattern OOS stats for this model
            for pat_name in ALL_PATTERN_NAMES:
                is_pat = pats_v[is_flag] == pat_name
                if is_pat.sum() < min_samples:
                    continue

                oos_pat = pats_oos == pat_name
                n_oos_pat = int(oos_pat.sum())

                if n_oos_pat > 0 and len(probs_oos) > 0:
                    probs_p = probs_oos[oos_pat]
                    y_p = y_oos[oos_pat]
                    oos_acc = float(np.mean((probs_p >= 0.5).astype(int) == y_p))
                    wins = probs_p[y_p == 1]
                    losses = probs_p[y_p == 0]
                    oos_avg_win = float(wins.mean()) if len(wins) > 0 else float("nan")
                    oos_avg_loss = float(losses.mean()) if len(losses) > 0 else float("nan")
                else:
                    oos_acc = float("nan")
                    oos_avg_win = float("nan")
                    oos_avg_loss = float("nan")

                pat_stats_list.append(PatternAIStats(
                    pattern=pat_name,
                    direction=dirn,
                    hold_days=hp,
                    n_is=int(is_pat.sum()),
                    n_oos=n_oos_pat,
                    oos_accuracy=oos_acc,
                    oos_avg_prob_win=oos_avg_win,
                    oos_avg_prob_loss=oos_avg_loss,
                    model_cv_accuracy=cv_acc,
                    model_cv_std=cv_std,
                ))

    # Sort pattern_stats: valid entries first (by OOS accuracy desc), then invalid
    def _sort_key(s: PatternAIStats) -> tuple:
        return (
            0 if s.is_valid else 1,
            -(s.oos_accuracy if s.oos_accuracy == s.oos_accuracy else 0),
        )
    pat_stats_list.sort(key=_sort_key)

    # Aggregate feature importances (mean across models)
    mean_imp = {
        name: float(np.mean(vals))
        for name, vals in imp_accumulator.items()
    }

    return AIAnalysisResult(
        ticker=ticker,
        backtest=backtest,
        pattern_stats=pat_stats_list,
        signal_probs=sig_preds,
        feature_importances=mean_imp,
        n_models_trained=n_models,
    )
