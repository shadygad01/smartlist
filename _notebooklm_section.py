"""
Standalone module: build_notebooklm_section()
Imported by dashboard.py to avoid nested f-string syntax issues.

Tab purpose: SmartList Learning Engine — discover, validate, remember,
and promote knowledge that can improve future SmartList decisions.

Every section must answer: "What decision does this improve?"
"""
import json


def build_notebooklm_section(
    data: dict,
    BG1: str, BG2: str, BOR: str, FG: str, DIM: str,
    G: str, R: str, A: str, B: str,
    _section_header,
    _box,
    _ts,
) -> str:
    # ── correct key names from get_discovery_data() ─────────────────────────
    all_assets    = data.get("all_assets", [])
    lessons       = data.get("lessons", [])
    log_entries   = data.get("log_entries", [])
    inbox         = data.get("inbox", [])
    shadow_log    = data.get("shadow_log", {})   # dict: asset_id → [rows]
    total_signals = data.get("total_signals", 0)
    val_history   = data.get("val_history", {})  # dict: asset_id → [rows]

    STATUS_COLOR = {
        "Emerging":           B,
        "Validating":         A,
        "LearningCandidate":  A,
        "PromotionCandidate": G,
        "ShadowProduction":   G,
        "ProductionReady":    G,
        "Promoted":           G,
        "Rejected":           R,
        "Archived":           DIM,
    }
    TERMINAL = {"Promoted", "Rejected", "Archived"}

    NOVELTY_COLOR = {
        "NewAlpha":       G,
        "AlphaAmplifier": A,
        "Duplicate":      DIM,
        "Repackaged":     DIM,
        "Unknown":        DIM,
    }
    IMPACT_COLOR = {"High": G, "Medium": A, "Low": DIM}

    # ── promotion target → plain-language decision impact ────────────────────
    TARGET_DECISION = {
        "RankingEnhancement":      "Improves ranking score for qualifying signals",
        "ConfidenceBooster":       "Increases confidence in top-ranked signals",
        "EarlyReversalCandidate":  "Improves exit timing — hold shorter or longer",
        "ScannerFilter":           "Filters out low-probability setups earlier",
    }

    # ── group assets by stage ────────────────────────────────────────────────
    active          = [a for a in all_assets if a["status"] not in TERMINAL]
    emerging        = [a for a in active if a["status"] == "Emerging"]
    validating      = [a for a in active if a["status"] in ("Validating", "LearningCandidate")]
    promo_queue     = [a for a in active if a["status"] == "PromotionCandidate"]
    shadow_assets   = [a for a in active if a["status"] in ("ShadowProduction", "ProductionReady")]
    promoted        = [a for a in all_assets if a["status"] == "Promoted"]
    rejected        = [a for a in all_assets if a["status"] in ("Rejected", "Archived")]

    def _status_badge(status: str) -> str:
        col = STATUS_COLOR.get(status, DIM)
        return (
            '<span style="background:' + col + '22;color:' + col
            + ';border:1px solid ' + col + ';border-radius:3px;'
            'padding:1px 6px;font-size:11px;white-space:nowrap">'
            + status + "</span>"
        )

    def _novelty_badge(novelty: str) -> str:
        col = NOVELTY_COLOR.get(novelty, DIM)
        return (
            '<span style="color:' + col + ';font-size:11px">[' + novelty + "]</span>"
        )

    def _lift_str(val, suffix="pp") -> str:
        if val is None:
            return '<span style="color:' + DIM + '">—</span>'
        col = G if float(val) >= 0 else R
        sign = "+" if float(val) >= 0 else ""
        return '<span style="color:' + col + '">' + sign + str(round(float(val), 1)) + suffix + "</span>"

    def _n_validations(asset_id: str) -> int:
        return len(val_history.get(asset_id, []))

    def _promotion_readiness(a: dict) -> str:
        """Returns a plain-text readiness label based on evidence."""
        lift = a.get("mfe_lift_pp")
        n    = a.get("n_signals") or 0
        status = a.get("status", "")
        if status in ("PromotionCandidate", "ProductionReady", "Promoted"):
            return "Ready for human review"
        if lift is None:
            return "No evidence yet"
        if n < 30:
            return "Insufficient data (n<30)"
        if abs(lift) >= 3.0:
            return "Strong signal — needs formal validation"
        if abs(lift) >= 1.5:
            return "Marginal — needs more data"
        return "Weak signal — monitor"

    def _active_asset_row(a: dict) -> str:
        status  = a.get("status", "")
        novelty = a.get("novelty_class", "Unknown")
        col     = STATUS_COLOR.get(status, DIM)
        target  = a.get("promotion_target") or ""
        decision = TARGET_DECISION.get(target, "—")
        n_val    = _n_validations(a["id"])

        return (
            "<tr>"
            '<td style="color:' + FG + ';font-weight:bold;padding:5px 8px">'
            + a.get("name", "") + " " + _novelty_badge(novelty) + "</td>"
            '<td style="padding:5px 8px">' + _status_badge(status) + "</td>"
            '<td style="padding:5px 8px;text-align:right">' + _lift_str(a.get("mfe_lift_pp")) + "</td>"
            '<td style="color:' + B + ';font-size:11px;padding:5px 8px">' + target + "</td>"
            '<td style="color:' + DIM + ';font-size:11px;padding:5px 8px">' + decision + "</td>"
            '<td style="color:' + DIM + ';font-size:11px;text-align:center;padding:5px 8px">' + str(n_val) + "</td>"
            "</tr>"
        )

    def _active_asset_card(a: dict) -> str:
        status  = a.get("status", "")
        col     = STATUS_COLOR.get(status, DIM)
        novelty = a.get("novelty_class", "Unknown")
        ncol    = NOVELTY_COLOR.get(novelty, DIM)
        target  = a.get("promotion_target") or ""
        decision_impact = TARGET_DECISION.get(target, "Not yet determined")
        readiness = _promotion_readiness(a)
        n_val     = _n_validations(a["id"])
        lift      = a.get("mfe_lift_pp")
        corr      = a.get("corr_mfe_40d")
        inc_r2    = a.get("incremental_r2")
        n_sigs    = a.get("n_signals") or 0
        hypothesis = a.get("hypothesis") or "—"

        # parse evidence JSON for n and p-value
        ev_p = None
        ev_str = ""
        try:
            ev = json.loads(a.get("evidence") or "{}")
            ev_p = ev.get("p_value")
            ev_str = (
                "n_fired=" + str(ev.get("n_yes") or ev.get("n_sector") or ev.get("n_short") or ev.get("n_fast") or "")
                + "  p=" + str(ev_p or "—")
            )
        except Exception:
            pass

        card = (
            '<div style="border:1px solid ' + col + ';border-radius:6px;padding:14px;'
            'margin-bottom:14px;background:' + BG2 + '">'
            # Header
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
            '<span style="color:' + col + ';font-weight:bold;font-size:14px">' + a.get("name", "") + "</span>"
            + _status_badge(status)
            + '<span style="color:' + ncol + ';font-size:11px">' + novelty + "</span>"
        )
        if target:
            card += '<span style="color:' + B + ';font-size:11px;margin-left:auto">→ ' + target + "</span>"
        card += "</div>"

        # Decision Impact — the primary question
        card += (
            '<div style="background:' + BG1 + '44;border-left:3px solid ' + col
            + ';border-radius:0 4px 4px 0;padding:8px 12px;margin-bottom:10px">'
            '<div style="color:' + DIM + ';font-size:10px;text-transform:uppercase;letter-spacing:1px">DECISION IMPACT</div>'
            '<div style="color:' + FG + ';font-size:13px;font-weight:bold;margin-top:2px">' + decision_impact + "</div>"
            '<div style="color:' + A + ';font-size:11px;margin-top:3px">Readiness: ' + readiness + "</div>"
            "</div>"
        )

        # Stats row
        card += (
            '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:6px;margin-bottom:10px">'
        )
        for label, val_str in [
            ("MFE LIFT", _lift_str(lift) if lift is not None else '<span style="color:' + DIM + '">—</span>'),
            ("SIGNALS", '<span style="color:' + FG + '">' + str(n_sigs) + "</span>"),
            ("VALIDATIONS", '<span style="color:' + FG + '">' + str(n_val) + "</span>"),
            ("INC R²", '<span style="color:' + FG + '">' + (str(round(inc_r2, 4)) if inc_r2 is not None else "—") + "</span>"),
        ]:
            card += (
                '<div style="background:' + BG1 + ';border-radius:4px;padding:6px;text-align:center">'
                '<div style="color:' + DIM + ';font-size:10px">' + label + "</div>"
                '<div style="font-size:12px;font-weight:bold">' + val_str + "</div></div>"
            )
        card += "</div>"

        # Hypothesis
        card += (
            '<div style="margin-bottom:6px">'
            '<span style="color:' + DIM + ';font-size:10px;text-transform:uppercase">Hypothesis: </span>'
            '<span style="color:' + FG + ';font-size:12px">' + hypothesis[:300] + "</span></div>"
        )

        # Evidence summary
        if ev_str.strip() not in ("n_fired=  p=—", ""):
            card += (
                '<div style="margin-bottom:6px;color:' + DIM + ';font-size:11px">'
                "Evidence: " + ev_str + "</div>"
            )

        card += "</div>"
        return card

    # ────────────────────────────────────────────────────────────────────────────
    # BUILD HTML
    # ────────────────────────────────────────────────────────────────────────────
    html = _section_header("🧠 SmartList Learning Engine", "Discover · Validate · Promote · Improve Decisions")

    # ── Section 1: What is being learned right now ───────────────────────────
    counts_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px">'
    )
    stages = [
        ("Emerging",          len(emerging),      B,   "Candidates under observation"),
        ("Under Validation",  len(validating),    A,   "Being statistically tested"),
        ("Promotion Queue",   len(promo_queue),   G,   "Ready for human review"),
        ("In Shadow",         len(shadow_assets), G,   "Measuring live lift"),
        ("Promoted",          len(promoted),      G,   "Knowledge acting on decisions"),
        ("Archived",          len(rejected),      DIM, "Disproven or duplicate"),
    ]
    for label, count, col, tooltip in stages:
        counts_html += (
            '<div style="background:' + BG2 + ';border:1px solid ' + BOR
            + ';border-radius:6px;padding:10px 16px;text-align:center;min-width:120px">'
            '<div style="color:' + col + ';font-size:22px;font-weight:bold">' + str(count) + "</div>"
            '<div style="color:' + FG + ';font-size:11px;font-weight:bold">' + label + "</div>"
            '<div style="color:' + DIM + ';font-size:10px;margin-top:2px">' + tooltip + "</div>"
            "</div>"
        )
    counts_html += "</div>"
    counts_html += (
        '<div style="color:' + DIM + ';font-size:11px;margin-top:6px">'
        "Learning from " + str(total_signals) + " production signals  ·  "
        "Promotion = human review only — knowledge never auto-deploys"
        "</div>"
    )
    html += _box("Learning Status", counts_html)

    # ── Section 2: Active Knowledge Assets ──────────────────────────────────
    if active:
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px">'
            "<thead><tr>"
            '<th style="color:' + DIM + ';text-align:left;padding:5px 8px;border-bottom:1px solid ' + BOR + '">Knowledge Asset</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:5px 8px;border-bottom:1px solid ' + BOR + '">Stage</th>'
            '<th style="color:' + DIM + ';text-align:right;padding:5px 8px;border-bottom:1px solid ' + BOR + '">MFE Lift</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:5px 8px;border-bottom:1px solid ' + BOR + '">Promotion Target</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:5px 8px;border-bottom:1px solid ' + BOR + '">Decision Impact</th>'
            '<th style="color:' + DIM + ';text-align:center;padding:5px 8px;border-bottom:1px solid ' + BOR + '">Validations</th>'
            "</tr></thead><tbody>"
        )
        for a in active:
            table += _active_asset_row(a)
        table += "</tbody></table>"
        html += _box("Active Knowledge Assets", table)

        for a in active:
            html += _active_asset_card(a)
    else:
        html += _box(
            "Active Knowledge Assets",
            '<p style="color:' + DIM + '">No active assets. Run: python discovery_engine.py discover</p>',
        )

    # ── Section 3: Promotion Queue ───────────────────────────────────────────
    if promo_queue:
        pq_html = (
            '<div style="color:' + A + ';font-size:12px;margin-bottom:10px;font-style:italic">'
            "These assets have sufficient evidence to improve a SmartList decision. "
            "Human review required before any change is made to production logic."
            "</div>"
        )
        for a in promo_queue:
            target   = a.get("promotion_target") or "—"
            lift     = a.get("mfe_lift_pp")
            decision = TARGET_DECISION.get(target, "—")
            n_val    = _n_validations(a["id"])
            pq_html += (
                '<div style="border:2px solid ' + G + ';border-radius:6px;padding:12px 16px;margin-bottom:10px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                '<span style="color:' + G + ';font-weight:bold;font-size:14px">' + a.get("name", "") + "</span>"
                + _status_badge("PromotionCandidate")
                + "</div>"
                '<div style="color:' + FG + ';font-size:13px;font-weight:bold;margin-bottom:4px">'
                "→ " + target + ": " + decision
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-bottom:6px">'
                + (a.get("hypothesis") or "—")[:200] + "</div>"
                '<div style="color:' + DIM + ';font-size:11px">'
                "MFE lift: " + (_lift_str(lift) if lift is not None else "—")
                + "  |  Validations: " + str(n_val)
                + "</div></div>"
            )
        html += _box("Promotion Queue", pq_html)
    else:
        html += _box(
            "Promotion Queue",
            '<p style="color:' + DIM + ';font-size:12px">'
            "No assets ready for promotion. Assets reach this stage after statistical "
            "validation confirms lift ≥3pp with p&lt;0.05."
            "</p>",
        )

    # ── Section 4: Shadow Production ────────────────────────────────────────
    if shadow_assets:
        sh_html = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
            "Shadow production: pattern runs alongside SmartList — zero impact on live decisions. "
            "Lift measured on historical signals that match the firing condition."
            "</div>"
        )
        for a in shadow_assets:
            shadow_rows = shadow_log.get(a["id"], [])
            latest = shadow_rows[-1] if shadow_rows else None
            sh_lift   = latest.get("mfe_lift_pp") if latest else None
            n_fired   = latest.get("n_fired") if latest else None
            n_not     = latest.get("n_not_fired") if latest else None
            sh_html += (
                '<div style="border:1px solid ' + G + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                '<span style="color:' + G + ';font-weight:bold">' + a.get("name", "") + "</span>"
                + _status_badge(a.get("status", "")) + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-bottom:4px">'
                "Decision target: " + TARGET_DECISION.get(a.get("promotion_target") or "", "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px">'
                "Shadow lift: " + (_lift_str(sh_lift) if sh_lift is not None else "not yet measured")
                + ("  |  Fired: " + str(n_fired) + " signals  |  Control: " + str(n_not) + " signals" if n_fired else "")
                + "</div></div>"
            )
        html += _box("Shadow Production", sh_html)

    # ── Section 5: Promoted Knowledge ───────────────────────────────────────
    if promoted:
        pr_html = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
            "Promoted knowledge is ready for integration into SmartList logic by a developer."
            "</div>"
        )
        for a in promoted:
            target   = a.get("promotion_target") or "—"
            decision = TARGET_DECISION.get(target, "—")
            pr_html += (
                '<div style="border-left:3px solid ' + G + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="color:' + G + ';font-weight:bold">' + a.get("name", "") + "</div>"
                '<div style="color:' + FG + ';font-size:13px;margin-top:2px">' + decision + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:4px">' + (a.get("hypothesis") or "—")[:200] + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:4px">'
                "Target: " + target
                + ("  |  Promoted: " + (a.get("promoted_at") or "")[:10] if a.get("promoted_at") else "")
                + "</div></div>"
            )
        html += _box("Promoted Knowledge", pr_html)

    # ── Section 6: Rejected / Archived ──────────────────────────────────────
    if rejected:
        rej_html = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:8px">'
            "Archived to prevent re-discovery of disproven or duplicate patterns."
            "</div>"
        )
        for a in rejected:
            rej_html += (
                '<div style="border-left:2px solid ' + DIM + ';padding:6px 10px;margin-bottom:6px">'
                '<div style="color:' + DIM + '">' + a.get("name", "") + " [" + a.get("novelty_class", "") + "]</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:2px">' + (a.get("hypothesis") or "—")[:150] + "</div>"
                "</div>"
            )
        html += _box("Archived Knowledge", rej_html)

    # ── Section 7: Lessons Learned ───────────────────────────────────────────
    if lessons:
        lessons_html = ""
        for lesson in lessons:
            cat    = lesson.get("category") or "General"
            impact = lesson.get("impact") or "Medium"
            icol   = IMPACT_COLOR.get(impact, DIM)
            logged = (lesson.get("logged_at") or "")[:10]
            lessons_html += (
                '<div style="border-left:3px solid ' + icol + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
                '<span style="color:' + icol + ';font-size:11px;border:1px solid ' + icol + ';border-radius:3px;padding:1px 5px">'
                + impact + "</span>"
                '<span style="color:' + DIM + ';font-size:11px">[' + cat + "]</span>"
                + ('<span style="color:' + DIM + ';font-size:10px;margin-left:auto">' + logged + "</span>" if logged else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px">' + (lesson.get("lesson") or "") + "</div>"
                "</div>"
            )
        html += _box("Lessons Learned", lessons_html)
    else:
        html += _box(
            "Lessons Learned",
            '<p style="color:' + DIM + ';font-size:12px">'
            "Record what SmartList has learned from this research. "
            'Add via: python discovery_engine.py lesson "text" [Timing|Confidence|Structure|Volume|Context] [High|Medium|Low]'
            "</p>",
        )

    # ── Section 8: Recent Knowledge Events (collapsed) ──────────────────────
    meaningful_events = [
        e for e in log_entries
        if e.get("event_type") in ("StatusChange", "Promoted", "Rejected", "Validated", "Lesson")
    ][:10]

    if meaningful_events:
        ev_html = '<table style="width:100%;border-collapse:collapse;font-size:11px"><tbody>'
        for e in meaningful_events:
            ts      = (e.get("logged_at") or "")[:10]
            name    = e.get("asset_name") or "—"
            etype   = e.get("event_type") or ""
            summary = (e.get("summary") or "")[:140]
            etype_col = G if etype in ("Promoted", "Validated") else (R if etype == "Rejected" else A)
            ev_html += (
                "<tr>"
                '<td style="color:' + DIM + ';padding:4px 8px;white-space:nowrap;vertical-align:top">' + ts + "</td>"
                '<td style="color:' + etype_col + ';padding:4px 8px;white-space:nowrap;vertical-align:top">' + etype + "</td>"
                '<td style="color:' + FG + ';padding:4px 8px;vertical-align:top">'
                + ('<b>' + name + '</b> — ' if name != "—" else "") + summary + "</td>"
                "</tr>"
            )
        ev_html += "</tbody></table>"
        html += _box("Recent Knowledge Events", ev_html)

    # ── Section 9: External Knowledge Intake ────────────────────────────────
    intake_html = (
        '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
        "Submit hypotheses from external research (NotebookLM, manual analysis, sector reports) "
        "for validation against SmartList production data."
        "</div>"
    )
    if inbox:
        for item in inbox:
            status_text = item.get("status") or "Pending"
            scol = G if status_text in ("Created",) else A
            intake_html += (
                '<div style="border:1px solid ' + scol + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                '<span style="color:' + FG + ';font-weight:bold">' + (item.get("title") or "Untitled") + "</span>"
                '<span style="color:' + scol + ';font-size:11px;margin-left:auto">' + status_text + "</span>"
                + ('<span style="color:' + DIM + ';font-size:10px">' + (item.get("submitted_at") or "")[:10] + "</span>" if item.get("submitted_at") else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px">' + (item.get("content") or "")[:300] + "</div>"
                + ('<div style="color:' + G + ';font-size:11px;margin-top:4px">→ Knowledge asset created</div>' if item.get("asset_id") else "")
                + "</div>"
            )
    else:
        intake_html += (
            '<p style="color:' + DIM + ';font-size:12px">'
            "No external hypotheses submitted yet. "
            "Submit via: python discovery_engine.py add_notebooklm &quot;hypothesis title&quot; &quot;description&quot;"
            "</p>"
        )
    html += _box("External Knowledge Intake", intake_html)

    return html
