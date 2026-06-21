"""
Visual constants — colors, stars, badges.
Theme drives Dashboard, Email, and Telegram consistently.
"""

# ── Star ratings ──────────────────────────────────────────────────────────────

STAR_FULL  = "★"
STAR_EMPTY = "☆"

STARS = {
    5: "★★★★★",
    4: "★★★★☆",
    3: "★★★☆☆",
    2: "★★☆☆☆",
    1: "★☆☆☆☆",
    0: "☆☆☆☆☆",
}


def stars(n: int) -> str:
    return STARS.get(max(0, min(5, int(n))), "☆☆☆☆☆")


def signal_quality_stars(r2: float) -> tuple[str, str]:
    if r2 >= 75: return STARS[5], "Exceptional"
    if r2 >= 65: return STARS[4], "Strong"
    if r2 >= 55: return STARS[3], "Good"
    if r2 >= 45: return STARS[2], "Acceptable"
    return STARS[1], "Developing"


def portfolio_health_stars(health_score: float) -> tuple[str, str, str]:
    """Returns (stars, label, color_hex)."""
    if health_score >= 85: return STARS[5], "Stable",             "#155724"
    if health_score >= 70: return STARS[4], "Well Positioned",    "#155724"
    if health_score >= 55: return STARS[3], "Attention Advised",  "#856404"
    if health_score >= 40: return STARS[2], "Needs Attention",    "#842029"
    return                        STARS[1], "Review Recommended", "#842029"


# ── Email color palette ───────────────────────────────────────────────────────

class EmailTheme:
    HEADER_BG       = "#1a3a5c"
    HEADER_FG       = "#ffffff"
    HEADER_SUBTITLE = "#8fb8d8"

    SECTION_TITLE   = "#0B5394"
    BODY_FG         = "#333333"
    MUTED_FG        = "#666666"

    BUY_BG          = "#d4edda"
    BUY_FG          = "#155724"
    BUY_BORDER      = "#c3e6cb"

    WATCH_BG        = "#cfe2ff"
    WATCH_FG        = "#084298"
    WATCH_BORDER    = "#b6d4fe"

    PRIORITY_BG     = "#fff3cd"
    PRIORITY_FG     = "#664d03"
    PRIORITY_BORDER = "#ffecb5"

    PORTFOLIO_HEADER = "#1a3a5c"
    ROW_ALT_BG       = "#f9fafb"
    BORDER_COLOR     = "#dde3ea"

    POSITIVE_PNL    = "#155724"
    NEGATIVE_PNL    = "#721c24"


# ── Dashboard color palette ───────────────────────────────────────────────────

class DashTheme:
    BG0 = "#0b0c1a"
    BG1 = "#10112a"
    BG2 = "#181930"
    BOR = "#252645"
    FG  = "#d0d4e8"
    DIM = "#8b8fa8"
    G   = "#4caf50"
    R   = "#f44336"
    A   = "#f0b840"
    B   = "#50d8d0"


# ── Signal badge colors (for HTML email) ─────────────────────────────────────

def signal_badge_colors(score: float) -> tuple[str, str, str]:
    """Returns (text_color, bg_color, border_color) for the signal badge."""
    if score >= 85: return "#155724", "#d4edda", "#c3e6cb"
    if score >= 70: return "#155724", "#c3e6cb", "#b1dfbb"
    if score >= 55: return "#0a3622", "#d1e7dd", "#a3cfbb"
    if score >= 35: return "#084298", "#cfe2ff", "#b6d4fe"
    return                 "#721c24", "#f8d7da", "#f5c6cb"


# ── Telegram visual separators ────────────────────────────────────────────────

TG_DIVIDER       = "─" * 25
TG_SECTION_DIV   = "━" * 21
TG_HEADER_DIV    = "━" * 21
