"""
Standalone module: build_notebooklm_section()
Imported by dashboard.py to avoid nested f-string syntax issues.

Tab purpose: SmartList Learning Engine — discover, validate, remember,
and promote knowledge that can improve future SmartList decisions.

Purity rule: every section must answer "What decision does this improve?"
             If the answer is unclear the section is not shown.
"""
import json


# Promotion criteria — used in asset cards and stage guidance
PROMO_CRITERIA = {
    "LearningCandidate":  "p<0.05, lift>=3pp, n>=50 → needs incremental R² validation",
    "PromotionCandidate": "incremental R²>0 confirmed → ready for human review",
    "ShadowProduction":   "14 days shadow lift>=3pp → advance to ProductionReady",
    "ProductionReady":    "Human review complete → integrate into production logic",
}

PROMOTION_PATH = {
    "RankingEnhancement":     "→ scoring.py: sector-aware weight added to r1-r8 sum",
    "ConfidenceBooster":      "→ confidence_score(): multiplier applied to high-conviction signals",
    "EarlyReversalCandidate": "→ exit_logic.py: early exit flag when pattern fires",
    "ScannerFilter":          "→ main.py: pre-filter discards signals when pattern absent",
}

MIN_N = {"Emerging": 0, "LearningCandidate": 50, "PromotionCandidate": 50,
         "ShadowProduction": 50, "ProductionReady": 50, "Promoted": 50}


def build_notebooklm_section(
    data: dict,
    BG1: str, BG2: str, BOR: str, FG: str, DIM: str,
    G: str, R: str, A: str, B: str,
    _section_header,
    _box,
    _ts,
) -> str:
    all_assets    = data.get("all_assets", [])
    lessons       = data.get("lessons", [])
    log_entries   = data.get("log_entries", [])
    inbox         = data.get("inbox", [])
    shadow_log    = data.get("shadow_log", {})
    total_signals = data.get("total_signals", 0)
    val_history   = data.get("val_history", {})

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

    TARGET_DECISION = {
        "RankingEnhancement":      "Improves ranking score for qualifying signals",
        "ConfidenceBooster":       "Increases confidence in top-ranked signals",
        "EarlyReversalCandidate":  "Improves exit timing",
        "ScannerFilter":           "Filters low-probability setups earlier",
    }

    # ── group assets ─────────────────────────────────────────────────────────
    active        = [a for a in all_assets if a["status"] not in TERMINAL]
    emerging      = [a for a in active if a["status"] == "Emerging"]
    learning      = [a for a in active if a["status"] in ("Validating", "LearningCandidate")]
    promo_queue   = [a for a in active if a["status"] == "PromotionCandidate"]
    shadow        = [a for a in active if a["status"] in ("ShadowProduction", "ProductionReady")]
    promoted      = [a for a in all_assets if a["status"] == "Promoted"]
    archived      = [a for a in all_assets if a["status"] in ("Rejected", "Archived")]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _badge(text: str, col: str) -> str:
        return (
            '<span style="background:' + col + '22;color:' + col
            + ';border:1px solid ' + col + ';border-radius:3px;'
            'padding:1px 6px;font-size:11px;white-space:nowrap">' + text + "</span>"
        )

    def _lift(val) -> str:
        if val is None:
            return '<span style="color:' + DIM + '">—</span>'
        f = float(val)
        col = G if f >= 0 else R
        return '<span style="color:' + col + '">' + ("+" if f >= 0 else "") + str(round(f, 1)) + "pp</span>"

    def _n_val(asset_id: str) -> int:
        return len(val_history.get(asset_id, []))

    def _ev(a: dict) -> dict:
        try:
            return json.loads(a.get("evidence") or "{}")
        except Exception:
            return {}

    def _next_step(a: dict) -> str:
        """What must happen for this asset to advance one stage."""
        status = a["status"]
        n      = a.get("n_signals") or 0
        target = a.get("promotion_target") or ""
        if status == "Emerging":
            if n < 50:
                return f"Accumulate more signals (currently n={n}, need n≥50)"
            return "Run: python discovery_engine.py validate " + a["id"]
        if status == "LearningCandidate":
            return "Run incremental R² validation to confirm independence from r1-r8, then promote to PromotionCandidate"
        if status == "PromotionCandidate":
            return "Human review: python discovery_engine.py shadow_promote " + a["id"]
        if status == "ShadowProduction":
            return "Run: python discovery_engine.py shadow — measure 14 days of live lift"
        if status == "ProductionReady":
            return "Developer: integrate into " + PROMOTION_PATH.get(target, "production logic")
        return "—"

    def _asset_card(a: dict, expanded: bool = True) -> str:
        status   = a["status"]
        col      = STATUS_COLOR.get(status, DIM)
        novelty  = a.get("novelty_class", "Unknown")
        target   = a.get("promotion_target") or ""
        decision = TARGET_DECISION.get(target, "Not yet determined")
        path     = PROMOTION_PATH.get(target, "—")
        nv       = _n_val(a["id"])
        lift     = a.get("mfe_lift_pp")
        n        = a.get("n_signals") or 0
        ev       = _ev(a)
        p_val    = ev.get("p_value")
        inc_r2   = a.get("incremental_r2")
        hyp      = (a.get("hypothesis") or "—")[:280]
        next_st  = _next_step(a)

        # promotion probability assessment
        if status in ("PromotionCandidate", "ProductionReady", "Promoted"):
            promo_prob = "High"
            promo_col  = G
        elif lift is not None and p_val is not None and lift >= 3.0 and p_val < 0.05 and n >= 50:
            promo_prob = "Medium — needs R² validation"
            promo_col  = A
        elif lift is not None and lift >= 2.0 and n >= 30:
            promo_prob = "Low — needs more evidence"
            promo_col  = A
        else:
            promo_prob = "Very low — insufficient data"
            promo_col  = DIM

        card = (
            '<div style="border:1px solid ' + col + ';border-radius:6px;padding:14px;margin-bottom:14px;background:' + BG2 + '">'
            # Title row
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px">'
            '<span style="color:' + col + ';font-weight:bold;font-size:14px">' + a.get("name", "") + "</span>"
            + _badge(status, col)
            + '<span style="color:' + NOVELTY_COLOR.get(novelty, DIM) + ';font-size:11px">' + novelty + "</span>"
        )
        if target:
            card += '<span style="color:' + B + ';font-size:11px;margin-left:auto">→ ' + target + "</span>"
        card += "</div>"

        # Decision Impact block — primary question
        card += (
            '<div style="background:' + BG1 + ';border-left:3px solid ' + col
            + ';border-radius:0 4px 4px 0;padding:8px 12px;margin-bottom:10px">'
            '<div style="color:' + DIM + ';font-size:10px;letter-spacing:1px;text-transform:uppercase">DECISION IMPACT</div>'
            '<div style="color:' + FG + ';font-size:13px;font-weight:bold;margin-top:2px">' + decision + "</div>"
            '<div style="color:' + DIM + ';font-size:11px;margin-top:3px">Integration path: ' + path + "</div>"
            "</div>"
        )

        # Evidence strip
        card += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px">'
        for label, val_html in [
            ("MFE LIFT",     _lift(lift)),
            ("N SIGNALS",    '<span style="color:' + (G if n >= 50 else A) + '">' + str(n) + "</span>"),
            ("p-VALUE",      '<span style="color:' + (G if p_val and p_val < 0.05 else A if p_val and p_val < 0.10 else DIM) + '">'
                             + (str(round(p_val, 3)) if p_val is not None else "—") + "</span>"),
            ("VALIDATIONS",  '<span style="color:' + FG + '">' + str(nv) + "</span>"),
        ]:
            card += (
                '<div style="background:' + BG1 + '88;border-radius:4px;padding:5px;text-align:center">'
                '<div style="color:' + DIM + ';font-size:10px">' + label + "</div>"
                '<div style="font-size:12px;font-weight:bold">' + val_html + "</div></div>"
            )
        card += "</div>"

        # Hypothesis
        card += (
            '<div style="margin-bottom:8px">'
            '<span style="color:' + DIM + ';font-size:10px;text-transform:uppercase">Hypothesis: </span>'
            '<span style="color:' + FG + ';font-size:12px">' + hyp + "</span></div>"
        )

        # Promotion readiness
        card += (
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
            '<span style="color:' + DIM + ';font-size:11px">Promotion probability: </span>'
            '<span style="color:' + promo_col + ';font-size:11px;font-weight:bold">' + promo_prob + "</span>"
            "</div>"
        )

        # Next step — actionable
        card += (
            '<div style="background:' + A + '15;border:1px solid ' + A + '44;border-radius:4px;padding:6px 10px">'
            '<span style="color:' + A + ';font-size:10px;text-transform:uppercase">NEXT STEP: </span>'
            '<span style="color:' + FG + ';font-size:11px">' + next_st + "</span>"
            "</div>"
        )

        card += "</div>"
        return card

    # ── BUILD HTML ───────────────────────────────────────────────────────────
    html = _section_header("🧠 SmartList Learning Engine", "Discover · Validate · Promote · Improve Decisions")

    # ── 1. LEARNING STATUS ───────────────────────────────────────────────────
    # Purpose: pipeline health at a glance — what stage is each piece of knowledge at?
    status_html = '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px">'
    stages = [
        ("Emerging",         len(emerging),    B,   "Under observation"),
        ("Learning",         len(learning),    A,   "Being validated"),
        ("Promotion Queue",  len(promo_queue), G,   "Ready for review"),
        ("Shadow",           len(shadow),      G,   "Measuring live lift"),
        ("Promoted",         len(promoted),    G,   "Acting on decisions"),
        ("Archived",         len(archived),    DIM, "Disproven / duplicate"),
    ]
    for label, count, col, tooltip in stages:
        status_html += (
            '<div style="background:' + BG2 + ';border:1px solid ' + BOR
            + ';border-radius:6px;padding:10px 16px;text-align:center;min-width:110px">'
            '<div style="color:' + col + ';font-size:22px;font-weight:bold">' + str(count) + "</div>"
            '<div style="color:' + FG + ';font-size:11px;font-weight:bold">' + label + "</div>"
            '<div style="color:' + DIM + ';font-size:10px;margin-top:2px">' + tooltip + "</div>"
            "</div>"
        )
    status_html += "</div>"
    status_html += (
        '<div style="color:' + DIM + ';font-size:11px">'
        + str(total_signals) + " production signals analysed  ·  "
        "Promotion = human review — knowledge never auto-deploys"
        "</div>"
    )
    html += _box("Learning Status", status_html)

    # ── 2. ACTIVE KNOWLEDGE ASSETS TABLE ────────────────────────────────────
    # Purpose: one-line view of everything in the pipeline with decision impact
    if active:
        tbl = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>'
            + "".join(
                '<th style="color:' + DIM + ';text-align:left;padding:5px 8px;border-bottom:1px solid ' + BOR + '">' + h + "</th>"
                for h in ["Asset", "Stage", "MFE Lift", "N", "p", "Decision Impact", "Next Step"]
            )
            + "</tr></thead><tbody>"
        )
        for a in active:
            ev   = _ev(a)
            p    = ev.get("p_value")
            n    = a.get("n_signals") or 0
            pcol = G if p and p < 0.05 else (A if p and p < 0.10 else DIM)
            ncol = G if n >= 50 else A
            scol = STATUS_COLOR.get(a["status"], DIM)
            tbl += (
                "<tr>"
                '<td style="color:' + FG + ';font-weight:bold;padding:5px 8px">' + a.get("name", "") + "</td>"
                '<td style="padding:5px 8px">' + _badge(a["status"], scol) + "</td>"
                '<td style="padding:5px 8px;text-align:right">' + _lift(a.get("mfe_lift_pp")) + "</td>"
                '<td style="color:' + ncol + ';padding:5px 8px;text-align:right">' + str(n) + "</td>"
                '<td style="color:' + pcol + ';padding:5px 8px;text-align:right">'
                + (str(round(p, 3)) if p is not None else "—") + "</td>"
                '<td style="color:' + B + ';font-size:11px;padding:5px 8px">'
                + TARGET_DECISION.get(a.get("promotion_target") or "", "—") + "</td>"
                '<td style="color:' + DIM + ';font-size:11px;padding:5px 8px">' + _next_step(a)[:80] + "</td>"
                "</tr>"
            )
        tbl += "</tbody></table>"
        html += _box("Active Knowledge Assets", tbl)
        for a in active:
            html += _asset_card(a)
    else:
        html += _box(
            "Active Knowledge Assets",
            '<p style="color:' + DIM + '">No active assets. Run: python discovery_engine.py discover</p>',
        )

    # ── 3. PROMOTION QUEUE ───────────────────────────────────────────────────
    # Purpose: surface knowledge ready for developer integration
    if promo_queue:
        pq = (
            '<div style="color:' + A + ';font-size:12px;margin-bottom:10px;font-style:italic">'
            "Sufficient evidence to improve a SmartList decision. "
            "Awaiting human review — no auto-deployment ever."
            "</div>"
        )
        for a in promo_queue:
            target = a.get("promotion_target") or "—"
            path   = PROMOTION_PATH.get(target, "—")
            pq += (
                '<div style="border:2px solid ' + G + ';border-radius:6px;padding:12px 16px;margin-bottom:10px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                '<span style="color:' + G + ';font-weight:bold;font-size:14px">' + a.get("name", "") + "</span>"
                + _badge("PromotionCandidate", G) + "</div>"
                '<div style="color:' + FG + ';font-size:13px;font-weight:bold;margin-bottom:4px">' + TARGET_DECISION.get(target, "—") + "</div>"
                '<div style="color:' + B + ';font-size:11px;margin-bottom:6px">Integration: ' + path + "</div>"
                '<div style="color:' + DIM + ';font-size:11px">'
                "MFE lift: " + _lift(a.get("mfe_lift_pp")) + "  |  "
                "Validations: " + str(_n_val(a["id"]))
                + "</div></div>"
            )
        html += _box("Promotion Queue", pq)

    # ── 4. SHADOW PRODUCTION ─────────────────────────────────────────────────
    # Purpose: measure live lift before promotion — final confirmation step
    if shadow:
        sh = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
            "Pattern runs alongside SmartList. Zero impact on live decisions. "
            "Advances to ProductionReady after 14 days with lift≥3pp."
            "</div>"
        )
        for a in shadow:
            shadow_rows = shadow_log.get(a["id"], [])
            latest = shadow_rows[-1] if shadow_rows else None
            sh_lift = latest.get("mfe_lift_pp") if latest else None
            n_fired = latest.get("n_fired") if latest else None
            n_not   = latest.get("n_not_fired") if latest else None
            target  = a.get("promotion_target") or ""
            sh += (
                '<div style="border:1px solid ' + G + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                '<span style="color:' + G + ';font-weight:bold">' + a.get("name", "") + "</span>"
                + _badge(a["status"], G) + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-bottom:4px">'
                + TARGET_DECISION.get(target, "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px">'
                "Shadow lift: " + (_lift(sh_lift) if sh_lift is not None else "not yet measured")
                + ("  |  fired=" + str(n_fired) + "  control=" + str(n_not) if n_fired else "")
                + "</div></div>"
            )
        html += _box("Shadow Production", sh)

    # ── 5. PROMOTED KNOWLEDGE ────────────────────────────────────────────────
    # Purpose: institutional memory — what has been validated and is ready to use
    if promoted:
        pr = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
            "Ready for developer integration into SmartList production logic."
            "</div>"
        )
        for a in promoted:
            target = a.get("promotion_target") or "—"
            path   = PROMOTION_PATH.get(target, "—")
            pr += (
                '<div style="border-left:3px solid ' + G + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="color:' + G + ';font-weight:bold">' + a.get("name", "") + " → " + target + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:2px">' + TARGET_DECISION.get(target, "—") + "</div>"
                '<div style="color:' + B + ';font-size:11px;margin-top:2px">' + path + "</div>"
                + ('<div style="color:' + DIM + ';font-size:10px;margin-top:2px">Promoted: '
                   + (a.get("promoted_at") or "")[:10] + "</div>" if a.get("promoted_at") else "")
                + "</div>"
            )
        html += _box("Promoted Knowledge", pr)

    # ── 6. LESSONS LEARNED ───────────────────────────────────────────────────
    # Purpose: cross-asset learning that shapes future discovery and validation
    if lessons:
        ll = ""
        for lesson in lessons:
            cat    = lesson.get("category") or "General"
            impact = lesson.get("impact") or "Medium"
            icol   = IMPACT_COLOR.get(impact, DIM)
            logged = (lesson.get("logged_at") or "")[:10]
            ll += (
                '<div style="border-left:3px solid ' + icol + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
                + _badge(impact, icol)
                + '<span style="color:' + DIM + ';font-size:11px">[' + cat + "]</span>"
                + ('<span style="color:' + DIM + ';font-size:10px;margin-left:auto">' + logged + "</span>" if logged else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px">' + (lesson.get("lesson") or "") + "</div>"
                "</div>"
            )
        html += _box("Lessons Learned", ll)
    else:
        html += _box(
            "Lessons Learned",
            '<p style="color:' + DIM + ';font-size:12px">'
            "No lessons yet. Record what SmartList learns from each discovery:<br>"
            'python discovery_engine.py lesson "text" [Timing|Confidence|Structure|Volume|Context] [High|Medium|Low]'
            "</p>",
        )

    # ── 7. ARCHIVED KNOWLEDGE (collapsed summary) ────────────────────────────
    # Purpose: anti-duplication memory — prevents re-discovering known dead ends
    if archived:
        rej_html = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:8px">'
            "Disproven or insufficient-evidence patterns. Kept to prevent re-discovery."
            "</div>"
        )
        # Group by reason
        duplicates  = [a for a in archived if a.get("novelty_class") in ("Duplicate", "Repackaged")]
        insufficient = [a for a in archived if a.get("novelty_class") not in ("Duplicate", "Repackaged")]
        if duplicates:
            rej_html += (
                '<div style="margin-bottom:6px">'
                '<span style="color:' + DIM + ';font-size:11px;font-weight:bold">Duplicate / Already Captured (' + str(len(duplicates)) + '): </span>'
                '<span style="color:' + DIM + ';font-size:11px">'
                + ", ".join(a.get("name", "").replace("No Incremental Lift — ", "") for a in duplicates)
                + "</span></div>"
            )
        if insufficient:
            for a in insufficient:
                ev    = _ev(a)
                p_val = ev.get("p_value")
                n     = a.get("n_signals") or 0
                rej_html += (
                    '<div style="border-left:2px solid ' + DIM + ';padding:5px 10px;margin-bottom:5px">'
                    '<span style="color:' + DIM + ';font-weight:bold">' + a.get("name", "") + "</span>"
                    '<span style="color:' + DIM + ';font-size:11px"> — '
                    + "n=" + str(n) + ", p=" + (str(round(p_val, 3)) if p_val else "—")
                    + " (insufficient evidence)" + "</span></div>"
                )
        html += _box("Archived Knowledge", rej_html)

    # ── 8. RECENT KNOWLEDGE EVENTS (only if meaningful events exist) ─────────
    # Purpose: audit trail of decisions — shows why assets were moved
    meaningful = [
        e for e in log_entries
        if e.get("event_type") in ("StatusChange", "Promoted", "Rejected", "Archived", "Validated", "Lesson")
    ][:8]
    if meaningful:
        ev_html = '<table style="width:100%;border-collapse:collapse;font-size:11px"><tbody>'
        for e in meaningful:
            ts    = (e.get("logged_at") or "")[:10]
            name  = e.get("asset_name") or ""
            etype = e.get("event_type") or ""
            summ  = (e.get("summary") or "")[:150]
            ecol  = G if etype in ("Promoted", "Validated") else (R if etype in ("Rejected", "Archived") else A)
            ev_html += (
                "<tr>"
                '<td style="color:' + DIM + ';padding:4px 8px;white-space:nowrap;vertical-align:top;width:80px">' + ts + "</td>"
                '<td style="padding:4px 8px;vertical-align:top;width:100px">' + _badge(etype, ecol) + "</td>"
                '<td style="color:' + FG + ';padding:4px 8px;vertical-align:top">'
                + ('<b>' + name + '</b> — ' if name and name != "—" else "") + summ
                + "</td></tr>"
            )
        ev_html += "</tbody></table>"
        html += _box("Recent Knowledge Decisions", ev_html)

    # ── 9. EXTERNAL KNOWLEDGE INTAKE ────────────────────────────────────────
    # Purpose: feed human insights from external research into the validation pipeline
    if inbox:
        ik_html = (
            '<div style="color:' + DIM + ';font-size:11px;margin-bottom:10px">'
            "External hypotheses submitted for validation against SmartList production data."
            "</div>"
        )
        for item in inbox:
            st   = item.get("status") or "Pending"
            scol = G if st == "Created" else A
            ik_html += (
                '<div style="border:1px solid ' + scol + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                '<span style="color:' + FG + ';font-weight:bold">' + (item.get("title") or "Untitled") + "</span>"
                + _badge(st, scol)
                + ('<span style="color:' + DIM + ';font-size:10px;margin-left:auto">' + (item.get("submitted_at") or "")[:10] + "</span>" if item.get("submitted_at") else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px">' + (item.get("content") or "")[:300] + "</div>"
                + ('<div style="color:' + G + ';font-size:11px;margin-top:4px">→ Knowledge asset created</div>' if item.get("asset_id") else "")
                + "</div>"
            )
    else:
        ik_html = (
            '<p style="color:' + DIM + ';font-size:12px">'
            "Submit external research hypotheses for automated validation against production data.<br>"
            "python discovery_engine.py add_notebooklm &quot;hypothesis title&quot; &quot;description and evidence&quot;"
            "</p>"
        )
    html += _box("External Knowledge Intake", ik_html)

    return html
