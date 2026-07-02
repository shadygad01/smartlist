"""
Constitutional vocabulary — all user-facing labels live here.

Production logic is immutable. Only the words we show change.
"""

# ── Stock names — single source of truth ─────────────────────────────────────

STOCK_NAMES = {
    "COMI.CA": "Commercial International Bank",
    "TMGH.CA": "Talaat Moustafa Group",
    "ETEL.CA": "Telecom Egypt",
    "EGAL.CA": "Egypt Aluminum",
    "EAST.CA": "Eastern Company",
    "ABUK.CA": "Abu Qir Fertilizers",
    "ORAS.CA": "Orascom Construction PLC",
    "EFIH.CA": "e-Finance for Digital and Financial Investments",
    "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
    "FWRY.CA": "Fawry for Banking Technology",
    "EMFD.CA": "Emaar Misr for Development",
    "PHDC.CA": "Palm Hills Developments",
    "ORHD.CA": "Orascom Development Egypt",
    "EFID.CA": "Edita Food Industries",
    "HRHO.CA": "EFG Holding",
    "JUFO.CA": "Juhayna Food Industries",
    "BTFH.CA": "Beltone Financial Holding",
    "RAYA.CA": "Raya Holding",
    "GBCO.CA": "GB Auto",
    "HELI.CA": "Heliopolis Housing",
    "ARCC.CA": "Arabian Cement Company",
    "MCQE.CA": "Misr Cement (Qena)",
    "ORWE.CA": "Oriental Weavers",
    "ISPH.CA": "Ibnsina Pharma",
    "RMDA.CA": "Rameda Pharmaceutical",
    "OIH.CA":  "Orascom Investment Holding",
    "CCAP.CA": "Qalaa Holdings",
}

# ── Signal vocabulary ─────────────────────────────────────────────────────────

SIGNAL_LABELS = {
    "INSTITUTIONAL BUY": "Constitutional BUY",
    "VERY STRONG BUY":   "High Conviction BUY",
    "STRONG BUY":        "Constitutional BUY",
    "BUY":               "Constitutional BUY",
    "WAIT":              "Watch — Monitoring",
    "SKIP":              "Not In Scope",
    "NEUTRAL":           "Neutral",
    "SELL":              "Reduce",
    "STRONG SELL":       "Exit Signal",
}

SIGNAL_EMOJI = {
    "INSTITUTIONAL BUY": "🟣",
    "VERY STRONG BUY":   "🟢",
    "STRONG BUY":        "🟢",
    "BUY":               "🟩",
    "WAIT":              "🔵",
    "NEUTRAL":           "⚪",
    "SELL":              "🔴",
    "STRONG SELL":       "🔴",
}

# Tier labels replacing "A-TIER / B-TIER"
TIER_LABELS = {
    1: "Premier Opportunities",
    2: "Monitored Opportunities",
}

# Portfolio category vocabulary
CATEGORY_LABELS = {
    "KEEP":                  "Portfolio Core",
    "KEEP_EVOLVED":          "Materially Appreciated",
    "HIGH_CONVICTION_BUY":   "High Conviction BUY",
    "BUY_WITH_AWARENESS":    "Buy With Diversification Awareness",
    "FUTURE_PRIORITY":       "Future Priority",
    "WATCH":                 "Watch",
    "BUY_RESERVE":           "Reserve Opportunity",
}

# BQ action vocabulary
BQ_LABELS = {
    "REVIEW EXIT": "Review Position",
    "MONITOR":     "Monitor Closely",
    "QUALITY":     "Quality Confirmed",
}

# Score axis labels
SCORE_AXIS = {
    "smc":        "Signal Quality",
    "rank_score": "Rank Score",
    "expectancy": "Factor Expectancy",
    "r2":         "Signal Quality",
}

# Pattern intelligence
PATTERN_TIER = {
    "strong":   "High Confidence Setup",
    "moderate": "Moderate Confidence Setup",
    "weak":     "Low Confidence Setup",
    "poor":     "Insufficient History",
}

# Platform identity
PLATFORM_NAME        = "EGX Constitutional Morning Brief"
PLATFORM_SHORT       = "EGX Constitutional"
EMAIL_SUBJECT_PREFIX = "EGX Constitutional Morning Brief"
FOOTER_TEXT          = "EGX Constitutional Investment Platform  ·  Research-Driven  ·  Constitutionally Governed"

# Decision driver vocabulary
DECISION_DRIVER = {
    "buy":  "Discount zone confirmed. Constitutional entry criteria met.",
    "wait": "Discount zone active. Monitoring for full entry confirmation.",
    "skip": "Above equilibrium — premium zone. Constitutional setup not active.",
}

# Data freshness
FRESHNESS_LABELS = {
    True:  "Current",
    False: "Prior Session",
}

# Empty-day message
NO_SETUPS_MESSAGE = (
    "No constitutional entry setups reached monitoring threshold today.\n"
    "Portfolio positions continue under constitutional management."
)

# Section headers
SECTION_HEADERS = {
    "header":          "EGX Constitutional Morning Brief",
    "opportunities":   "Today's Opportunities",
    "portfolio":       "Current Portfolio",
    "open_positions":  "Portfolio Positions — Constitutional Targets",
    "research":        "Research Insight",
    "watch":           "Monitoring List",
    "score_breakdown": "Factor Contribution",
    "entry_zones":     "Entry Strategy — Averaging Plan",
    "pattern":         "Pattern Intelligence — Historical Context",
    "ranking":         "Ranked Opportunities",
}


def translate_signal(raw_signal: str) -> str:
    """Return constitutional vocabulary for a raw signal string."""
    return SIGNAL_LABELS.get(raw_signal.upper(), raw_signal)


def signal_emoji(raw_signal: str) -> str:
    return SIGNAL_EMOJI.get(raw_signal.upper(), "🔵")


def translate_bq_action(raw_action: str) -> str:
    for key, val in BQ_LABELS.items():
        if key in raw_action:
            return val
    return raw_action


def translate_category(raw_cat: str) -> str:
    return CATEGORY_LABELS.get(raw_cat, raw_cat.replace("_", " ").title())


# ── Telegram structural strings ───────────────────────────────────────────────

TG_HEADER              = "📋 *EGX Constitutional Morning Brief*"
TG_POSITIONS_HEADER    = "📂 *Portfolio Positions  ({n})*"
TG_SECTION_SEP         = "━━━━━━━━━━━━━━━━━━━━━"
TG_REALTIME_HEADER     = "🚨 *Real-Time Alert*\n━━━━━━━━━━━━━━━━━━━━━━━"
TG_CHANGE_HEADER       = "🚨 *Signal Change — BUY Triggered*\n━━━━━━━━━━━━━━━━━━━━━"
TG_RESEARCH_HEADER     = "🔬 *Research Tracking — Pre-Confirmation*  _(not for entry)_"
TG_IN_PORTFOLIO        = "  🔵 _In Portfolio_"
TG_OPEN_POSITION_ICON  = "📌"
TG_SIGNAL_ICON         = "📈"

# ── Email structural strings ──────────────────────────────────────────────────

EMAIL_HEADER_TITLE     = "EGX Constitutional Morning Brief"
EMAIL_HEADER_BG        = "#1a3a5c"
EMAIL_HEADER_FG        = "#ffffff"
EMAIL_HEADER_SUBTITLE  = "#8fb8d8"
EMAIL_FOOTER_TEXT      = "EGX Constitutional Investment Platform &nbsp;·&nbsp; Research-Driven &nbsp;·&nbsp; Constitutionally Governed"

# Column headers
COL_SIGNAL_QUALITY     = "Signal Quality"
COL_RANK_SCORE         = "Rank Score / Signal Quality"
COL_FACTOR_EXP         = "Factor Expectancy"
COL_ENTRY_STRATEGY     = "ENTRY STRATEGY — AVERAGING PLAN"
COL_PATTERN_INTEL      = "PATTERN INTELLIGENCE — HISTORICAL CONTEXT"
COL_FACTOR_CONTRIB     = "Factor Contribution"

# Tier row labels
TIER_PREMIER           = "PREMIER"
TIER_MONITOR           = "MONITOR"

# ── Dashboard structural strings ──────────────────────────────────────────────

DASH_TITLE             = "EGX Constitutional Investment Platform"
DASH_SUBTITLE          = "Research-Driven · Constitutionally Governed · 27-Symbol Universe · Live State"
DASH_FOOTER            = "EGX Constitutional Investment Platform · Built {ts} · Research-Driven · Constitutionally Governed"

# ── Heatmap identity ──────────────────────────────────────────────────────────

HEATMAP_TITLE          = "EGX Constitutional — Signal Score Heatmap"
HEATMAP_BADGE          = "EGX Constitutional · Cairo Time"
HEATMAP_SCORE_LABEL    = "Signal Quality Score"
