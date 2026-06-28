"""Tests for core.config."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.config import (
    Config,
    ConfigError,
    DataConfig,
    load_config,
    save_config,
)


VALID_YAML = """\
data:
  price_dir: "./prices"
  export_dir: "./exports"

download:
  default_start_date: "2010-01-01"
  provider: "yfinance"
  alpha_vantage_key: ""

news:
  provider: "newsapi"
  newsapi_key: ""
  max_headlines: 20

chart:
  default_timeframe: "D"
  candle_bull_color: "#26a69a"
  candle_bear_color: "#ef5350"
  background_color: "#131722"
  ma_colors: ["#2196F3", "#FF9800"]
  export_resolution: [1920, 1080]

indicators:
  rsi_period: 14
  rsi_overbought: 70
  rsi_oversold: 30
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  stc_fast: 23
  stc_slow: 50
  stc_cycle: 10

scheduler:
  enabled: false
  cron: "0 18 * * 1-5"
  symbols_file: "./watchlist.txt"
"""


def _write_yaml(tmp_path: Path, content: str = VALID_YAML) -> Path:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(content, encoding="utf-8")
    return cfg_path


def test_load_config_returns_typed_dataclass(tmp_path):
    cfg = load_config(_write_yaml(tmp_path))

    assert isinstance(cfg, Config)
    assert isinstance(cfg.data, DataConfig)
    assert cfg.download.default_start_date == date(2010, 1, 1)
    assert cfg.download.provider == "yfinance"
    assert cfg.news.max_headlines == 20
    assert cfg.chart.default_timeframe == "D"
    assert cfg.chart.ma_colors == ("#2196F3", "#FF9800")
    assert cfg.chart.export_resolution == (1920, 1080)
    assert cfg.indicators.rsi_period == 14
    assert cfg.scheduler.enabled is False


def test_load_config_resolves_relative_paths_against_yaml_dir(tmp_path):
    cfg = load_config(_write_yaml(tmp_path))

    assert cfg.data.price_dir == (tmp_path / "prices").resolve()
    assert cfg.data.export_dir == (tmp_path / "exports").resolve()
    assert cfg.scheduler.symbols_file == (tmp_path / "watchlist.txt").resolve()


def test_load_config_keeps_absolute_paths_unchanged(tmp_path):
    abs_dir = (tmp_path / "absolute_prices").resolve()
    yaml_text = VALID_YAML.replace('"./prices"', f'"{abs_dir.as_posix()}"')
    cfg = load_config(_write_yaml(tmp_path, yaml_text))

    assert cfg.data.price_dir == abs_dir


def test_load_config_is_frozen(tmp_path):
    cfg = load_config(_write_yaml(tmp_path))
    with pytest.raises(Exception):
        cfg.download.provider = "alpha_vantage"  # type: ignore[misc]


def test_load_config_missing_section_raises(tmp_path):
    bad = VALID_YAML.replace("indicators:", "indicators_typo:")
    with pytest.raises(ConfigError, match="indicators"):
        load_config(_write_yaml(tmp_path, bad))


def test_load_config_missing_required_key_raises(tmp_path):
    bad = VALID_YAML.replace("  rsi_period: 14\n", "")
    with pytest.raises(ConfigError, match="rsi_period"):
        load_config(_write_yaml(tmp_path, bad))


def test_load_config_invalid_date_raises(tmp_path):
    bad = VALID_YAML.replace("2010-01-01", "not-a-date")
    with pytest.raises(ConfigError, match="date"):
        load_config(_write_yaml(tmp_path, bad))


def test_load_config_invalid_resolution_raises(tmp_path):
    bad = VALID_YAML.replace("[1920, 1080]", "[1920]")
    with pytest.raises(ConfigError, match="export_resolution"):
        load_config(_write_yaml(tmp_path, bad))


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_load_config_records_source_path(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    assert cfg.source_path == path.resolve()


# ── save_config ───────────────────────────────────────────────────────────────

def test_save_config_writes_yaml(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    out = tmp_path / "out.yaml"
    save_config(cfg, out)
    assert out.is_file()


def test_save_config_roundtrips_all_sections(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    out = tmp_path / "roundtrip.yaml"
    save_config(cfg, out)
    cfg2 = load_config(out)

    assert cfg2.download.default_start_date == cfg.download.default_start_date
    assert cfg2.download.provider == cfg.download.provider
    assert cfg2.news.max_headlines == cfg.news.max_headlines
    assert cfg2.chart.candle_bull_color == cfg.chart.candle_bull_color
    assert cfg2.chart.ma_colors == cfg.chart.ma_colors
    assert cfg2.chart.export_resolution == cfg.chart.export_resolution
    assert cfg2.indicators.rsi_period == cfg.indicators.rsi_period
    assert cfg2.indicators.stc_fast == cfg.indicators.stc_fast
    assert cfg2.scheduler.enabled == cfg.scheduler.enabled
    assert cfg2.scheduler.cron == cfg.scheduler.cron


def test_save_config_defaults_to_source_path(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    returned = save_config(cfg)
    assert returned == path.resolve()
    cfg2 = load_config(path)
    assert cfg2.indicators.rsi_period == cfg.indicators.rsi_period


def test_save_config_creates_parent_dirs(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    deep = tmp_path / "a" / "b" / "c" / "config.yaml"
    save_config(cfg, deep)
    assert deep.is_file()


def test_save_config_stores_relative_paths(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    # Save to same dir: paths (./prices, ./exports …) stay relative
    out = tmp_path / "copy.yaml"
    save_config(cfg, out)
    raw_text = out.read_text(encoding="utf-8")
    assert "./" in raw_text   # paths stored relative


def test_save_config_returns_written_path(tmp_path):
    path = _write_yaml(tmp_path)
    cfg = load_config(path)
    out = tmp_path / "saved.yaml"
    result = save_config(cfg, out)
    assert result == out
