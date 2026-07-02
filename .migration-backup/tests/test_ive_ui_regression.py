"""
tests/test_ive_ui_regression.py — Playwright UI regression suite for the IVE card.

WHY THIS SUITE EXISTS
─────────────────────
The IVE card was invisible on the dashboard despite being present in the HTML.
Root cause: <details> element without the `open` attribute — browser collapses
content by default. HTML inspection alone cannot catch this class of bug.

WHAT THIS SUITE PROVES
───────────────────────
Every test verifies that IVE card fields are not just in the DOM, but actually
VISIBLE to the user: non-zero bounding box, no hidden CSS properties, no
collapsed ancestor (<details>, overflow:hidden, etc.).

SURFACES COVERED
────────────────
  RT-1  Dashboard (BUY signal context)
  RT-2  Dashboard (RE-ACCUMULATION context)
  RT-3  BUY alert email
  RT-4  RE-ACCUMULATION alert email
  RT-5  Daily EGX email (IVE rows inside signal tables)
  RT-6  Negative: no card for ticker without valuation data
  RT-7  Missing valuation: graceful render with no IVE card (no crash)
  RT-8  Regression probe: prove <details> collapse IS caught by this suite

Run:
  pytest tests/test_ive_ui_regression.py -v

Screenshots saved to: tests/artifacts/ive/
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

# ── Project root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import valuation.db as _vdb

# ── Constants ─────────────────────────────────────────────────────────────────

ARTIFACTS_DIR = ROOT / "tests" / "artifacts" / "ive"

import os
_default_chromium = "/opt/pw-browsers/chromium"
CHROMIUM_PATH = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", _default_chromium)

# Fields that must be visible in the dark-theme dashboard card
DASHBOARD_FIELDS = [
    "Fair Value", "Upside", "Bull Case", "Base Case", "Bear Case", "Consensus",
]

# Fields that must be visible in the light-theme email card
EMAIL_FIELDS = [
    "Current Price", "Fair Value (IVE)", "Upside / Downside",
    "Bull Case", "Base Case", "Bear Case",
    "Analyst Consensus Target", "Last Financial Statement", "Valuation Date",
]

TICKER_A = "COMI.CA"   # BUY signal test ticker
TICKER_B = "ETEL.CA"   # RE-ACCUMULATION test ticker
TICKER_NONE = "XXXX.CA"  # ticker with no valuation data in DB


# ── DB Fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def isolated_db(tmp_path_factory):
    """
    Module-scoped isolated valuation DB redirected into a temp path.
    Restores the original DB path on teardown.
    """
    db_path = tmp_path_factory.mktemp("ive_regression_db") / "valuation.db"
    original_db   = _vdb._DB
    original_flag = _vdb._schema_initialized

    _vdb._DB = db_path
    _vdb._schema_initialized = False
    _vdb.init_db()

    conn = sqlite3.connect(str(db_path))

    for ticker, fv, bear, bull, consensus in [
        (TICKER_A, 138.54,  99.75, 187.03, 131.50),
        (TICKER_B,  98.29,  66.24, 141.70,  93.10),
    ]:
        _vdb.save_company(conn, ticker, {
            "company_name": ticker, "sector": "Banks",
            "industry": "Banking", "currency": "EGP",
            "shares_outstanding": 100_000_000,
        })
        # Minimal financials row so last_stmt_year query returns a value
        conn.execute(
            "INSERT OR IGNORE INTO financials (ticker, year) VALUES (?, 2023)",
            (ticker,),
        )
        _vdb.save_valuation_model(conn, ticker, "2026-06-28", {
            "dcf":             fv * 0.95,
            "ddm":             fv * 0.85,
            "residual_income": fv * 0.90,
            "earnings_power":  fv * 0.88,
            "ev_ebitda":       fv * 1.05,
            "pe":              fv * 1.10,
            "pb":              fv * 0.80,
            "weighted_fair_value": fv,
            "bear_case":  bear,
            "base_case":  fv,
            "bull_case":  bull,
        })
        _vdb.save_analyst_consensus(
            conn, ticker, "Test Research", consensus, "BUY", "2026-06-28"
        )

    conn.commit()
    conn.close()

    yield db_path

    _vdb._DB               = original_db
    _vdb._schema_initialized = original_flag


# ── Browser Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def browser_inst():
    """Module-scoped Playwright Chromium browser."""
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROMIUM_PATH, headless=True)
        yield b
        b.close()


@pytest.fixture()
def page(browser_inst: Browser) -> Generator[Page, None, None]:
    """Per-test Playwright page (900×800 viewport)."""
    p = browser_inst.new_page(viewport={"width": 900, "height": 800})
    yield p
    p.close()


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _wrap_dashboard(card_html: str) -> str:
    """Minimal dark-theme wrapper matching production dashboard context."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>body{{background:#0a0b14;padding:20px;font-family:Arial,sans-serif;}}</style>
</head>
<body>
<div style="max-width:900px;margin:auto;padding:16px;background:#10112a;
            border:1px solid #252645;border-radius:10px;">
  {card_html}
</div>
</body></html>"""


def _wrap_email(card_html: str) -> str:
    """Minimal light-theme wrapper matching production email table structure."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="background:#f5f5f5;padding:20px;">
<table width="640" cellpadding="0" cellspacing="0"
       style="margin:auto;background:#ffffff;border-collapse:collapse;">
  <tr><td style="padding:14px 28px 0 28px;">{card_html}</td></tr>
</table>
</body></html>"""


def _open(page: Page, html: str, tmp_path: Path) -> None:
    """Write HTML to temp file and open in Playwright."""
    f = tmp_path / "ive_test.html"
    f.write_text(html, encoding="utf-8")
    page.goto(f"file://{f}")
    page.wait_for_load_state("networkidle")


def _save_screenshot(page: Page, name: str) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS_DIR / name), full_page=True)


# ── Core Visibility Assertion ─────────────────────────────────────────────────

def _assert_visible(page: Page, text: str, ctx: str = "") -> None:
    """
    Full visibility assertion for a text node in a rendered page.

    Checks (in order):
      1. Element exists in DOM
      2. Playwright is_visible() == True
      3. Bounding box: height > 0 and width > 0
      4. Computed display != 'none'
      5. Computed visibility != 'hidden'
      6. Computed opacity > 0
      7. No ancestor hides or collapses the element:
           - display:none
           - visibility:hidden
           - opacity:0
           - <details> without open attribute  ← catches the original regression
    """
    label = f"[{ctx}] text={text!r}"

    # 1. DOM existence
    el = page.locator(f"text={text}").first
    assert el.count() > 0, f"{label}: NOT FOUND in DOM"

    # 2. Playwright built-in
    assert el.is_visible(), f"{label}: Playwright is_visible()=False"

    # 3. Bounding box
    bb = el.bounding_box()
    assert bb is not None, f"{label}: bounding_box is None (detached)"
    assert bb["height"] > 0, f"{label}: height=0 (element collapsed or hidden)"
    assert bb["width"]  > 0, f"{label}: width=0 (element collapsed or hidden)"

    # 4-6. Computed styles
    styles = page.evaluate(
        """el => {
            const s = window.getComputedStyle(el);
            return {
                display:    s.display,
                visibility: s.visibility,
                opacity:    parseFloat(s.opacity),
            };
        }""",
        el.element_handle(),
    )
    assert styles["display"]    != "none",    f"{label}: display=none"
    assert styles["visibility"] != "hidden",  f"{label}: visibility=hidden"
    assert styles["opacity"]    > 0,          f"{label}: opacity=0"

    # 7. Walk ancestor chain — catches <details> collapse and other hiding patterns
    hidden_by = page.evaluate(
        """el => {
            let cur = el.parentElement;
            while (cur && cur.tagName !== "BODY") {
                const s = window.getComputedStyle(cur);
                if (s.display === "none")
                    return "ancestor display:none — " + cur.tagName;
                if (s.visibility === "hidden")
                    return "ancestor visibility:hidden — " + cur.tagName;
                if (parseFloat(s.opacity) === 0)
                    return "ancestor opacity:0 — " + cur.tagName;
                if (cur.tagName === "DETAILS" && !cur.open)
                    return "<details> collapsed (open=false) — content is hidden";
                cur = cur.parentElement;
            }
            return null;
        }""",
        el.element_handle(),
    )
    assert hidden_by is None, f"{label}: hidden by ancestor → {hidden_by}"


def _assert_card_absent(page: Page, ctx: str = "") -> None:
    """Assert no IVE card exists in the rendered page."""
    el = page.locator("text=Institutional Valuation").first
    count = el.count()
    assert count == 0, (
        f"[{ctx}] IVE card should be absent but found {count} element(s)"
    )


# ── RT-1: Dashboard — BUY context ─────────────────────────────────────────────

def test_rt1_dashboard_buy_card_visible(isolated_db, page, tmp_path):
    """RT-1: IVE dashboard card is fully visible in BUY signal context."""
    from valuation.card import render_dashboard_card

    card_html = render_dashboard_card(TICKER_A, current_price=120.5)
    assert card_html, "render_dashboard_card() returned empty — check DB fixture"

    html = _wrap_dashboard(card_html)
    _open(page, html, tmp_path)

    for field in DASHBOARD_FIELDS:
        _assert_visible(page, field, ctx="Dashboard-BUY")

    _save_screenshot(page, "dashboard_buy.png")


# ── RT-2: Dashboard — RE-ACCUMULATION context ─────────────────────────────────

def test_rt2_dashboard_reaccum_card_visible(isolated_db, page, tmp_path):
    """RT-2: IVE dashboard card is fully visible in RE-ACCUMULATION context."""
    from valuation.card import render_dashboard_card

    card_html = render_dashboard_card(TICKER_B, current_price=88.0)
    assert card_html, "render_dashboard_card() returned empty — check DB fixture"

    html = _wrap_dashboard(card_html)
    _open(page, html, tmp_path)

    for field in DASHBOARD_FIELDS:
        _assert_visible(page, field, ctx="Dashboard-RE-ACCUM")

    _save_screenshot(page, "dashboard_reaccum.png")


# ── RT-3: BUY alert email ─────────────────────────────────────────────────────

def test_rt3_buy_email_card_visible(isolated_db, page, tmp_path):
    """RT-3: IVE email card is fully visible in BUY alert email."""
    from alert_email import build_alert_email

    _, html = build_alert_email({
        "ticker":        TICKER_A,
        "event_type":    "FIRST_BUY",
        "current_price": 120.5,
        "entry_price":   115.0,
        "stop_loss":     105.0,
        "target_1":      130.0,
        "target_2":      145.0,
        "score":         72.5,
        "reason":        "Constitutional BUY signal — regression test.",
    })

    _open(page, html, tmp_path)

    for field in EMAIL_FIELDS:
        _assert_visible(page, field, ctx="BUY-Email")

    _save_screenshot(page, "buy_email.png")


# ── RT-4: RE-ACCUMULATION alert email ─────────────────────────────────────────

def test_rt4_reaccum_email_card_visible(isolated_db, page, tmp_path):
    """RT-4: IVE email card is fully visible in RE-ACCUMULATION alert email."""
    from alert_email import build_alert_email

    _, html = build_alert_email({
        "ticker":        TICKER_B,
        "event_type":    "RE_ACCUMULATION",
        "current_price": 88.0,
        "entry_price":   84.0,
        "stop_loss":     78.0,
        "target_1":      96.0,
        "target_2":      108.0,
        "score":         68.0,
        "reason":        "Re-accumulation signal — regression test.",
    })

    _open(page, html, tmp_path)

    for field in EMAIL_FIELDS:
        _assert_visible(page, field, ctx="RE-ACCUM-Email")

    _save_screenshot(page, "reaccum_email.png")


# ── RT-5: Daily email — IVE card in signal rows ───────────────────────────────

def test_rt5_daily_email_ive_visible_for_signal_tickers(isolated_db, page, tmp_path):
    """RT-5: Daily email IVE rows are visible for BUY/RE-ACCUM signal tickers.

    Generates a minimal daily-email-style HTML containing the IVE card
    for a signal ticker (mirrors how egx_email.py injects ive_row into
    the BUY/RE-ACCUM signal tables).
    """
    from valuation.card import render_email_card

    card_html = render_email_card(TICKER_A, current_price=120.5)
    assert card_html, "render_email_card() returned empty — check DB fixture"

    # Mirror the egx_email.py injection pattern: ive_row inside a <table>
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="background:#f5f5f5;padding:20px;">
<table width="700" cellpadding="0" cellspacing="0"
       style="margin:auto;background:#ffffff;border-collapse:collapse;font-family:Arial;">
  <tr>
    <th style="padding:8px;background:#1a3a5c;color:#fff;">TICKER</th>
    <th style="padding:8px;background:#1a3a5c;color:#fff;">PRICE</th>
    <th style="padding:8px;background:#1a3a5c;color:#fff;">SIGNAL</th>
  </tr>
  <tr>
    <td style="padding:8px;">{TICKER_A}</td>
    <td style="padding:8px;">120.50 EGP</td>
    <td style="padding:8px;">FIRST BUY</td>
  </tr>
  <tr>
    <td colspan="5" style="padding:0 10px 10px 10px;">{card_html}</td>
  </tr>
</table>
</body></html>"""

    _open(page, html, tmp_path)

    for field in EMAIL_FIELDS:
        _assert_visible(page, field, ctx="Daily-Email")

    _save_screenshot(page, "daily_email.png")


# ── RT-6: Negative — no card for ticker without data ─────────────────────────

def test_rt6_no_card_for_ticker_without_valuation(isolated_db, page, tmp_path):
    """RT-6: IVE card must NOT appear for a ticker with no valuation data."""
    from valuation.card import render_dashboard_card, render_email_card

    # Both renderers should return empty string
    dash_html  = render_dashboard_card(TICKER_NONE, current_price=50.0)
    email_html = render_email_card(TICKER_NONE, current_price=50.0)

    assert dash_html  == "", f"Dashboard card should be empty for {TICKER_NONE}, got: {dash_html[:100]}"
    assert email_html == "", f"Email card should be empty for {TICKER_NONE}, got: {email_html[:100]}"

    # Render a page with the (empty) card — no card element must appear
    html = _wrap_dashboard(dash_html)
    _open(page, html, tmp_path)
    _assert_card_absent(page, ctx="No-Data-Ticker")
    _save_screenshot(page, "no_card_negative.png")


# ── RT-7: Missing valuation — graceful degradation ────────────────────────────

def test_rt7_buy_email_renders_without_crash_when_no_valuation(isolated_db, page, tmp_path):
    """RT-7: BUY email for a ticker with no IVE data renders correctly.

    No empty card, no placeholder text, no broken layout, no exception.
    The email renders fully — just without the IVE block.
    """
    from alert_email import build_alert_email

    _, html = build_alert_email({
        "ticker":        TICKER_NONE,
        "event_type":    "FIRST_BUY",
        "current_price": 50.0,
        "entry_price":   48.0,
        "stop_loss":     44.0,
        "target_1":      55.0,
        "target_2":      62.0,
        "score":         65.0,
        "reason":        "Signal — no valuation data available for this ticker.",
    })

    assert html, "build_alert_email() must return non-empty HTML even without IVE data"
    assert "CONSTITUTIONAL COMMAND CENTER" in html or "Constitutional Alert" in html, (
        "Email must render the main content even without IVE card"
    )

    _open(page, html, tmp_path)

    # No IVE card should appear
    _assert_card_absent(page, ctx="Missing-Valuation-Email")

    # Page must not be broken — check key structural elements are visible
    assert page.locator("text=FIRST BUY").first.count() > 0 or \
           page.locator("text=BUY SIGNAL").first.count() > 0 or \
           page.locator(f"text={TICKER_NONE}").first.count() > 0, (
        "Email page structure broken — expected signal type or ticker to be visible"
    )

    _save_screenshot(page, "no_valuation_graceful.png")


# ── RT-8: Regression probe — prove <details> is caught ───────────────────────

def test_rt8_regression_probe__details_collapse_is_caught(page, tmp_path):
    """RT-8: Prove this suite catches the original <details> hidden regression.

    Generates HTML with the OLD buggy structure (<details> without open),
    then verifies our visibility assertion raises AssertionError.
    This proves: if the fix is reverted, the suite will block the merge.
    """
    # OLD buggy HTML: <details> collapses the card content by default
    buggy_html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>body{background:#0a0b14;padding:20px;font-family:Arial,sans-serif;}</style>
</head>
<body>
<details style="margin-top:10px;">
  <summary style="font-size:11px;font-weight:700;color:#50d8d0;cursor:pointer;">
    &#127974; Institutional Valuation
    <span style="font-size:10px;color:#8b8fa8;">(click to expand)</span>
  </summary>
  <div style="padding:10px;background:#10112a;border:1px solid #252645;border-radius:7px;">
    <div style="display:flex;flex-wrap:wrap;gap:8px;">
      <div style="background:#0b0c1a;border:1px solid #252645;border-radius:6px;padding:8px 10px;">
        <div style="font-size:9px;color:#8b8fa8;">FAIR VALUE</div>
        <div style="font-size:13px;font-weight:700;color:#50d8d0;">138.54 EGP</div>
      </div>
    </div>
  </div>
</details>
</body></html>"""

    _open(page, buggy_html, tmp_path)

    # Heading IS visible (it's in the <summary>)
    heading = page.locator("text=Institutional Valuation").first
    assert heading.count() > 0, "Heading not found — test setup error"
    assert heading.is_visible(), "Heading should be visible (it's in <summary>)"

    # But the data inside <details> must NOT be visible
    fair_value_el = page.locator("text=FAIR VALUE").first
    assert fair_value_el.count() > 0, "FAIR VALUE element not found — test setup error"

    # _assert_visible MUST raise AssertionError because <details> hides the content.
    # Playwright's is_visible() catches it at step 2 (before the ancestor walk fires),
    # so we match on the common substring rather than the specific step message.
    with pytest.raises(AssertionError):
        _assert_visible(page, "FAIR VALUE", ctx="Regression-Probe-BuggyHTML")

    # Also verify the bounding box check would have caught it
    # (content div is zero-height when details is closed)
    assert not fair_value_el.is_visible(), (
        "CRITICAL: Fair Value appears visible inside collapsed <details>. "
        "The regression probe is broken — fix _assert_visible()."
    )

    # Directly verify that the ancestor walk (step 7 of _assert_visible) identifies
    # the <details> collapse by name — this is what would fire if is_visible() ever
    # changes behaviour to permit closed-details content.
    hidden_by = page.evaluate(
        """el => {
            let cur = el.parentElement;
            while (cur && cur.tagName !== "BODY") {
                if (cur.tagName === "DETAILS" && !cur.open)
                    return "<details> collapsed (open=false) — content is hidden";
                cur = cur.parentElement;
            }
            return null;
        }""",
        fair_value_el.element_handle(),
    )
    assert hidden_by is not None and "<details> collapsed" in hidden_by, (
        f"Ancestor walk must identify <details> collapse, got: {hidden_by}"
    )

    # Screenshot showing the collapsed state
    _save_screenshot(page, "regression_probe_before_fix.png")


# ── RT-9: Verify fixed HTML passes all checks ─────────────────────────────────

def test_rt9_fixed_html_passes_all_visibility_checks(isolated_db, page, tmp_path):
    """RT-9: The FIXED card structure passes all visibility checks.

    Uses the actual render_dashboard_card() output (which uses <div> not <details>)
    and verifies all assertions pass. This is the final proof that the fix works.
    """
    from valuation.card import render_dashboard_card

    card_html = render_dashboard_card(TICKER_A, current_price=120.5)
    assert "<details" not in card_html, (
        "render_dashboard_card() must not use <details> element. "
        "The fix has been reverted — this test is blocking a regression."
    )

    html = _wrap_dashboard(card_html)
    _open(page, html, tmp_path)

    for field in DASHBOARD_FIELDS:
        _assert_visible(page, field, ctx="Fixed-Card")

    _save_screenshot(page, "regression_probe_after_fix.png")
