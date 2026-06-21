"""
Presentation model — typed containers for all data passed to formatters.

Production code produces raw dicts/scores. The model layer translates
them into presentation-ready structures before any formatter touches them.
No trading logic lives here.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalPresentation:
    """One scanner signal, translated for display."""
    symbol:             str
    name:               str
    sector:             str
    price:              float
    raw_signal:         str                 # original: "BUY", "WAIT", etc.
    signal_label:       str                 # constitutional: "Constitutional BUY"
    signal_emoji:       str
    score:              int                 # SMC score (unchanged)
    rank_score:         float               # 0.6*expectancy + 0.4*score
    factor_exp_score:   float
    target:             float
    upside_pct:         Optional[float]     # (target-price)/price*100
    is_fresh:           bool
    is_buy:             bool
    is_in_portfolio:    bool

    signal_quality_stars:  str = ""         # ★★★★☆
    signal_quality_label:  str = ""         # Exceptional / Strong / etc.

    pattern_score:      Optional[float] = None
    pattern_effective:  Optional[float] = None   # /5
    pattern_win_rate:   Optional[float] = None
    pattern_avg_gain:   Optional[float] = None
    pattern_cases:      Optional[int]   = None
    pattern_label:      str = ""

    bq_score:           Optional[float] = None
    bq_action:          str = ""

    ctx_label:          str = ""
    raw_score:          Optional[int] = None
    is_early_buy:       bool = False

    position_size_pct:  Optional[float] = None
    position_size_tier: str = ""


@dataclass
class PositionPresentation:
    """One open portfolio position for display."""
    symbol:         str
    name:           str
    entry_price:    float
    current_price:  Optional[float]
    target:         float
    pnl_pct:        Optional[float]
    entry_date:     str
    entry_score:    float
    reinforced:     bool = False
    reinf_price:    Optional[float] = None
    avg_price:      Optional[float] = None
    bq_score:       Optional[float] = None
    bq_action:      str = ""


@dataclass
class PortfolioHealthPresentation:
    stars:          str
    label:          str
    narrative:      str
    observations:   list[str] = field(default_factory=list)
    held_count:     int = 0
    sector_alloc:   dict = field(default_factory=dict)


@dataclass
class DailyBriefModel:
    """Complete data model for one daily scan presentation."""
    date_str:           str
    scan_count:         int
    buy_count:          int
    watch_count:        int
    no_setups:          bool

    signals:            list[SignalPresentation] = field(default_factory=list)
    positions:          list[PositionPresentation] = field(default_factory=list)
    portfolio_health:   Optional[PortfolioHealthPresentation] = None

    early_buy_signals:  list[SignalPresentation] = field(default_factory=list)
    research_insight:   str = ""
