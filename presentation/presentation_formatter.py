"""
Constitutional formatters — Telegram, Email, Dashboard.

All three consume the same DailyBriefModel.
No score computation. No trading logic. Presentation only.
"""

from .presentation_model import (
    DailyBriefModel, SignalPresentation, PositionPresentation,
    PortfolioHealthPresentation,
)
from .presentation_language import (
    PLATFORM_NAME, PLATFORM_SHORT, EMAIL_SUBJECT_PREFIX, FOOTER_TEXT,
    NO_SETUPS_MESSAGE, SECTION_HEADERS, translate_bq_action, translate_signal,
    signal_emoji,
)
from .presentation_theme import (
    EmailTheme as ET, DashTheme as DT, TG_DIVIDER, TG_SECTION_DIV,
    signal_badge_colors, stars,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════

class TelegramFormatter:
    """Formats DailyBriefModel into constitutional Telegram message(s)."""

    def format(self, brief: DailyBriefModel) -> list[str]:
        """Return list of message chunks (≤4000 chars each)."""
        lines = self._build_lines(brief)
        return self._chunk("\n".join(lines))

    def _build_lines(self, brief: DailyBriefModel) -> list[str]:
        lines = [
            f"📋 *{PLATFORM_NAME}*",
            f"*{brief.date_str}*",
            TG_SECTION_DIV,
        ]

        if brief.no_setups:
            lines += [
                "",
                NO_SETUPS_MESSAGE,
            ]
        else:
            lines += [
                f"_{brief.buy_count} constitutional entr{'y' if brief.buy_count == 1 else 'ies'}"
                f" · {brief.watch_count} monitoring_",
                "",
            ]

        # Open positions
        if brief.positions:
            lines += [TG_SECTION_DIV, f"📂 *Portfolio Positions  ({len(brief.positions)})*", ""]
            for p in brief.positions:
                lines += self._format_position(p)
            lines.append(TG_SECTION_DIV + "\n")

        # Signals
        for sig in brief.signals:
            lines += self._format_signal(sig)

        # Early buy research
        if brief.early_buy_signals:
            lines += [
                TG_SECTION_DIV,
                f"🔬 *Research Tracking — Pre-Confirmation*  _(observation only)_",
                f"_{len(brief.early_buy_signals)} signal(s) — partial discount, monitoring for entry criteria_",
                "",
            ]
            for sig in brief.early_buy_signals:
                lines += self._format_early_buy(sig)
            lines.append(TG_SECTION_DIV)

        return lines

    def _format_signal(self, sig: SignalPresentation) -> list[str]:
        portfolio_tag = "  🔵 _In Portfolio_" if sig.is_in_portfolio else ""
        quality_line  = f"   Signal Quality  *{sig.signal_quality_stars}* {sig.signal_quality_label}" if sig.signal_quality_stars else ""

        lines = [
            TG_DIVIDER,
            f"{sig.signal_emoji} *{sig.name}*  `{sig.symbol}`{portfolio_tag}",
            f"   Signal         *{sig.signal_label}*",
        ]
        if quality_line:
            lines.append(quality_line)
        lines.append(f"   Price          *{sig.price} EGP*")

        if sig.is_buy:
            upside_str = f"  (+{sig.upside_pct:.1f}%)" if sig.upside_pct is not None else ""
            lines.append(f"   Target         *{sig.target:.2f} EGP*{upside_str}")

            if sig.is_in_portfolio:
                lines.append("   💼 _Monitoring open position_")
            elif sig.position_size_pct is not None:
                lines.append(
                    f"   Position Size  *{sig.position_size_pct:.1f}%* of portfolio"
                    f"  ({sig.position_size_tier})"
                )

        if sig.pattern_score is not None and sig.pattern_effective is not None:
            lines.append(
                f"   Research       *{sig.pattern_label}*  |  Win Rate *{sig.pattern_win_rate*100:.0f}%*"
                f"  ({sig.pattern_cases} cases)"
            )

        if sig.bq_score is not None:
            lines.append(f"   Quality Check  *{sig.bq_score:.0f}/100*  {sig.bq_action}")

        data_label = "Current" if sig.is_fresh else "Prior Session"
        lines.append(f"   Data           {'✅' if sig.is_fresh else '⚠️'} {data_label}")
        lines.append("")
        return lines

    def _format_position(self, pos: PositionPresentation) -> list[str]:
        if pos.current_price is not None:
            pnl_str = (
                f"+{pos.pnl_pct:.1f}%" if (pos.pnl_pct or 0) >= 0
                else f"{pos.pnl_pct:.1f}%"
            )
            cur_str = f"{pos.current_price} EGP  ({pnl_str})"
        else:
            cur_str = "—"

        lines = [
            f"📌 *{pos.symbol}*  {pos.name}",
            f"   Entry   {pos.entry_price:.2f} EGP",
            f"   Now     {cur_str}",
            f"   Target  *{pos.target:.2f} EGP*",
        ]
        if pos.bq_score is not None:
            lines.append(f"   Quality  *{pos.bq_score:.0f}/100*  {pos.bq_action}")
        if pos.reinforced and pos.reinf_price:
            lines.append(f"   Re-entry {pos.reinf_price:.2f} EGP")
            if pos.avg_price:
                lines.append(f"   Avg      *{pos.avg_price:.2f} EGP*")
        lines.append("")
        return lines

    def _format_early_buy(self, sig: SignalPresentation) -> list[str]:
        return [
            TG_DIVIDER,
            f"🔬 *{sig.name}*  `{sig.symbol}`",
            f"   Score   *{sig.raw_score or sig.score}/100*",
            f"   Price   *{sig.price} EGP*",
            f"   _Tracking — no portfolio action_",
            "",
        ]

    @staticmethod
    def _chunk(text: str, max_len: int = 4000) -> list[str]:
        chunks, current = [], ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_len:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)
        return chunks


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════

class EmailFormatter:
    """Formats DailyBriefModel into an HTML email string."""

    def subject(self, brief: DailyBriefModel) -> str:
        suffix = f" — {brief.buy_count} Entr{'y' if brief.buy_count == 1 else 'ies'}" if brief.buy_count else ""
        return f"{EMAIL_SUBJECT_PREFIX} · {brief.date_str}{suffix}"

    def format(self, brief: DailyBriefModel, inner_html: str) -> str:
        """
        Wrap existing inner_html (from main.py build_report) with
        constitutional header and footer.
        The inner_html is produced by the existing engine — we wrap, not replace.
        """
        header = self._header(brief)
        footer = self._footer()
        return (
            f'<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
            f'<table width="680" cellpadding="0" cellspacing="0" border="0" align="center" '
            f'style="background:#ffffff;border:1px solid #d0d7e2;">'
            f'<tr><td style="padding:0 24px 24px 24px;">'
            f'{header}{inner_html}{footer}'
            f'</td></tr></table></body></html>'
        )

    def _header(self, brief: DailyBriefModel) -> str:
        summary = (
            f"{brief.buy_count} constitutional entr{'y' if brief.buy_count == 1 else 'ies'}"
            if brief.buy_count
            else "Portfolio management — no new entries today"
        )
        return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{ET.HEADER_BG};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:{ET.HEADER_FG};font-size:20px;
                font-weight:700;letter-spacing:0.3px;">{PLATFORM_NAME}</div>
    <div style="font-family:Arial,sans-serif;color:{ET.HEADER_SUBTITLE};font-size:12px;
                margin-top:6px;">{brief.date_str} &nbsp;·&nbsp; {summary}</div>
  </td></tr>
</table>"""

    def _footer(self) -> str:
        return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin-top:40px;border-top:1px solid {ET.BORDER_COLOR};">
  <tr><td align="center" style="padding:16px;font-family:Arial,sans-serif;
                                font-size:11px;color:#bbb;letter-spacing:0.4px;">
    {FOOTER_TEXT}
  </td></tr>
</table>"""

    def portfolio_health_block(self, health: PortfolioHealthPresentation) -> str:
        return f"""
<div style="background:#f4f8ff;border:1px solid #c8daf5;border-radius:6px;
            padding:16px 20px;margin:16px 0;">
  <div style="font-family:Arial,sans-serif;font-size:13px;font-weight:bold;
              color:{ET.SECTION_TITLE};margin-bottom:8px;">
    Portfolio Health &nbsp; {health.stars} &nbsp; {health.label}
  </div>
  <div style="font-family:Arial,sans-serif;font-size:12px;color:{ET.BODY_FG};
              line-height:1.6;">{health.narrative}</div>
</div>"""

    def signal_badge_html(self, label: str, score: float) -> str:
        tc, tbg, tbr = signal_badge_colors(score)
        return (
            f'<span style="display:inline-block;padding:4px 12px;border-radius:12px;'
            f'font-size:11px;font-weight:700;letter-spacing:0.3px;'
            f'background:{tbg};color:{tc};border:1px solid {tbr};">{label}</span>'
        )

    def ranking_header(self) -> str:
        return f"""
<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:bold;
            color:{ET.SECTION_TITLE};margin:20px 0 8px 0;letter-spacing:0.5px;">
  {SECTION_HEADERS['ranking']}
</div>"""

    def open_positions_header(self) -> str:
        return f"""
<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:bold;
            color:{ET.SECTION_TITLE};margin:20px 0 6px 0;letter-spacing:0.5px;">
  📊 {SECTION_HEADERS['open_positions']}
</div>"""


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════

class DashboardFormatter:
    """Constitutional vocabulary for Dashboard section headers."""

    SECTION_TITLES = {
        "alpha_status":        "Constitutional Engine Status",
        "bottom_pipeline":     "Signal Discovery Pipeline",
        "learning":            "Today's Research Insights",
        "current_research":    "Active Research",
        "alpha_snapshot":      "Today's Constitutional Signals",
        "knowledge_findings":  "Knowledge Base Highlights",
        "alpha_performance":   "Constitutional Performance",
        "changes":             "Changes Since Yesterday",
        "deployment":          "Deployment History",
        "system_health":       "System Health",
        "portfolio":           "Portfolio Intelligence",
        "research_lab":        "Constitutional Research Lab",
    }

    def section_header(self, key: str, icon: str = "") -> str:
        title = self.SECTION_TITLES.get(key, key.replace("_", " ").title())
        border = DT.BOR
        color  = DT.B
        return (
            f'<div style="color:{color};font-size:1em;font-weight:700;'
            f'letter-spacing:0.05em;margin:0 0 12px;padding-bottom:8px;'
            f'border-bottom:1px solid {border}">'
            f'{icon} {title}</div>'
        )

    def platform_title(self) -> str:
        return f"EGX Constitutional Investment Platform"

    def platform_subtitle(self) -> str:
        return "Research-Driven · Constitutionally Governed · 27-Symbol Universe"
