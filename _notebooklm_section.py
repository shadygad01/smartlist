"""
Standalone module: build_notebooklm_section()
Imported by dashboard.py to avoid nested f-string syntax issues.
"""


def build_notebooklm_section(
    data: dict,
    BG1: str, BG2: str, BOR: str, FG: str, DIM: str,
    G: str, R: str, A: str, B: str,
    _section_header,
    _box,
    _ts,
) -> str:
    assets          = data.get("assets", [])
    lessons         = data.get("lessons", [])
    discovery_log   = data.get("discovery_log", [])
    inbox_items     = data.get("inbox_items", [])
    shadow_log      = data.get("shadow_log", [])
    total_signals   = data.get("total_signals", 0)
    summary         = data.get("summary", {})

    STATUS_COLOR = {
        "Emerging":          B,
        "Validating":        A,
        "LearningCandidate": A,
        "PromotionCandidate": G,
        "ShadowProduction":  G,
        "ProductionReady":   G,
        "Promoted":          G,
        "Rejected":          R,
        "Archived":          DIM,
    }
    TERMINAL = {"Promoted", "Rejected", "Archived"}

    NOVELTY_COLOR = {
        "NewAlpha":        G,
        "AlphaAmplifier":  A,
        "Duplicate":       DIM,
        "Repackaged":      DIM,
        "Unknown":         DIM,
    }

    IMPACT_COLOR = {"High": G, "Medium": A, "Low": DIM}

    # ── group assets by pipeline stage ──────────────────────────────────────
    emerging        = [a for a in assets if a["status"] == "Emerging"]
    validating      = [a for a in assets if a["status"] in ("Validating", "LearningCandidate")]
    promo_queue     = [a for a in assets if a["status"] == "PromotionCandidate"]
    shadow_assets   = [a for a in assets if a["status"] == "ShadowProduction"]
    ready_assets    = [a for a in assets if a["status"] == "ProductionReady"]
    promoted        = [a for a in assets if a["status"] == "Promoted"]
    rejected        = [a for a in assets if a["status"] in ("Rejected", "Archived")]
    active          = [a for a in assets if a["status"] not in TERMINAL]

    def _status_badge(status: str) -> str:
        col = STATUS_COLOR.get(status, DIM)
        return (
            '<span style="background:' + col + '22;color:' + col +
            ';border:1px solid ' + col + ';border-radius:3px;'
            'padding:1px 6px;font-size:11px;white-space:nowrap">'
            + status + "</span>"
        )

    def _novelty_badge(novelty: str) -> str:
        col = NOVELTY_COLOR.get(novelty, DIM)
        return (
            '<span style="color:' + col + ';font-size:11px">[' + novelty + "]</span>"
        )

    def _stat(label: str, val) -> str:
        return (
            '<span style="color:' + DIM + ';font-size:11px">' + label + ": </span>"
            '<span style="color:' + FG + ';font-size:12px">' + str(val) + "</span>  "
        )

    def _asset_row(a: dict) -> str:
        status   = a.get("status", "")
        novelty  = a.get("novelty_class", "Unknown")
        col      = STATUS_COLOR.get(status, DIM)
        lift     = a.get("lift_pct")
        lift_str = (
            ('<span style="color:' + (G if lift > 0 else R) + '">+' + str(round(lift, 1)) + '%</span>')
            if lift is not None else
            '<span style="color:' + DIM + '">—</span>'
        )
        pearson  = a.get("pearson_r")
        pearson_str = (
            '<span style="color:' + (G if pearson and pearson > 0 else R) + '">'
            + str(round(pearson, 3)) + '</span>'
        ) if pearson is not None else '<span style="color:' + DIM + '">—</span>'

        promotion_target = a.get("promotion_target") or ""
        target_str = (
            '<span style="color:' + B + ';font-size:11px">→ ' + promotion_target + "</span>"
        ) if promotion_target else ""

        return (
            "<tr>"
            '<td style="color:' + col + ';font-weight:bold;padding:4px 8px">' + str(a.get("id", "")) + "</td>"
            '<td style="color:' + FG + ';padding:4px 8px">'
            + a.get("name", "") + " " + _novelty_badge(novelty) + " " + target_str
            + "</td>"
            '<td style="padding:4px 8px">' + _status_badge(status) + "</td>"
            '<td style="padding:4px 8px;text-align:right">' + lift_str + "</td>"
            '<td style="padding:4px 8px;text-align:right">' + pearson_str + "</td>"
            '<td style="color:' + DIM + ';font-size:11px;padding:4px 8px">'
            + (a.get("source") or "") + "</td>"
            "</tr>"
        )

    def _asset_card(a: dict) -> str:
        status  = a.get("status", "")
        col     = STATUS_COLOR.get(status, DIM)
        novelty = a.get("novelty_class", "Unknown")
        ncol    = NOVELTY_COLOR.get(novelty, DIM)

        lift     = a.get("lift_pct")
        lift_str = (
            str(round(lift, 1)) + "% lift over baseline"
            if lift is not None else "not measured"
        )
        pearson  = a.get("pearson_r")
        p_str    = str(round(pearson, 3)) if pearson is not None else "—"
        inc_r2   = a.get("incremental_r2")
        inc_str  = str(round(inc_r2, 4)) if inc_r2 is not None else "—"
        n_val    = a.get("n_validations", 0)

        hypothesis  = a.get("hypothesis") or "—"
        evidence    = a.get("evidence") or "—"
        lessons_txt = a.get("lessons_learned") or "—"
        rationale   = a.get("rationale") or ""
        prom_target = a.get("promotion_target") or ""
        overlap     = a.get("overlap_assessment") or "—"

        card = (
            '<div style="border:1px solid ' + col + ';border-radius:6px;padding:14px;'
            'margin-bottom:12px;background:' + BG2 + '">'
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            '<span style="color:' + col + ';font-weight:bold;font-size:14px">#' + str(a.get("id", "")) + ' ' + a.get("name", "") + "</span>"
            + _status_badge(status) +
            '<span style="color:' + ncol + ';font-size:11px;margin-left:4px">' + novelty + "</span>"
        )
        if prom_target:
            card += '<span style="color:' + B + ';font-size:11px;margin-left:auto">→ ' + prom_target + "</span>"
        card += "</div>"

        card += (
            '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:6px;margin-bottom:10px">'
            '<div style="background:' + BG1 + ';border-radius:4px;padding:6px;text-align:center">'
            '<div style="color:' + DIM + ';font-size:10px">LIFT</div>'
            '<div style="color:' + (G if lift and lift > 0 else R) + ';font-size:13px;font-weight:bold">' + lift_str + '</div></div>'
            '<div style="background:' + BG1 + ';border-radius:4px;padding:6px;text-align:center">'
            '<div style="color:' + DIM + ';font-size:10px">PEARSON r</div>'
            '<div style="color:' + FG + ';font-size:13px;font-weight:bold">' + p_str + "</div></div>"
            '<div style="background:' + BG1 + ';border-radius:4px;padding:6px;text-align:center">'
            '<div style="color:' + DIM + ';font-size:10px">INC R²</div>'
            '<div style="color:' + FG + ';font-size:13px;font-weight:bold">' + inc_str + "</div></div>"
            '<div style="background:' + BG1 + ';border-radius:4px;padding:6px;text-align:center">'
            '<div style="color:' + DIM + ';font-size:10px">VALIDATIONS</div>'
            '<div style="color:' + FG + ';font-size:13px;font-weight:bold">' + str(n_val) + "</div></div>"
            "</div>"
        )

        card += (
            '<div style="margin-bottom:6px">'
            '<span style="color:' + DIM + ';font-size:11px">HYPOTHESIS: </span>'
            '<span style="color:' + FG + ';font-size:12px">' + hypothesis + "</span></div>"
        )
        card += (
            '<div style="margin-bottom:6px">'
            '<span style="color:' + DIM + ';font-size:11px">EVIDENCE: </span>'
            '<span style="color:' + FG + ';font-size:12px">' + evidence + "</span></div>"
        )
        if overlap and overlap != "—":
            card += (
                '<div style="margin-bottom:6px">'
                '<span style="color:' + DIM + ';font-size:11px">OVERLAP: </span>'
                '<span style="color:' + A + ';font-size:12px">' + overlap + "</span></div>"
            )
        if lessons_txt and lessons_txt != "—":
            card += (
                '<div style="margin-bottom:6px">'
                '<span style="color:' + DIM + ';font-size:11px">LESSONS: </span>'
                '<span style="color:' + A + ';font-size:12px">' + lessons_txt + "</span></div>"
            )
        if rationale:
            card += (
                '<div style="margin-bottom:4px">'
                '<span style="color:' + DIM + ';font-size:11px">DECISION RATIONALE: </span>'
                '<span style="color:' + FG + ';font-size:12px">' + rationale + "</span></div>"
            )
        card += "</div>"
        return card

    # ────────────────────────────────────────────────────────────────────────────
    # Section 1: Summary / Pipeline Overview
    # ────────────────────────────────────────────────────────────────────────────
    html = _section_header("🔬 NotebookLM Discovery Engine", "Auto-discovery · Knowledge Assets · Promotion Pipeline")

    counts_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">'
    )
    pipeline_stages = [
        ("Emerging",         len(emerging),       B),
        ("Validating",       len(validating),      A),
        ("Promo Candidates", len(promo_queue),     G),
        ("Shadow Production",len(shadow_assets),   G),
        ("Promoted",         len(promoted),        G),
        ("Rejected/Archived",len(rejected),        DIM),
        ("Total Signals",    total_signals,        FG),
    ]
    for label, count, col in pipeline_stages:
        counts_html += (
            '<div style="background:' + BG2 + ';border:1px solid ' + BOR +
            ';border-radius:6px;padding:10px 16px;text-align:center;min-width:110px">'
            '<div style="color:' + col + ';font-size:20px;font-weight:bold">' + str(count) + "</div>"
            '<div style="color:' + DIM + ';font-size:11px">' + label + "</div>"
            "</div>"
        )
    counts_html += "</div>"
    html += _box("Pipeline Overview", counts_html)

    # ── pipeline diagram ──
    pipeline_diagram = (
        '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;font-size:11px;margin:8px 0">'
        '<span style="color:' + B + ';border:1px solid ' + B + ';border-radius:3px;padding:2px 6px">Emerging</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + A + ';border:1px solid ' + A + ';border-radius:3px;padding:2px 6px">Validating</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + A + ';border:1px solid ' + A + ';border-radius:3px;padding:2px 6px">LearningCandidate</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + G + ';border:1px solid ' + G + ';border-radius:3px;padding:2px 6px">PromotionCandidate</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + G + ';border:1px solid ' + G + ';border-radius:3px;padding:2px 6px">ShadowProduction</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + G + ';border:1px solid ' + G + ';border-radius:3px;padding:2px 6px">ProductionReady</span>'
        '<span style="color:' + DIM + '">→</span>'
        '<span style="color:' + G + ';font-weight:bold;border:1px solid ' + G + ';border-radius:3px;padding:2px 6px">Promoted</span>'
        "</div>"
    )
    html += _box("Promotion Pipeline", pipeline_diagram)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 2: Active Knowledge Assets (all non-terminal)
    # ────────────────────────────────────────────────────────────────────────────
    if active:
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px">'
            "<thead><tr>"
            '<th style="color:' + DIM + ';text-align:left;padding:4px 8px;border-bottom:1px solid ' + BOR + '">ID</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:4px 8px;border-bottom:1px solid ' + BOR + '">Knowledge Asset</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:4px 8px;border-bottom:1px solid ' + BOR + '">Status</th>'
            '<th style="color:' + DIM + ';text-align:right;padding:4px 8px;border-bottom:1px solid ' + BOR + '">MFE Lift</th>'
            '<th style="color:' + DIM + ';text-align:right;padding:4px 8px;border-bottom:1px solid ' + BOR + '">Pearson r</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:4px 8px;border-bottom:1px solid ' + BOR + '">Source</th>'
            "</tr></thead><tbody>"
        )
        for a in active:
            table += _asset_row(a)
        table += "</tbody></table>"
        html += _box("Active Knowledge Assets", table)
        for a in active:
            html += _asset_card(a)
    else:
        html += _box("Active Knowledge Assets", '<p style="color:' + DIM + '">No active assets. Run: python discovery_engine.py discover</p>')

    # ────────────────────────────────────────────────────────────────────────────
    # Section 3: Emerging Behaviors
    # ────────────────────────────────────────────────────────────────────────────
    if emerging:
        emerg_html = ""
        for a in emerging:
            lift = a.get("lift_pct")
            lift_str = ("+" + str(round(lift, 1)) + "%") if lift is not None else "—"
            emerg_html += (
                '<div style="border-left:3px solid ' + B + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="color:' + B + ';font-weight:bold">' + a.get("name", "") + " " + _novelty_badge(a.get("novelty_class", "Unknown")) + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:4px">' + (a.get("hypothesis") or "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:4px">'
                "Source: " + (a.get("source") or "—") + "  |  MFE Lift: " + lift_str
                + "</div></div>"
            )
        html += _box("Emerging Behaviors", emerg_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 4: Learning Candidates
    # ────────────────────────────────────────────────────────────────────────────
    if validating:
        lc_html = ""
        for a in validating:
            n_val   = a.get("n_validations", 0)
            lift    = a.get("lift_pct")
            lift_str = ("+" + str(round(lift, 1)) + "%") if lift is not None else "—"
            pearson = a.get("pearson_r")
            p_str   = str(round(pearson, 3)) if pearson is not None else "—"
            lc_html += (
                '<div style="border-left:3px solid ' + A + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px">'
                '<span style="color:' + A + ';font-weight:bold">' + a.get("name", "") + "</span>"
                + _status_badge(a.get("status", "")) +
                "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:4px">' + (a.get("hypothesis") or "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:4px">'
                "Validations: " + str(n_val) + "  |  Pearson r: " + p_str + "  |  MFE Lift: " + lift_str
                + "</div></div>"
            )
        html += _box("Learning Candidates", lc_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 5: Promotion Queue
    # ────────────────────────────────────────────────────────────────────────────
    if promo_queue:
        pq_html = ""
        for a in promo_queue:
            target  = a.get("promotion_target") or "—"
            lift    = a.get("lift_pct")
            lift_str = ("+" + str(round(lift, 1)) + "%") if lift is not None else "—"
            pq_html += (
                '<div style="border:1px solid ' + G + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px">'
                '<span style="color:' + G + ';font-weight:bold">' + a.get("name", "") + "</span>"
                + _status_badge("PromotionCandidate") +
                '<span style="color:' + B + ';font-size:11px;margin-left:auto">Target: ' + target + "</span>"
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:6px">' + (a.get("hypothesis") or "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:4px">'
                "MFE Lift: " + lift_str + "</div>"
                '<div style="color:' + A + ';font-size:11px;margin-top:6px;font-style:italic">'
                "⚠ Awaiting human review — promotion does not auto-deploy"
                + "</div></div>"
            )
        html += _box("Promotion Queue", pq_html)
    else:
        html += _box("Promotion Queue", '<p style="color:' + DIM + ';font-size:12px">No assets in promotion queue.</p>')

    # ────────────────────────────────────────────────────────────────────────────
    # Section 6: Shadow Production Candidates
    # ────────────────────────────────────────────────────────────────────────────
    if shadow_assets or ready_assets:
        sh_html = ""
        for a in (shadow_assets + ready_assets):
            shadow_rows = [s for s in shadow_log if s.get("asset_id") == a.get("id")]
            latest_shadow = shadow_rows[-1] if shadow_rows else None
            sh_lift = latest_shadow.get("lift_pct") if latest_shadow else None
            sh_lift_str = ("+" + str(round(sh_lift, 1)) + "%") if sh_lift is not None else "—"
            sh_fired = latest_shadow.get("fired_count") if latest_shadow else None
            sh_html += (
                '<div style="border:1px solid ' + G + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px">'
                '<span style="color:' + G + ';font-weight:bold">' + a.get("name", "") + "</span>"
                + _status_badge(a.get("status", "")) +
                "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:6px">'
                "Shadow MFE Lift: " + sh_lift_str
                + ("  |  Fired on: " + str(sh_fired) + " signals" if sh_fired is not None else "")
                + "</div>"
                '<div style="color:' + DIM + ';font-size:10px;margin-top:4px">'
                "Running alongside production — zero impact on live decisions"
                + "</div></div>"
            )
        html += _box("Shadow Production", sh_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 7: Promoted Knowledge
    # ────────────────────────────────────────────────────────────────────────────
    if promoted:
        pr_html = ""
        for a in promoted:
            target   = a.get("promotion_target") or "—"
            rationale = a.get("rationale") or "—"
            promoted_at = a.get("updated_at") or ""
            pr_html += (
                '<div style="border-left:3px solid ' + G + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="color:' + G + ';font-weight:bold">' + a.get("name", "") + " → " + target + "</div>"
                '<div style="color:' + FG + ';font-size:12px;margin-top:4px">' + (a.get("hypothesis") or "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:4px">'
                "Rationale: " + rationale + ("  |  " + promoted_at[:10] if promoted_at else "")
                + "</div></div>"
            )
        html += _box("Promoted Knowledge", pr_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 8: Rejected / Archived Knowledge
    # ────────────────────────────────────────────────────────────────────────────
    if rejected:
        rej_html = ""
        for a in rejected:
            rationale = a.get("rationale") or "—"
            rej_html += (
                '<div style="border-left:3px solid ' + DIM + ';padding:8px 12px;margin-bottom:8px">'
                '<div style="color:' + DIM + ';font-weight:bold">' + a.get("name", "") + " [" + a.get("status", "") + "]</div>"
                '<div style="color:' + DIM + ';font-size:12px;margin-top:4px">' + (a.get("hypothesis") or "—") + "</div>"
                '<div style="color:' + DIM + ';font-size:11px;margin-top:2px">Reason: ' + rationale + "</div></div>"
            )
        html += _box("Rejected / Archived", rej_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 9: Lessons Learned
    # ────────────────────────────────────────────────────────────────────────────
    if lessons:
        lessons_html = ""
        for lesson in lessons:
            cat    = lesson.get("category") or "General"
            impact = lesson.get("impact") or "Medium"
            icol   = IMPACT_COLOR.get(impact, DIM)
            lessons_html += (
                '<div style="border-left:3px solid ' + icol + ';padding:8px 12px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
                '<span style="color:' + icol + ';font-size:11px;border:1px solid ' + icol + ';border-radius:3px;padding:1px 5px">' + impact + "</span>"
                '<span style="color:' + DIM + ';font-size:11px">[' + cat + "]</span>"
                + ('<span style="color:' + DIM + ';font-size:10px;margin-left:auto">' + (lesson.get("created_at") or "")[:10] + "</span>" if lesson.get("created_at") else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px">' + (lesson.get("lesson") or "") + "</div>"
                + ('<div style="color:' + DIM + ';font-size:11px;margin-top:2px">Asset: #' + str(lesson.get("asset_id")) + "</div>" if lesson.get("asset_id") else "")
                + "</div>"
            )
        html += _box("Lessons Learned", lessons_html)
    else:
        html += _box("Lessons Learned", '<p style="color:' + DIM + ';font-size:12px">No lessons recorded. Add via: python discovery_engine.py lesson "text" [category] [impact]</p>')

    # ────────────────────────────────────────────────────────────────────────────
    # Section 10: Discovery History
    # ────────────────────────────────────────────────────────────────────────────
    if discovery_log:
        log_html = (
            '<table style="width:100%;border-collapse:collapse;font-size:11px">'
            "<thead><tr>"
            '<th style="color:' + DIM + ';text-align:left;padding:3px 8px;border-bottom:1px solid ' + BOR + '">When</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:3px 8px;border-bottom:1px solid ' + BOR + '">Asset</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:3px 8px;border-bottom:1px solid ' + BOR + '">Action</th>'
            '<th style="color:' + DIM + ';text-align:left;padding:3px 8px;border-bottom:1px solid ' + BOR + '">Details</th>'
            "</tr></thead><tbody>"
        )
        for entry in discovery_log[:50]:
            ts    = (entry.get("created_at") or "")[:16]
            name  = entry.get("asset_name") or ""
            action = entry.get("action") or ""
            detail = entry.get("detail") or ""
            log_html += (
                "<tr>"
                '<td style="color:' + DIM + ';padding:3px 8px;white-space:nowrap">' + ts + "</td>"
                '<td style="color:' + FG + ';padding:3px 8px">' + name + "</td>"
                '<td style="color:' + B + ';padding:3px 8px">' + action + "</td>"
                '<td style="color:' + DIM + ';padding:3px 8px">' + detail + "</td>"
                "</tr>"
            )
        log_html += "</tbody></table>"
        html += _box("Discovery History", log_html)

    # ────────────────────────────────────────────────────────────────────────────
    # Section 11: NotebookLM Discoveries (inbox)
    # ────────────────────────────────────────────────────────────────────────────
    inbox_html = ""
    if inbox_items:
        for item in inbox_items:
            processed = item.get("processed", 0)
            pcol = G if processed else A
            ptext = "processed" if processed else "pending"
            inbox_html += (
                '<div style="border:1px solid ' + pcol + ';border-radius:6px;padding:10px 14px;margin-bottom:8px;background:' + BG2 + '">'
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                '<span style="color:' + FG + ';font-weight:bold">' + (item.get("title") or "Untitled") + "</span>"
                '<span style="color:' + pcol + ';font-size:11px;margin-left:auto">[' + ptext + "]</span>"
                + ('<span style="color:' + DIM + ';font-size:10px">' + (item.get("created_at") or "")[:10] + "</span>" if item.get("created_at") else "")
                + "</div>"
                '<div style="color:' + FG + ';font-size:12px;white-space:pre-wrap">' + (item.get("content") or "") + "</div>"
                + ('<div style="color:' + DIM + ';font-size:11px;margin-top:4px">Generated asset: #' + str(item.get("generated_asset_id")) + "</div>" if item.get("generated_asset_id") else "")
                + "</div>"
            )
    else:
        inbox_html = (
            '<p style="color:' + DIM + ';font-size:12px">'
            "No NotebookLM discoveries submitted. Add via: python discovery_engine.py add_notebooklm &quot;title&quot; &quot;content&quot;"
            "</p>"
        )
    html += _box("NotebookLM Discoveries", inbox_html)

    return html
