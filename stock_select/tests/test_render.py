"""Tests for the generated page."""
from __future__ import annotations

import json
import re

import pytest

import config
import render
import screener


@pytest.fixture(scope="module")
def result():
    return screener.run(["SP500", "HSI"], limit=6, demo_mode=True, log=lambda *a: None)


@pytest.fixture(scope="module")
def page(result):
    return render.build_page(result)


def test_page_is_a_complete_document(page):
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    assert page.count("<body>") == 1


def test_page_is_self_contained(page):
    """No CDN, no external stylesheet, no remote image — it must open offline."""
    assert "src=\"http" not in page
    assert "href=\"http" not in page
    assert "@import" not in page


def test_every_section_is_present(page):
    for anchor in ('id="universe"', 'id="heatmap"', 'id="tbody"', 'id="thead"',
                   'id="hero-value"', 'id="selstats"', 'id="f-score"', 'id="export"',
                   "Methodology"):
        assert anchor in page, anchor


def test_filters_cover_every_promised_control(page):
    for control in ("f-stack", "f-cross", "f-rsi", "f-sector", "f-score", "f-q", "reset"):
        assert f'id="{control}"' in page


def test_payload_round_trips(page, result):
    blob = re.search(r"window\.__SELECT__ = (\{.*?\});</script>", page, re.S).group(1)
    data = json.loads(blob.replace("\\u003c", "<"))
    assert len(data["rows"]) == len(result["rows"])
    assert [f["key"] for f in data["factors"]] == list(config.FACTOR_COMPONENTS)
    assert data["weights"] == config.FACTOR_WEIGHTS


def test_demo_run_is_labelled_as_demo(page):
    assert '<div class="demo-banner">' in page and "Demo data." in page


def test_live_run_carries_no_demo_banner(result):
    # The CSS rule is always present; the banner element must not be.
    live = render.build_page(dict(result, demo=False))
    assert '<div class="demo-banner">' not in live
    assert "Demo data." not in live


def test_missing_fundamentals_are_disclosed(result):
    page = render.build_page(dict(result, fundamentals=False))
    assert "quality &amp; value neutral" in page


def test_hostile_company_name_cannot_break_out_of_the_script_block(result):
    hostile = "</script><img src=x onerror=alert(1)>"
    rows = [dict(result["rows"][0], name=hostile, sector=hostile, ticker=hostile)]
    page = render.build_page(dict(result, rows=rows))

    # The literal tag must not survive anywhere — not in the JSON payload and
    # not in the sector <option> markup.
    assert "</script><img" not in page
    assert "<img src=x" not in page
    # …but the text itself is still carried, escaped, so the page renders it.
    blob = re.search(r"window\.__SELECT__ = (\{.*?\});</script>", page, re.S).group(1)
    assert json.loads(blob.replace("\\u003c", "<"))["rows"][0]["name"] == hostile


def test_factor_weights_are_published_on_the_page(page):
    for weight in config.FACTOR_WEIGHTS.values():
        assert f"weight {weight:.0%}" in page


def test_thresholds_come_from_config(page):
    assert f"&ge; {int(config.RSI_OVERBOUGHT)}" in page
    assert f"&le; {int(config.RSI_OVERSOLD)}" in page
