"""
Standalone module: _section_research_lab()
Imported by dashboard.py to avoid nested f-string syntax issues.
"""
import json


def build_research_lab_section(
    data: dict,
    BG1: str, BG2: str, BOR: str, FG: str, DIM: str,
    G: str, R: str, A: str, B: str,
    _section_header,
    _box,
    _ts,
) -> str:
    hypotheses         = data["hypotheses"]
    live_stats         = data["live_stats"]
    latest_validation  = data["latest_validation"]
    validation_history = data["validation_history"]
    log_entries        = data["log_entries"]
    lessons            = data["lessons"]
    total_signals      = data["total_signals"]

    TERMINAL = {"Promoted", "Rejected", "Retired"}
    STATUS_COLOR = {
        "Tracking": B, "Validated": B, "Improving": G,
        "Stable": A, "Failing": R, "Promoted": G,
        "Rejected": DIM, "Retired": DIM,
    }

    def bs(s):
        c = STATUS_COLOR.get(s, DIM)
        return (
            '<span style="background:' + c + '22;color:' + c + ';border:1px solid ' + c + ';'
            'padding:2px 8px;border-radius:4px;font-size:0.78em;font-weight:600">' + s + '</span>'
        )

    def fc(v, good=0.15, warn=0.05):
        if v is None:
            return '<span style="color:' + DIM + '">—</span>'
        c = G if v >= good else (A if v >= warn else R)
        return '<span style="color:' + c + '">' + f'{v:+.3f}' + '</span>'

    def fr2(v):
        if v is None:
            return '<span style="color:' + DIM + '">—</span>'
        c = G if v >= 0.01 else (A if v >= 0.005 else DIM)
        return '<span style="color:' + c + '">' + f'{v:+.4f}' + '</span>'

    def fp(v):
        if v is None:
            return '<span style="color:' + DIM + '">—</span>'
        c = G if v >= 0.05 else (A if v >= 0 else R)
        return '<span style="color:' + c + '">' + f'{v*100:+.1f}pp' + '</span>'

    def fmfe(v):
        if v is None:
            return '<span style="color:' + DIM + '">—</span>'
        c = G if v >= 0.07 else (A if v >= 0 else R)
        return '<span style="color:' + c + '">' + f'{v*100:+.1f}%' + '</span>'

    def qrow(label, q1, q2, q3, q4):
        sep = ' <span style="color:' + DIM + '">→</span> '
        cells = sep.join(fmfe(q) for q in [q1, q2, q3, q4])
        return (
            '<div style="font-size:0.82em;margin-bottom:4px">'
            '<span style="color:' + DIM + ';display:inline-block;min-width:80px">' + label + '</span>'
            ' Q1→Q4: ' + cells + '</div>'
        )

    active   = [h for h in hypotheses if h["status"] not in ("Rejected", "Retired")]
    terminal = [h for h in hypotheses if h["status"] in TERMINAL]

    # ── 1. Summary table ──────────────────────────────────────────────────────
    act_rows = ""
    for h in active:
        st  = live_stats.get(h["id"], {})
        lv  = latest_validation.get(h["id"])
        lv_date = _ts(lv["run_at"], "%Y-%m-%d") if lv else "never"
        n   = st.get("n", 0)
        act_rows += (
            '<tr style="border-top:1px solid ' + BOR + '">'
            '<td style="padding:7px 10px;font-weight:600;color:' + FG + '">' + h["name"] + '</td>'
            '<td style="padding:7px 10px">' + bs(h["status"])
            + ((' <span style="color:' + DIM + ';font-size:0.75em">→ ' + st.get("auto_status", "") + '</span>')
               if st.get("auto_status") and st.get("auto_status") != h["status"] else "")
            + '</td>'
            '<td style="padding:7px 10px;text-align:right">' + fc(st.get("corr_mfe_40d")) + '</td>'
            '<td style="padding:7px 10px;text-align:right">' + fc(st.get("corr_r20d")) + '</td>'
            '<td style="padding:7px 10px;text-align:right">' + fr2(st.get("incremental_r2")) + '</td>'
            '<td style="padding:7px 10px;text-align:right">' + fp(st.get("win_rate_lift")) + '</td>'
            '<td style="padding:7px 10px;text-align:right;color:' + DIM + '">'
            + str(n) + '/' + str(total_signals) + '</td>'
            '<td style="padding:7px 10px;color:' + DIM + ';font-size:0.78em">' + lv_date + '</td>'
            '</tr>'
        )
    no_row = '<tr><td colspan="8" style="padding:10px;color:' + DIM + '">No active hypotheses.</td></tr>'
    act_table = (
        '<table style="width:100%;border-collapse:collapse;font-size:0.83em">'
        '<thead><tr style="color:' + DIM + '">'
        '<th style="padding:6px 10px;text-align:left">Hypothesis</th>'
        '<th style="padding:6px 10px;text-align:left">Status</th>'
        '<th style="padding:6px 10px;text-align:right">r(MFE40)</th>'
        '<th style="padding:6px 10px;text-align:right">r(R20D)</th>'
        '<th style="padding:6px 10px;text-align:right">ΔR²</th>'
        '<th style="padding:6px 10px;text-align:right">WR Lift</th>'
        '<th style="padding:6px 10px;text-align:right">N scored/total</th>'
        '<th style="padding:6px 10px;text-align:left">Last Formal Validation</th>'
        '</tr></thead><tbody>' + (act_rows or no_row) + '</tbody></table>'
    )

    # ── 2. Hypothesis detail cards ────────────────────────────────────────────
    cards = ""
    for h in active:
        hid = h["id"]
        st  = live_stats.get(hid, {})
        lv  = latest_validation.get(hid)
        vh  = validation_history.get(hid, [])

        # Correlation trend arrows
        trend = ""
        corrs = [v["corr_mfe_40d"] for v in vh[-5:] if v.get("corr_mfe_40d") is not None]
        if len(corrs) >= 2:
            arrows = []
            for i in range(1, len(corrs)):
                d = corrs[i] - corrs[i - 1]
                if d > 0.005:
                    arrows.append('<span style="color:' + G + '">↑</span>')
                elif d < -0.005:
                    arrows.append('<span style="color:' + R + '">↓</span>')
                else:
                    arrows.append('<span style="color:' + DIM + '">→</span>')
            trend = (
                ' <span style="color:' + DIM + ';font-size:0.75em">r(MFE40) trend:</span> '
                + " ".join(arrows)
            )

        lv_note = ""
        if lv and lv.get("conclusion"):
            lv_note = (
                '<div style="color:' + B + ';font-size:0.78em;margin-top:8px;line-height:1.5">'
                '<strong>Last formal conclusion (' + _ts(lv["run_at"], "%Y-%m-%d") + '):</strong> '
                + lv["conclusion"] + '</div>'
            )

        cards += (
            '<div style="background:' + BG2 + ';border:1px solid ' + BOR + ';border-radius:6px;'
            'padding:14px 16px;margin-bottom:10px">'
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">'
            '<span style="font-weight:700;color:' + FG + '">' + h["name"] + '</span>'
            + bs(h["status"]) +
            '<span style="color:' + DIM + ';font-size:0.78em">→ ' + str(h.get("promotion_target", "—")) + '</span>'
            + trend + '</div>'
            '<div style="color:' + DIM + ';font-size:0.78em;margin-bottom:8px;line-height:1.5">'
            + str(h.get("description", "")) + '</div>'
            '<div style="color:' + DIM + ';font-size:0.75em;border-left:2px solid ' + BOR + ';'
            'padding-left:8px;margin-bottom:10px">Formula: ' + str(h.get("formula_notes", "—")) + '</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:18px;font-size:0.83em;margin-bottom:8px">'
            '<div><div style="color:' + DIM + ';font-size:0.75em;margin-bottom:3px">r vs MFE_40D</div>'
            + fc(st.get("corr_mfe_40d")) + '</div>'
            '<div><div style="color:' + DIM + ';font-size:0.75em;margin-bottom:3px">r vs R20D</div>'
            + fc(st.get("corr_r20d")) + '</div>'
            '<div><div style="color:' + DIM + ';font-size:0.75em;margin-bottom:3px">ΔR² beyond r1-r8</div>'
            + fr2(st.get("incremental_r2")) + '</div>'
            '<div><div style="color:' + DIM + ';font-size:0.75em;margin-bottom:3px">WR Lift Q4−Q1</div>'
            + fp(st.get("win_rate_lift")) + '</div>'
            '<div><div style="color:' + DIM + ';font-size:0.75em;margin-bottom:3px">Signals scored</div>'
            '<span style="color:' + FG + '">' + str(st.get("n", 0)) + '</span></div>'
            '</div>'
            + qrow("MFE_40D", st.get("q1_mfe_40d"), st.get("q2_mfe_40d"),
                   st.get("q3_mfe_40d"), st.get("q4_mfe_40d"))
            + qrow("R20D", st.get("q1_r20d"), st.get("q2_r20d"),
                   st.get("q3_r20d"), st.get("q4_r20d"))
            + '<div style="color:' + DIM + ';font-size:0.75em;border-left:2px solid ' + BOR + ';'
            'padding-left:8px;margin-top:8px">Overlap: ' + str(h.get("overlap_analysis", "—")) + '</div>'
            + lv_note
            + '<div style="color:' + DIM + ';font-size:0.76em;margin-top:8px">'
            'Formal validations: ' + str(len(vh)) + ' &nbsp;|&nbsp; '
            '<code>python research_features.py validate ' + hid + '</code></div>'
            '</div>'
        )

    # ── 3. Promotion Queue ────────────────────────────────────────────────────
    promo_cands = [
        h for h in active
        if (live_stats.get(h["id"], {}).get("corr_mfe_40d") or 0) >= 0.15
        and (live_stats.get(h["id"], {}).get("incremental_r2") or 0) >= 0.01
        and h["status"] != "Promoted"
    ]
    if promo_cands:
        pr = ""
        for h in promo_cands:
            st = live_stats.get(h["id"], {})
            pr += (
                '<tr style="border-top:1px solid ' + BOR + '">'
                '<td style="padding:7px 10px;color:' + G + ';font-weight:600">' + h["name"] + '</td>'
                '<td style="padding:7px 10px">' + fc(st.get("corr_mfe_40d")) + '</td>'
                '<td style="padding:7px 10px">' + fr2(st.get("incremental_r2")) + '</td>'
                '<td style="padding:7px 10px;color:' + DIM + '">' + str(st.get("n", 0)) + '</td>'
                '<td style="padding:7px 10px;color:' + DIM + '">' + str(h.get("promotion_target", "—")) + '</td>'
                '<td style="padding:7px 10px;color:' + DIM + ';font-size:0.76em">'
                '<code>python research_features.py promote ' + h["id"] + ' '
                + str(h.get("promotion_target", "")) + ' "&lt;rationale&gt;"</code></td></tr>'
            )
        promo_body = (
            '<div style="color:' + G + ';font-size:0.82em;margin-bottom:8px">'
            'Promotion = ready for human review only. No automatic changes to production.</div>'
            '<table style="width:100%;border-collapse:collapse;font-size:0.83em">'
            '<thead><tr style="color:' + DIM + '">'
            '<th style="padding:6px 10px;text-align:left">Hypothesis</th>'
            '<th style="padding:6px 10px;text-align:left">r(MFE40)</th>'
            '<th style="padding:6px 10px;text-align:left">ΔR²</th>'
            '<th style="padding:6px 10px;text-align:left">N</th>'
            '<th style="padding:6px 10px;text-align:left">Target</th>'
            '<th style="padding:6px 10px;text-align:left">Command</th>'
            '</tr></thead><tbody>' + pr + '</tbody></table>'
        )
    else:
        promo_body = (
            '<p style="color:' + DIM + ';font-size:0.83em">'
            'No hypotheses meet promotion criteria (r(MFE40)≥0.15 and ΔR²≥0.01).</p>'
        )

    # ── 4. Lessons Learned ────────────────────────────────────────────────────
    cat_c = {
        "Alpha": G, "DataQuality": R, "MarketRegime": A,
        "Methodology": B, "General": DIM,
    }
    les_html = ""
    for les in lessons[:20]:
        c   = cat_c.get(les.get("category", "General"), DIM)
        ab  = ('<span style="color:' + G + ';font-size:0.75em">actionable</span>'
               if les.get("actionable") else "")
        les_html += (
            '<div style="border-left:3px solid ' + c + ';padding:8px 12px;margin-bottom:8px;'
            'background:' + BG2 + ';border-radius:0 4px 4px 0">'
            '<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px">'
            '<span style="color:' + c + ';font-size:0.75em;font-weight:600">'
            + str(les.get("category", "General")) + '</span>'
            + ab +
            '<span style="color:' + DIM + ';font-size:0.75em;margin-left:auto">'
            + _ts(les.get("logged_at"), "%Y-%m-%d") + '</span></div>'
            '<div style="color:' + FG + ';font-size:0.83em;line-height:1.5">'
            + str(les.get("lesson", "")) + '</div></div>'
        )
    if not les_html:
        les_html = (
            '<p style="color:' + DIM + ';font-size:0.83em">No lessons recorded. '
            'Use: <code>python research_features.py lesson "text" [category]</code></p>'
        )

    # ── 5. Promotion History ──────────────────────────────────────────────────
    pl = [e for e in log_entries if e.get("event_type") == "Promoted"]
    if pl:
        ph = ""
        for e in pl:
            try:
                det = json.loads(e.get("details_json") or "{}")
            except Exception:
                det = {}
            ph += (
                '<tr style="border-top:1px solid ' + BOR + '">'
                '<td style="padding:6px 10px;color:' + FG + '">' + str(e.get("hyp_name", "—")) + '</td>'
                '<td style="padding:6px 10px;color:' + G + '">Promoted</td>'
                '<td style="padding:6px 10px;color:' + DIM + '">' + str(det.get("target", "—")) + '</td>'
                '<td style="padding:6px 10px;color:' + DIM + '">'
                + _ts(e.get("logged_at"), "%Y-%m-%d") + '</td>'
                '<td style="padding:6px 10px;color:' + DIM + ';font-size:0.78em">'
                + str(det.get("rationale", ""))[:120] + '</td></tr>'
            )
        ph_table = (
            '<table style="width:100%;border-collapse:collapse;font-size:0.83em">'
            '<thead><tr style="color:' + DIM + '">'
            '<th style="padding:6px 10px;text-align:left">Hypothesis</th>'
            '<th style="padding:6px 10px;text-align:left">Decision</th>'
            '<th style="padding:6px 10px;text-align:left">Target</th>'
            '<th style="padding:6px 10px;text-align:left">Date</th>'
            '<th style="padding:6px 10px;text-align:left">Rationale</th>'
            '</tr></thead><tbody>' + ph + '</tbody></table>'
        )
    else:
        ph_table = '<p style="color:' + DIM + ';font-size:0.83em">No promotions recorded.</p>'

    # ── 6. Rejected / Retired Archive ─────────────────────────────────────────
    ar = ""
    for h in terminal:
        lv  = latest_validation.get(h["id"])
        evt = next(
            (e for e in log_entries
             if e.get("hypothesis_id") == h["id"]
             and e.get("event_type") in ("Rejected", "Retired")),
            None,
        )
        rat = ""
        if evt:
            try:
                rat = json.loads(evt.get("details_json") or "{}").get("rationale", "")[:120]
            except Exception:
                pass
        final_r = fc(lv["corr_mfe_40d"] if lv else None)
        final_n = str(lv["n_signals"]) if lv else "—"
        ar += (
            '<tr style="border-top:1px solid ' + BOR + '">'
            '<td style="padding:6px 10px;color:' + DIM + '">' + h["name"] + '</td>'
            '<td style="padding:6px 10px">' + bs(h["status"]) + '</td>'
            '<td style="padding:6px 10px;color:' + DIM + '">' + final_r + '</td>'
            '<td style="padding:6px 10px;color:' + DIM + '">' + final_n + '</td>'
            '<td style="padding:6px 10px;color:' + DIM + ';font-size:0.78em">' + rat + '</td>'
            '<td style="padding:6px 10px;color:' + DIM + '">'
            + _ts(h.get("updated_at"), "%Y-%m-%d") + '</td></tr>'
        )
    no_arch = '<tr><td colspan="6" style="padding:10px;color:' + DIM + '">None archived yet.</td></tr>'
    arch = (
        '<div style="color:' + DIM + ';font-size:0.78em;margin-bottom:8px">'
        'Permanent record. Rejected = no alpha found. Retired = was valid, no longer relevant. '
        'Both remain searchable to prevent re-discovering known dead ends.</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:0.83em">'
        '<thead><tr style="color:' + DIM + '">'
        '<th style="padding:6px 10px;text-align:left">Hypothesis</th>'
        '<th style="padding:6px 10px;text-align:left">Status</th>'
        '<th style="padding:6px 10px;text-align:left">Final r(MFE40)</th>'
        '<th style="padding:6px 10px;text-align:left">N</th>'
        '<th style="padding:6px 10px;text-align:left">Rationale</th>'
        '<th style="padding:6px 10px;text-align:left">Date</th>'
        '</tr></thead><tbody>' + (ar or no_arch) + '</tbody></table>'
    )

    # ── 7. Research Log ───────────────────────────────────────────────────────
    et_color = {
        "Promoted": G, "Validated": B, "Discovered": B,
        "StatusChange": A, "Rejected": R, "Retired": DIM, "Lesson": A,
    }
    lr = ""
    for e in log_entries[:40]:
        et = e.get("event_type", "—")
        c  = et_color.get(et, DIM)
        lr += (
            '<tr style="border-top:1px solid ' + BOR + '">'
            '<td style="padding:5px 10px;color:' + DIM + ';font-size:0.78em;white-space:nowrap">'
            + _ts(e.get("logged_at"), "%Y-%m-%d %H:%M") + '</td>'
            '<td style="padding:5px 10px;color:' + FG + ';font-size:0.82em">'
            + str(e.get("hyp_name") or "—") + '</td>'
            '<td style="padding:5px 10px">'
            '<span style="color:' + c + ';font-size:0.78em;font-weight:600">' + et + '</span></td>'
            '<td style="padding:5px 10px;color:' + DIM + ';font-size:0.78em;'
            'max-width:400px;word-break:break-word">'
            + str(e.get("summary", ""))[:180] + '</td></tr>'
        )
    no_log = '<tr><td colspan="4" style="padding:10px;color:' + DIM + '">No events yet.</td></tr>'
    log_t = (
        '<table style="width:100%;border-collapse:collapse;font-size:0.83em">'
        '<thead><tr style="color:' + DIM + '">'
        '<th style="padding:6px 10px;text-align:left">Time</th>'
        '<th style="padding:6px 10px;text-align:left">Hypothesis</th>'
        '<th style="padding:6px 10px;text-align:left">Event</th>'
        '<th style="padding:6px 10px;text-align:left">Summary</th>'
        '</tr></thead><tbody>' + (lr or no_log) + '</tbody></table>'
    )

    # ── Assemble ──────────────────────────────────────────────────────────────
    hdr = _section_header("RESEARCH LAB — ALPHA DISCOVERY KNOWLEDGE BASE", "🧪")
    intro = (
        '<div style="color:' + DIM + ';font-size:0.78em;margin-bottom:14px;line-height:1.6">'
        'Living knowledge base for alpha research. Hypotheses are tracked, validated formally, '
        'and decided upon. Every conclusion is permanently recorded. '
        'Statistics computed live from <strong style="color:' + FG + '">'
        + str(total_signals) + ' signals</strong> with validated outcomes '
        '(production DB read-only). Knowledge — decisions, lessons, conclusions — '
        'stored in <code>research.db</code> separately from production. '
        'Exit-research hypotheses (Support Failure) never affect production decisions.</div>'
    )

    return (
        '<div style="background:' + BG1 + ';border:2px solid ' + B + ';'
        'border-radius:10px;padding:16px 20px;margin-bottom:18px">'
        + hdr + intro
        + _box("ACTIVE HYPOTHESES", act_table, B)
        + _box("HYPOTHESIS DETAIL & LIVE STATISTICS",
               cards or '<p style="color:' + DIM + '">No active hypotheses.</p>', B)
        + _box("PROMOTION QUEUE — READY FOR HUMAN REVIEW", promo_body, G)
        + _box("LESSONS LEARNED", les_html, A)
        + _box("PROMOTION HISTORY", ph_table, G)
        + _box("REJECTED / RETIRED ARCHIVE", arch, DIM)
        + _box("RESEARCH LOG (last 40 events)", log_t, DIM)
        + '</div>'
    )
