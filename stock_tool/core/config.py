"""Configuration loading for StockTool.

Reads ``config.yaml`` and exposes its contents as a tree of frozen, typed
dataclasses. Relative paths in the YAML are resolved against the directory
that contains the YAML file, so the application behaves the same regardless
of the current working directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILENAME = "config.yaml"


class ConfigError(ValueError):
    """Raised when ``config.yaml`` is missing required keys or has bad values."""


@dataclass(frozen=True)
class DataConfig:
    price_dir: Path
    export_dir: Path


@dataclass(frozen=True)
class DownloadConfig:
    default_start_date: date
    provider: str
    alpha_vantage_key: str


@dataclass(frozen=True)
class NewsConfig:
    provider: str
    newsapi_key: str
    max_headlines: int


@dataclass(frozen=True)
class ChartConfig:
    default_timeframe: str
    candle_bull_color: str
    candle_bear_color: str
    background_color: str
    ma_colors: tuple[str, ...]
    export_resolution: tuple[int, int]


@dataclass(frozen=True)
class IndicatorsConfig:
    rsi_period: int
    rsi_overbought: int
    rsi_oversold: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    stc_fast: int
    stc_slow: int
    stc_cycle: int
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    stoch_k: int = 14
    stoch_d: int = 3


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool
    cron: str
    symbols_file: Path


@dataclass(frozen=True)
class Config:
    data: DataConfig
    download: DownloadConfig
    news: NewsConfig
    chart: ChartConfig
    indicators: IndicatorsConfig
    scheduler: SchedulerConfig
    source_path: Path


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        raise ConfigError(f"Missing required key '{section_name}.{key}' in config")
    return section[key]


def _require_section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in raw or not isinstance(raw[name], dict):
        raise ConfigError(f"Missing required section '{name}' in config")
    return raw[name]


def _resolve_path(value: str, base_dir: Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(f"Invalid date '{value}'; expected YYYY-MM-DD") from exc
    raise ConfigError(f"Invalid date value: {value!r}")


def _parse_resolution(value: Any) -> tuple[int, int]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(v, int) for v in value)
    ):
        raise ConfigError(
            f"chart.export_resolution must be [width, height] integers; got {value!r}"
        )
    return int(value[0]), int(value[1])


def _parse_ma_colors(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"chart.ma_colors must be a list of strings; got {value!r}")
    return tuple(value)


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate ``config.yaml``.

    Args:
        path: Path to the YAML file. If ``None``, looks for ``config.yaml`` in
            the current working directory.

    Returns:
        A populated :class:`Config` instance.

    Raises:
        FileNotFoundError: The config file does not exist.
        ConfigError: Required keys are missing or values are malformed.
    """
    config_path = Path(path) if path is not None else Path.cwd() / DEFAULT_CONFIG_FILENAME
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    logger.debug("Loading config from %s", config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping; got {type(raw).__name__}")

    base_dir = config_path.parent

    data_raw = _require_section(raw, "data")
    data_cfg = DataConfig(
        price_dir=_resolve_path(_require(data_raw, "price_dir", "data"), base_dir),
        export_dir=_resolve_path(_require(data_raw, "export_dir", "data"), base_dir),
    )

    dl_raw = _require_section(raw, "download")
    download_cfg = DownloadConfig(
        default_start_date=_parse_date(_require(dl_raw, "default_start_date", "download")),
        provider=str(_require(dl_raw, "provider", "download")),
        alpha_vantage_key=str(dl_raw.get("alpha_vantage_key", "")),
    )

    news_raw = _require_section(raw, "news")
    news_cfg = NewsConfig(
        provider=str(_require(news_raw, "provider", "news")),
        newsapi_key=str(news_raw.get("newsapi_key", "")),
        max_headlines=int(_require(news_raw, "max_headlines", "news")),
    )

    chart_raw = _require_section(raw, "chart")
    chart_cfg = ChartConfig(
        default_timeframe=str(_require(chart_raw, "default_timeframe", "chart")),
        candle_bull_color=str(_require(chart_raw, "candle_bull_color", "chart")),
        candle_bear_color=str(_require(chart_raw, "candle_bear_color", "chart")),
        background_color=str(_require(chart_raw, "background_color", "chart")),
        ma_colors=_parse_ma_colors(_require(chart_raw, "ma_colors", "chart")),
        export_resolution=_parse_resolution(
            _require(chart_raw, "export_resolution", "chart")
        ),
    )

    ind_raw = _require_section(raw, "indicators")
    indicators_cfg = IndicatorsConfig(
        rsi_period=int(_require(ind_raw, "rsi_period", "indicators")),
        rsi_overbought=int(_require(ind_raw, "rsi_overbought", "indicators")),
        rsi_oversold=int(_require(ind_raw, "rsi_oversold", "indicators")),
        macd_fast=int(_require(ind_raw, "macd_fast", "indicators")),
        macd_slow=int(_require(ind_raw, "macd_slow", "indicators")),
        macd_signal=int(_require(ind_raw, "macd_signal", "indicators")),
        stc_fast=int(_require(ind_raw, "stc_fast", "indicators")),
        stc_slow=int(_require(ind_raw, "stc_slow", "indicators")),
        stc_cycle=int(_require(ind_raw, "stc_cycle", "indicators")),
        bb_period=int(ind_raw.get("bb_period", 20)),
        bb_std=float(ind_raw.get("bb_std", 2.0)),
        atr_period=int(ind_raw.get("atr_period", 14)),
        stoch_k=int(ind_raw.get("stoch_k", 14)),
        stoch_d=int(ind_raw.get("stoch_d", 3)),
    )

    sched_raw = _require_section(raw, "scheduler")
    scheduler_cfg = SchedulerConfig(
        enabled=bool(_require(sched_raw, "enabled", "scheduler")),
        cron=str(_require(sched_raw, "cron", "scheduler")),
        symbols_file=_resolve_path(
            _require(sched_raw, "symbols_file", "scheduler"), base_dir
        ),
    )

    return Config(
        data=data_cfg,
        download=download_cfg,
        news=news_cfg,
        chart=chart_cfg,
        indicators=indicators_cfg,
        scheduler=scheduler_cfg,
        source_path=config_path,
    )


def save_config(config: Config, path: str | Path | None = None) -> Path:
    """Serialise *config* back to YAML and write to disk.

    Args:
        config: The :class:`Config` to persist.
        path:   Destination path.  Defaults to ``config.source_path``.

    Returns:
        The path that was written.
    """
    dest = Path(path) if path is not None else config.source_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    base = dest.parent

    def _rel(p: Path) -> str:
        try:
            return "./" + str(p.relative_to(base)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    data: dict = {
        "data": {
            "price_dir": _rel(config.data.price_dir),
            "export_dir": _rel(config.data.export_dir),
        },
        "download": {
            "default_start_date": config.download.default_start_date.isoformat(),
            "provider": config.download.provider,
            "alpha_vantage_key": config.download.alpha_vantage_key,
        },
        "news": {
            "provider": config.news.provider,
            "newsapi_key": config.news.newsapi_key,
            "max_headlines": config.news.max_headlines,
        },
        "chart": {
            "default_timeframe": config.chart.default_timeframe,
            "candle_bull_color": config.chart.candle_bull_color,
            "candle_bear_color": config.chart.candle_bear_color,
            "background_color": config.chart.background_color,
            "ma_colors": list(config.chart.ma_colors),
            "export_resolution": list(config.chart.export_resolution),
        },
        "indicators": {
            "rsi_period": config.indicators.rsi_period,
            "rsi_overbought": config.indicators.rsi_overbought,
            "rsi_oversold": config.indicators.rsi_oversold,
            "macd_fast": config.indicators.macd_fast,
            "macd_slow": config.indicators.macd_slow,
            "macd_signal": config.indicators.macd_signal,
            "stc_fast": config.indicators.stc_fast,
            "stc_slow": config.indicators.stc_slow,
            "stc_cycle": config.indicators.stc_cycle,
            "bb_period": config.indicators.bb_period,
            "bb_std": config.indicators.bb_std,
            "atr_period": config.indicators.atr_period,
            "stoch_k": config.indicators.stoch_k,
            "stoch_d": config.indicators.stoch_d,
        },
        "scheduler": {
            "enabled": config.scheduler.enabled,
            "cron": config.scheduler.cron,
            "symbols_file": _rel(config.scheduler.symbols_file),
        },
    }
    dest.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False),
                    encoding="utf-8")
    logger.debug("Saved config to %s", dest)
    return dest
