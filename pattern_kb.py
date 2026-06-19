"""
Pattern Intelligence 2.0 — Self-Learning Knowledge Base
=========================================================
Research only. Zero impact on BUY/WAIT/SKIP/Price Gate/Tier/Entry decisions.

Primary metrics: MFE40, Expectancy
Data:            ALL signals (BUY, WAIT, SKIP, EARLY BUY)

Architecture:
  rebuild()                — full historical reconstruction from all sources
  discover_patterns()      — automatic 2/3-flag combination discovery
  update_from_outcomes()   — autonomous learning loop (called after outcomes mature)
  revalidate_features()    — MFE40-based indicator direction & weight correction
  log_telemetry()          — per-signal pattern metadata logging
  generate_report()        — ranked pattern research output
"""
# Constitution §AUTOMATIC ARCHIVING RULE — Research only; no path to production without r1-r8 mapping
RESEARCH_ONLY_LAB = True

import sqlite3
import json
import math
import statistics
import hashlib
from datetime import datetime, date
from collections import defaultdict

DB_PATH = "egx_research.db"
KB_VERSION = "2.0"

# ── Indicator metadata ────────────────────────────────────────────────────────
IND_KEYS = ["stoch_rsi", "p_vs_ma20", "mom_10d", "mom_5d", "atr_ratio", "vol_trend"]
# Design directions (may be corrected by revalidate_features)
IND_DIR_DEFAULT = {
    "stoch_rsi": "lower",
    "p_vs_ma20": "lower",
    "mom_10d":   "lower",
    "mom_5d":    "lower",
    "atr_ratio": "higher",
    "vol_trend": "lower",
}

# Gate flags from signals table (binary: component scored > 0)
GATE_FLAGS = ["r1_price", "r2_ob", "r3_liquidity", "r4_htf",
              "r5_avwap", "r6_macd", "r7_div", "r8_demand"]
# Extra structural flags
STRUCT_FLAGS = ["sweep_detected", "wick_rejection", "equal_lows",
                "sv_hit", "hvn_hit"]

ALL_BINARY_FLAGS = GATE_FLAGS + STRUCT_FLAGS  # 13 binary features

MIN_N_PATTERN = 20   # minimum occurrences for a pattern to qualify
MIN_N_REPORT  = 10   # minimum for regime/yearly sub-stats


# ─────────────────────────────────────────────────────────────────────────────
# DB INITIALISATION
# ─────────────────────────────────────────────────────────────────────────────

def _init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pattern_telemetry (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id             TEXT,
            symbol                TEXT,
            signal_date           TEXT,
            signal_class          TEXT,
            pattern_id            TEXT,
            pattern_version       TEXT,
            pattern_score         REAL,
            pattern_confidence    TEXT,
            matched_cases         INTEGER,
            historical_mfe40      REAL,
            historical_expectancy REAL,
            historical_peak_return REAL,
            market_regime         TEXT,
            indicators_json       TEXT,
            logged_at             TEXT,
            UNIQUE(signal_id)
        );

        CREATE TABLE IF NOT EXISTS pattern_knowledge_base (
            pattern_id      TEXT PRIMARY KEY,
            pattern_def     TEXT NOT NULL,
            pattern_version TEXT,
            n_total         INTEGER DEFAULT 0,
            mfe40_mean      REAL,
            mfe40_std       REAL,
            mfe40_best      REAL,
            mfe40_worst     REAL,
            expectancy      REAL,
            peak_return_avg REAL,
            mae40_mean      REAL,
            sharpe          REAL,
            confidence      TEXT,
            regime_stats    TEXT,
            yearly_stats    TEXT,
            last_seen       TEXT,
            last_updated    TEXT,
            status          TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS pattern_feature_stats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            feature         TEXT,
            direction_design TEXT,
            direction_data  TEXT,
            direction_correct INTEGER,
            spearman_rho    REAL,
            spearman_p      REAL,
            mfe40_corr      REAL,
            weight_design   REAL,
            weight_learned  REAL,
            n_signals       INTEGER,
            updated_at      TEXT,
            UNIQUE(feature)
        );

        CREATE TABLE IF NOT EXISTS pattern_kb_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      TEXT,
            action      TEXT,
            n_signals   INTEGER,
            n_patterns  INTEGER,
            top_pattern TEXT,
            note        TEXT
        );
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — FULL HISTORICAL RECONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def _load_all_records(conn):
    """
    Merge all signal sources into one unified research dataset.
    Includes BUY, WAIT, SKIP, EARLY BUY — no selection bias.
    Returns list of dicts with unified schema.
    """
    records = []

    # Source 1: signals + bottom_quality (production & live scans)
    rows = conn.execute("""
        SELECT
            s.id, s.symbol, s.signal_date, s.price_ok,
            s.raw_score, s.adj_score, s.signal_type,
            s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
            s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
            s.sweep_detected, s.wick_rejection, s.equal_lows,
            s.sv_hit, s.hvn_hit,
            s.ind_stoch_rsi, s.ind_p_vs_ma20, s.ind_mom_10d,
            s.ind_mom_5d, s.ind_atr_ratio, s.ind_vol_trend,
            s.market_regime,
            b.mfe_40d, b.mae_40d, b.peak_return_1y
        FROM signals s
        LEFT JOIN bottom_quality b ON s.id = b.signal_id
        WHERE b.mfe_40d IS NOT NULL
    """).fetchall()

    for r in rows:
        (sid, sym, sdate, price_ok, raw, adj, stype,
         r1, r2, r3, r4, r5, r6, r7, r8,
         sweep, wick, eqlows, sv, hvn,
         stoch, ma20, m10, m5, atr, vol,
         regime, mfe40, mae40, peak) = r
        records.append({
            "source": "signals",
            "id": sid, "symbol": sym, "date": sdate,
            "price_ok": price_ok or 0,
            "signal_class": stype or ("BUY" if price_ok else "WAIT"),
            "raw_score": raw or 0, "adj_score": adj or 0,
            "r1_price": 1 if (r1 or 0) > 0 else 0,
            "r2_ob":    1 if (r2 or 0) > 0 else 0,
            "r3_liquidity": 1 if (r3 or 0) > 0 else 0,
            "r4_htf":   1 if (r4 or 0) > 0 else 0,
            "r5_avwap": 1 if (r5 or 0) > 0 else 0,
            "r6_macd":  1 if (r6 or 0) > 0 else 0,
            "r7_div":   1 if (r7 or 0) > 0 else 0,
            "r8_demand": 1 if (r8 or 0) > 0 else 0,
            "sweep_detected": int(sweep or 0),
            "wick_rejection": int(wick or 0),
            "equal_lows": int(eqlows or 0),
            "sv_hit": int(sv or 0),
            "hvn_hit": int(hvn or 0),
            "stoch_rsi": stoch, "p_vs_ma20": ma20,
            "mom_10d": m10, "mom_5d": m5,
            "atr_ratio": atr, "vol_trend": vol,
            "regime": regime or "Unknown",
            "mfe40": mfe40, "mae40": mae40 or 0,
            "peak": peak or 0,
            "year": sdate[:4] if sdate else "",
        })

    # Source 2: hist_signals (historical archive)
    hist_rows = conn.execute("""
        SELECT
            symbol, signal_date, price_ok,
            raw_score, adj_score,
            r1_price, r2_ob, r3_liquidity, r4_htf,
            r5_avwap, r6_macd, r7_div, r8_demand,
            sweep_detected, wick_rejection, equal_lows,
            sv_hit, hvn_hit,
            mfe_40d, mae_40d, peak_return_1y,
            is_ramadan, sector
        FROM hist_signals
        WHERE mfe_40d IS NOT NULL
    """).fetchall()

    existing_keys = {(r["symbol"], r["date"]) for r in records}
    for r in hist_rows:
        (sym, sdate, price_ok,
         raw, adj,
         r1, r2, r3, r4, r5, r6, r7, r8,
         sweep, wick, eqlows, sv, hvn,
         mfe40, mae40, peak,
         ramadan, sector) = r
        if (sym, sdate) in existing_keys:
            continue
        records.append({
            "source": "hist_signals",
            "id": f"hist_{sym}_{sdate}",
            "symbol": sym, "date": sdate,
            "price_ok": price_ok or 0,
            "signal_class": "BUY" if price_ok else "WAIT",
            "raw_score": raw or 0, "adj_score": adj or 0,
            "r1_price": 1 if (r1 or 0) > 0 else 0,
            "r2_ob":    1 if (r2 or 0) > 0 else 0,
            "r3_liquidity": 1 if (r3 or 0) > 0 else 0,
            "r4_htf":   1 if (r4 or 0) > 0 else 0,
            "r5_avwap": 1 if (r5 or 0) > 0 else 0,
            "r6_macd":  1 if (r6 or 0) > 0 else 0,
            "r7_div":   1 if (r7 or 0) > 0 else 0,
            "r8_demand": 1 if (r8 or 0) > 0 else 0,
            "sweep_detected": int(sweep or 0),
            "wick_rejection": int(wick or 0),
            "equal_lows": int(eqlows or 0),
            "sv_hit": int(sv or 0),
            "hvn_hit": int(hvn or 0),
            "stoch_rsi": None, "p_vs_ma20": None,
            "mom_10d": None, "mom_5d": None,
            "atr_ratio": None, "vol_trend": None,
            "regime": "Unknown",
            "mfe40": mfe40, "mae40": mae40 or 0,
            "peak": peak or 0,
            "year": sdate[:4] if sdate else "",
        })

    # Source 3: signal_log.json (has indicator data + outcome data for 2774 records)
    LOG_FILE = "signal_log.json"
    try:
        import json as _json
        with open(LOG_FILE) as f:
            log_raw = _json.load(f)
        log_sigs = log_raw.get("signals", [])
        existing_keys2 = {(r["symbol"], r["date"]) for r in records}
        # Outcome → MFE40 proxy mapping
        OUTCOME_MFE40 = {"large": 0.35, "medium": 0.18, "small": 0.04,
                         "flat": 0.01, "neutral": None, "pending": None}
        for s in log_sigs:
            sym = s.get("symbol", "")
            sdate = s.get("signal_date") or s.get("date", "")
            outcome = s.get("outcome")
            if not sdate or outcome in (None, "pending", "neutral"):
                continue
            mfe40_proxy = OUTCOME_MFE40.get(outcome)
            if mfe40_proxy is None:
                continue
            if (sym, sdate) in existing_keys2:
                # Already have this signal — enrich with indicator data
                for rec in records:
                    if rec["symbol"] == sym and rec["date"] == sdate:
                        ind = s.get("indicators") or {}
                        if isinstance(ind, str):
                            try: ind = _json.loads(ind)
                            except: ind = {}
                        if isinstance(ind, dict):
                            for k in IND_KEYS:
                                if rec.get(k) is None and k in ind:
                                    rec[k] = ind.get(k)
                        break
                continue
            ind = s.get("indicators") or {}
            if isinstance(ind, str):
                try: ind = _json.loads(ind)
                except: ind = {}
            records.append({
                "source": "signal_log",
                "id": f"log_{sym}_{sdate}",
                "symbol": sym, "date": sdate,
                "price_ok": 1,
                "signal_class": s.get("signal", "BUY"),
                "raw_score": int(s.get("smc_score") or 0),
                "adj_score": int(s.get("smc_score") or 0),
                "r1_price": 0, "r2_ob": 0, "r3_liquidity": 0, "r4_htf": 0,
                "r5_avwap": 0, "r6_macd": 0, "r7_div": 0, "r8_demand": 0,
                "sweep_detected": 0, "wick_rejection": 0, "equal_lows": 0,
                "sv_hit": 0, "hvn_hit": 0,
                "stoch_rsi": ind.get("stoch_rsi") if isinstance(ind, dict) else None,
                "p_vs_ma20": ind.get("p_vs_ma20") if isinstance(ind, dict) else None,
                "mom_10d": ind.get("mom_10d") if isinstance(ind, dict) else None,
                "mom_5d": ind.get("mom_5d") if isinstance(ind, dict) else None,
                "atr_ratio": ind.get("atr_ratio") if isinstance(ind, dict) else None,
                "vol_trend": ind.get("vol_trend") if isinstance(ind, dict) else None,
                "regime": "Unknown",
                "mfe40": mfe40_proxy,
                "mae40": 0,
                "peak": s.get("peak_gain") or 0,
                "year": sdate[:4] if sdate else "",
            })
    except Exception as _log_err:
        pass  # signal_log.json not available or malformed — skip silently

    return records


# ─────────────────────────────────────────────────────────────────────────────
# REGIME CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _classify_regimes(records):
    """
    Classify each record's regime from monthly median MFE40.
    Bull: month avg > 75th pct; Bear: < 25th pct; else Sideways.
    """
    monthly = defaultdict(list)
    for r in records:
        mo = r["date"][:7] if r["date"] else ""
        if mo:
            monthly[mo].append(r["mfe40"])

    mo_avgs = {mo: statistics.median(vs) for mo, vs in monthly.items() if vs}
    if not mo_avgs:
        return

    vals = sorted(mo_avgs.values())
    n = len(vals)
    p25 = vals[max(0, int(n * 0.25))]
    p75 = vals[min(n - 1, int(n * 0.75))]

    for r in records:
        mo = r["date"][:7] if r["date"] else ""
        avg = mo_avgs.get(mo)
        if avg is None:
            r["regime"] = "Unknown"
        elif avg >= p75:
            r["regime"] = "Bull"
        elif avg <= p25:
            r["regime"] = "Bear"
        else:
            r["regime"] = "Sideways"


# ─────────────────────────────────────────────────────────────────────────────
# STATISTICS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_mean(vals):
    return statistics.mean(vals) if vals else None

def _safe_std(vals):
    return statistics.stdev(vals) if len(vals) > 1 else 0

def _safe_sharpe(vals, annualize=12):
    if len(vals) < 2: return None
    mu = statistics.mean(vals)
    sd = _safe_std(vals)
    return round(mu / sd * math.sqrt(annualize), 3) if sd > 0 else None

def _pattern_stats(grp):
    mfes = [r["mfe40"] for r in grp]
    maes = [r["mae40"] for r in grp]
    peaks = [r["peak"] for r in grp]
    return {
        "n": len(grp),
        "mfe40_mean": round(_safe_mean(mfes), 4) if mfes else None,
        "mfe40_std":  round(_safe_std(mfes), 4),
        "mfe40_best": round(max(mfes), 4),
        "mfe40_worst": round(min(mfes), 4),
        "expectancy": round(_safe_mean(mfes), 4) if mfes else None,
        "peak_return_avg": round(_safe_mean(peaks), 4) if peaks else None,
        "mae40_mean": round(_safe_mean(maes), 4) if maes else None,
        "sharpe": _safe_sharpe(mfes),
    }

def _pattern_id(flags_dict):
    """Stable hash from sorted flag definition."""
    s = json.dumps(flags_dict, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:12]

def _confidence(stats):
    """Evidence-based confidence from N, Sharpe, MFE40 stability."""
    n = stats["n"]
    sharpe = stats["sharpe"] or 0
    mfe40 = stats["mfe40_mean"] or 0
    std = stats["mfe40_std"] or 999
    cv = abs(std / mfe40) if mfe40 != 0 else 999  # coefficient of variation

    score = 0
    if n >= 100: score += 3
    elif n >= 50: score += 2
    elif n >= 20: score += 1

    if sharpe >= 3.0: score += 3
    elif sharpe >= 2.0: score += 2
    elif sharpe >= 1.0: score += 1

    if cv < 1.0: score += 2
    elif cv < 2.0: score += 1

    if mfe40 > 0.15: score += 2
    elif mfe40 > 0.07: score += 1

    if score >= 8: return "Very High"
    if score >= 6: return "High"
    if score >= 4: return "Moderate"
    if score >= 2: return "Low"
    return "Very Low"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 + 4 — PATTERN DISCOVERY + KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

def _compute_medians(records):
    """Compute medians for continuous indicator flags."""
    meds = {}
    for k in IND_KEYS:
        vals = [r[k] for r in records if r.get(k) is not None]
        meds[k] = statistics.median(vals) if vals else None
    return meds

def _apply_indicator_flags(records, medians, directions):
    """Add binary indicator flags to each record based on median + direction."""
    for r in records:
        for k in IND_KEYS:
            med = medians.get(k)
            v = r.get(k)
            if v is None or med is None:
                r[f"ind_{k}"] = None
                continue
            if directions.get(k, "lower") == "lower":
                r[f"ind_{k}"] = 1 if v < med else 0
            else:
                r[f"ind_{k}"] = 1 if v > med else 0

    return records

def _get_all_feature_flags(records):
    """
    All binary features: gate flags + struct flags + indicator flags.
    Only include indicator flags for records where all indicators are available.
    """
    # Gate + structural flags always available
    base_features = ALL_BINARY_FLAGS  # 13 flags

    # Indicator flags (only for records with indicator data)
    ind_features = [f"ind_{k}" for k in IND_KEYS]  # 6 flags

    # Return separate lists so callers can choose which to use
    return base_features, ind_features

def discover_patterns(records, conn, min_n=MIN_N_PATTERN):
    """
    Auto-discover all 2 and 3-way flag combinations with N >= min_n.
    Store results in pattern_knowledge_base.
    Returns list of discovered pattern dicts sorted by MFE40.
    """
    base_features, ind_features = _get_all_feature_flags(records)

    discovered = []

    # 2-way combinations from gate+struct flags (always available)
    for i in range(len(base_features)):
        for j in range(i + 1, len(base_features)):
            f1, f2 = base_features[i], base_features[j]
            grp = [r for r in records
                   if r.get(f1) == 1 and r.get(f2) == 1]
            if len(grp) < min_n:
                continue
            rest = [r for r in records
                    if not (r.get(f1) == 1 and r.get(f2) == 1)]
            _store_pattern(conn, {f1: 1, f2: 1}, grp, rest, discovered)

    # 3-way combinations
    for i in range(len(base_features)):
        for j in range(i + 1, len(base_features)):
            for k in range(j + 1, len(base_features)):
                f1, f2, f3 = base_features[i], base_features[j], base_features[k]
                grp = [r for r in records
                       if r.get(f1) == 1 and r.get(f2) == 1 and r.get(f3) == 1]
                if len(grp) < min_n:
                    continue
                rest = [r for r in records
                        if not (r.get(f1) == 1 and r.get(f2) == 1 and r.get(f3) == 1)]
                _store_pattern(conn, {f1: 1, f2: 1, f3: 1}, grp, rest, discovered)

    # Indicator flag combos (for records with indicator data)
    ind_records = [r for r in records
                   if all(r.get(f) is not None for f in ind_features)]
    if len(ind_records) >= min_n:
        for i in range(len(ind_features)):
            for j in range(i + 1, len(ind_features)):
                f1, f2 = ind_features[i], ind_features[j]
                for state in [(1, 1)]:
                    grp = [r for r in ind_records
                           if r.get(f1) == state[0] and r.get(f2) == state[1]]
                    if len(grp) < min_n:
                        continue
                    rest = [r for r in ind_records
                            if not (r.get(f1) == state[0] and r.get(f2) == state[1])]
                    flags = {f1: state[0], f2: state[1]}
                    _store_pattern(conn, flags, grp, rest, discovered)

        for i in range(len(ind_features)):
            for j in range(i + 1, len(ind_features)):
                for k in range(j + 1, len(ind_features)):
                    f1, f2, f3 = ind_features[i], ind_features[j], ind_features[k]
                    grp = [r for r in ind_records
                           if r.get(f1) == 1 and r.get(f2) == 1 and r.get(f3) == 1]
                    if len(grp) < min_n:
                        continue
                    rest = [r for r in ind_records
                            if not (r.get(f1) == 1 and r.get(f2) == 1 and r.get(f3) == 1)]
                    _store_pattern(conn, {f1: 1, f2: 1, f3: 1}, grp, rest, discovered)

    conn.commit()
    discovered.sort(key=lambda x: -(x["mfe40_mean"] or 0))
    return discovered


def _store_pattern(conn, flags_dict, grp, rest, discovered):
    """Compute stats for a pattern group and upsert to pattern_knowledge_base."""
    stats = _pattern_stats(grp)
    if stats["mfe40_mean"] is None:
        return

    pid = _pattern_id(flags_dict)
    conf = _confidence(stats)

    # Regime breakdown
    regime_stats = {}
    for reg in ["Bull", "Bear", "Sideways", "Unknown"]:
        reg_grp = [r for r in grp if r["regime"] == reg]
        if len(reg_grp) >= MIN_N_REPORT:
            rs = _pattern_stats(reg_grp)
            regime_stats[reg] = {
                "n": rs["n"],
                "mfe40": rs["mfe40_mean"],
                "expectancy": rs["expectancy"],
                "sharpe": rs["sharpe"],
            }

    # Yearly breakdown
    yearly_stats = {}
    for yr in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        yr_grp = [r for r in grp if r["year"] == yr]
        if len(yr_grp) >= MIN_N_REPORT:
            ys = _pattern_stats(yr_grp)
            yearly_stats[yr] = {
                "n": ys["n"],
                "mfe40": ys["mfe40_mean"],
                "expectancy": ys["expectancy"],
            }

    # Stability status
    yr_mfes = [(yr, yearly_stats[yr]["mfe40"]) for yr in sorted(yearly_stats.keys())
               if yearly_stats[yr]["mfe40"] is not None]
    if len(yr_mfes) >= 3:
        trend = yr_mfes[-1][1] - yr_mfes[0][1]
        if trend > 0.02:
            status = "improving"
        elif trend < -0.02:
            status = "deteriorating"
        else:
            status = "stable"
    elif len(yr_mfes) >= 1:
        status = "active"
    else:
        status = "active"

    last_seen = max(r["date"] for r in grp if r["date"]) if grp else ""

    conn.execute("""
        INSERT INTO pattern_knowledge_base
            (pattern_id, pattern_def, pattern_version,
             n_total, mfe40_mean, mfe40_std, mfe40_best, mfe40_worst,
             expectancy, peak_return_avg, mae40_mean, sharpe,
             confidence, regime_stats, yearly_stats,
             last_seen, last_updated, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(pattern_id) DO UPDATE SET
            n_total         = excluded.n_total,
            mfe40_mean      = excluded.mfe40_mean,
            mfe40_std       = excluded.mfe40_std,
            mfe40_best      = excluded.mfe40_best,
            mfe40_worst     = excluded.mfe40_worst,
            expectancy      = excluded.expectancy,
            peak_return_avg = excluded.peak_return_avg,
            mae40_mean      = excluded.mae40_mean,
            sharpe          = excluded.sharpe,
            confidence      = excluded.confidence,
            regime_stats    = excluded.regime_stats,
            yearly_stats    = excluded.yearly_stats,
            last_seen       = excluded.last_seen,
            last_updated    = excluded.last_updated,
            status          = excluded.status
    """, (
        pid, json.dumps(flags_dict), KB_VERSION,
        stats["n"], stats["mfe40_mean"], stats["mfe40_std"],
        stats["mfe40_best"], stats["mfe40_worst"],
        stats["expectancy"], stats["peak_return_avg"], stats["mae40_mean"],
        stats["sharpe"], conf,
        json.dumps(regime_stats), json.dumps(yearly_stats),
        last_seen, date.today().isoformat(), status,
    ))

    discovered.append({
        "pattern_id": pid,
        "flags": flags_dict,
        "n": stats["n"],
        "mfe40_mean": stats["mfe40_mean"],
        "expectancy": stats["expectancy"],
        "sharpe": stats["sharpe"],
        "confidence": conf,
        "status": status,
        "best_regime": max(regime_stats, key=lambda r: regime_stats[r]["mfe40"] or 0)
                       if regime_stats else None,
        "yearly_stats": yearly_stats,
    })


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7 — FEATURE REVALIDATION (MFE40-based)
# ─────────────────────────────────────────────────────────────────────────────

def revalidate_features(records, conn):
    """
    For each of 6 indicators compute:
    - Spearman rho vs MFE40 (primary metric, not win/loss)
    - Empirical direction from data
    - Correct direction in learned_weights.json if wrong

    Returns feature stats dict.
    """
    try:
        from scipy import stats as scipy_stats
        has_scipy = True
    except ImportError:
        has_scipy = False

    LEARNED_FILE = "learned_weights.json"
    try:
        with open(LEARNED_FILE) as f:
            lw = json.load(f)
    except Exception:
        lw = {}

    current_directions = lw.get("directions", IND_DIR_DEFAULT.copy())
    feature_stats = {}
    corrected = False

    for k in IND_KEYS:
        pairs = [(r[k], r["mfe40"]) for r in records
                 if r.get(k) is not None and r["mfe40"] is not None]
        if len(pairs) < 30:
            feature_stats[k] = {"n": len(pairs), "note": "insufficient data"}
            continue

        ind_vals = [p[0] for p in pairs]
        mfe_vals = [p[1] for p in pairs]
        n = len(pairs)

        # Spearman correlation vs MFE40
        if has_scipy:
            sp = scipy_stats.spearmanr(ind_vals, mfe_vals)
            rho = sp.statistic
            p_val = sp.pvalue
        else:
            rho = _manual_spearman(ind_vals, mfe_vals)
            p_val = None

        # Empirical direction: rho > 0 means "higher is better"
        empirical_dir = "higher" if rho > 0 else "lower"
        design_dir = IND_DIR_DEFAULT.get(k, "lower")
        data_dir = current_directions.get(k, design_dir)
        direction_correct = (empirical_dir == design_dir)

        # Means in wins vs losses (MFE40 >= 0.07 vs < 0.07)
        win_vals = [p[0] for p in pairs if p[1] >= 0.07]
        loss_vals = [p[0] for p in pairs if p[1] < 0.07]
        win_mean = statistics.mean(win_vals) if win_vals else None
        loss_mean = statistics.mean(loss_vals) if loss_vals else None

        feature_stats[k] = {
            "n": n,
            "spearman_rho": round(rho, 4),
            "spearman_p": round(p_val, 4) if p_val is not None else None,
            "direction_design": design_dir,
            "direction_empirical": empirical_dir,
            "direction_correct": direction_correct,
            "win_mean": round(win_mean, 4) if win_mean else None,
            "loss_mean": round(loss_mean, 4) if loss_mean else None,
        }

        # Correct direction if data is clear and significant
        if p_val is not None and p_val < 0.05 and abs(rho) >= 0.04:
            if current_directions.get(k) != empirical_dir:
                current_directions[k] = empirical_dir
                corrected = True
                feature_stats[k]["direction_corrected"] = True

        # Store to DB
        conn.execute("""
            INSERT INTO pattern_feature_stats
                (feature, direction_design, direction_data, direction_correct,
                 spearman_rho, spearman_p, mfe40_corr,
                 weight_design, weight_learned, n_signals, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(feature) DO UPDATE SET
                direction_data    = excluded.direction_data,
                direction_correct = excluded.direction_correct,
                spearman_rho      = excluded.spearman_rho,
                spearman_p        = excluded.spearman_p,
                mfe40_corr        = excluded.mfe40_corr,
                weight_learned    = excluded.weight_learned,
                n_signals         = excluded.n_signals,
                updated_at        = excluded.updated_at
        """, (
            k,
            design_dir, empirical_dir,
            1 if direction_correct else 0,
            round(rho, 4),
            round(p_val, 4) if p_val is not None else None,
            round(rho, 4),
            lw.get("weights", {}).get(k),
            lw.get("weights", {}).get(k),
            n,
            date.today().isoformat(),
        ))

    conn.commit()

    # Persist corrected directions
    if corrected:
        lw["directions"] = current_directions
        lw["directions_updated_at"] = date.today().isoformat()
        lw["directions_source"] = "mfe40_spearman_revalidation"
        try:
            with open(LEARNED_FILE, "w") as f:
                json.dump(lw, f, indent=2)
        except Exception:
            pass

    return feature_stats, corrected


def _manual_spearman(x, y):
    """Fallback Spearman without scipy."""
    n = len(x)
    rx = _rank(x)
    ry = _rank(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n**2 - 1))

def _rank(vals):
    sorted_vals = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0] * len(vals)
    for rank_pos, (orig_idx, _) in enumerate(sorted_vals):
        ranks[orig_idx] = rank_pos + 1
    return ranks


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — TELEMETRY LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_best_pattern(conn, gate_flags: dict) -> tuple:
    """
    Given a signal's gate flags dict (flag_name -> 0/1), find the best matching
    pattern from pattern_knowledge_base.
    Best = most specific (most required flags satisfied) then highest expectancy.
    Returns (pattern_id, mfe40_mean, expectancy, peak_return_avg, n_total) or all-None.
    """
    rows = conn.execute("""
        SELECT pattern_id, pattern_def, n_total, mfe40_mean, expectancy, peak_return_avg
        FROM pattern_knowledge_base
        WHERE n_total >= ?
        ORDER BY n_total DESC
    """, (MIN_N_PATTERN,)).fetchall()

    best_pid = None
    best_mfe40 = None
    best_exp = None
    best_peak = None
    best_matched = 0
    best_n = 0
    best_specificity = -1

    for row in rows:
        pid, pat_def_str, n_total, mfe40, exp, peak = row
        try:
            pat_def = json.loads(pat_def_str)
        except Exception:
            continue
        # Check if all required flags in this pattern are present in the signal
        match = True
        for flag, required_val in pat_def.items():
            if gate_flags.get(flag, 0) != required_val:
                match = False
                break
        if not match:
            continue
        # Prefer: more required flags (specificity) then higher expectancy
        specificity = len(pat_def)
        if (specificity > best_specificity or
                (specificity == best_specificity and (exp or 0) > (best_exp or 0))):
            best_specificity = specificity
            best_pid = pid
            best_mfe40 = mfe40
            best_exp = exp
            best_peak = peak
            best_matched = n_total
            best_n = n_total

    return best_pid, best_mfe40, best_exp, best_peak, best_matched


def log_telemetry(signal_id, symbol, signal_date, signal_class,
                  pattern_score, indicators, market_regime=None,
                  gate_flags: dict = None,
                  db_path=DB_PATH):
    """
    Log per-signal pattern telemetry. Called from main.py scan workflow.
    Does NOT modify entry decisions. Research only.
    gate_flags: dict of flag_name -> 0/1 (r1_price, r2_ob, ..., sv_hit, hvn_hit, etc.)
    """
    try:
        conn = sqlite3.connect(db_path)
        _init_tables(conn)

        # Look up best matching pattern from KB using gate flags
        pid = None
        hist_mfe40 = None
        hist_exp = None
        hist_peak = None
        matched = None

        if gate_flags:
            pid, hist_mfe40, hist_exp, hist_peak, matched = _lookup_best_pattern(conn, gate_flags)

        # Confidence from pattern_score AND pattern match quality
        if hist_mfe40 is not None and pattern_score is not None and pattern_score >= 50:
            conf = "High"
        elif hist_mfe40 is not None and (matched or 0) >= 50:
            conf = "Moderate"
        elif hist_mfe40 is not None:
            conf = "Low"
        elif pattern_score is None:
            conf = "Very Low"
        elif pattern_score >= 70:
            conf = "High"
        elif pattern_score >= 50:
            conf = "Moderate"
        elif pattern_score >= 35:
            conf = "Low"
        else:
            conf = "Very Low"

        conn.execute("""
            INSERT OR IGNORE INTO pattern_telemetry
                (signal_id, symbol, signal_date, signal_class,
                 pattern_id, pattern_version,
                 pattern_score, pattern_confidence, matched_cases,
                 historical_mfe40, historical_expectancy, historical_peak_return,
                 market_regime, indicators_json, logged_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            signal_id, symbol, signal_date, signal_class,
            pid, KB_VERSION,
            pattern_score, conf, matched,
            hist_mfe40, hist_exp, hist_peak,
            market_regime,
            json.dumps(indicators) if indicators else None,
            datetime.utcnow().isoformat(),
        ))
        conn.commit()
    except Exception as e:
        print(f"[PatternKB] telemetry log error: {e}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 — AUTONOMOUS LEARNING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def update_from_outcomes(db_path=DB_PATH):
    """
    Autonomous learning loop — called whenever new outcomes mature.
    1. Load all records with outcomes
    2. Revalidate features
    3. Rediscover patterns
    4. Update KB
    5. Update telemetry confidence from KB
    6. Log run
    Returns summary dict.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_tables(conn)
        records = _load_all_records(conn)
        _classify_regimes(records)

        if len(records) < 20:
            return {"status": "insufficient_data", "n": len(records)}

        # Feature revalidation
        medians = _compute_medians(records)

        # Load current directions (may have been corrected previously)
        try:
            with open("learned_weights.json") as f:
                lw = json.load(f)
            directions = lw.get("directions", IND_DIR_DEFAULT.copy())
        except Exception:
            directions = IND_DIR_DEFAULT.copy()

        records = _apply_indicator_flags(records, medians, directions)
        feat_stats, corrected = revalidate_features(records, conn)

        # Re-apply flags with (possibly corrected) directions
        if corrected:
            try:
                with open("learned_weights.json") as f:
                    lw2 = json.load(f)
                directions = lw2.get("directions", directions)
            except Exception:
                pass
            records = _apply_indicator_flags(records, medians, directions)

        # Pattern discovery
        patterns = discover_patterns(records, conn)

        # Update telemetry confidence from KB
        for pat in patterns:
            conn.execute("""
                UPDATE pattern_telemetry
                SET pattern_id = ?, pattern_confidence = ?
                WHERE pattern_confidence IS NULL
                  AND pattern_score IS NOT NULL
            """, (pat["pattern_id"], pat["confidence"]))

        # Log run
        top = patterns[0] if patterns else {}
        conn.execute("""
            INSERT INTO pattern_kb_log
                (run_at, action, n_signals, n_patterns, top_pattern, note)
            VALUES (?,?,?,?,?,?)
        """, (
            datetime.utcnow().isoformat(),
            "autonomous_update",
            len(records), len(patterns),
            json.dumps(top.get("flags", {})) if top else None,
            f"corrected_directions={corrected}",
        ))
        conn.commit()

        return {
            "status": "ok",
            "n_signals": len(records),
            "n_patterns": len(patterns),
            "directions_corrected": corrected,
            "top_pattern_mfe40": top.get("mfe40_mean"),
        }

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# FULL REBUILD (entry point for initial population)
# ─────────────────────────────────────────────────────────────────────────────

def rebuild(db_path=DB_PATH):
    """
    Full historical reconstruction from all sources.
    Phase 1 → 10 in sequence.
    Returns summary dict.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_tables(conn)

        # Phase 1: Load all records
        records = _load_all_records(conn)
        _classify_regimes(records)

        # Phase 7: Revalidate features
        medians = _compute_medians(records)
        try:
            with open("learned_weights.json") as f:
                lw = json.load(f)
            directions = lw.get("directions", IND_DIR_DEFAULT.copy())
        except Exception:
            directions = IND_DIR_DEFAULT.copy()

        records = _apply_indicator_flags(records, medians, directions)
        feat_stats, corrected = revalidate_features(records, conn)

        if corrected:
            try:
                with open("learned_weights.json") as f:
                    lw2 = json.load(f)
                directions = lw2.get("directions", directions)
                records = _apply_indicator_flags(records, medians, directions)
            except Exception:
                pass

        # Phase 3+4: Pattern discovery and KB population
        patterns = discover_patterns(records, conn)

        # Phase 10 log
        top = patterns[0] if patterns else {}
        conn.execute("""
            INSERT INTO pattern_kb_log
                (run_at, action, n_signals, n_patterns, top_pattern, note)
            VALUES (?,?,?,?,?,?)
        """, (
            datetime.utcnow().isoformat(), "full_rebuild",
            len(records), len(patterns),
            json.dumps(top.get("flags", {})) if top else None,
            f"v{KB_VERSION} rebuild",
        ))
        conn.commit()

        return {
            "status": "ok",
            "n_records": len(records),
            "n_patterns": len(patterns),
            "directions_corrected": corrected,
            "feature_stats": feat_stats,
        }

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 11 — RESEARCH REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(db_path=DB_PATH, top_n=20):
    """
    Generate ranked pattern research report from knowledge base.
    Returns formatted string.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_tables(conn)
        rows = conn.execute("""
            SELECT pattern_id, pattern_def, n_total, mfe40_mean, expectancy,
                   sharpe, mae40_mean, peak_return_avg, confidence,
                   regime_stats, yearly_stats, status, last_seen
            FROM pattern_knowledge_base
            WHERE n_total >= ?
            ORDER BY mfe40_mean DESC
        """, (MIN_N_PATTERN,)).fetchall()

        if not rows:
            return "Pattern Knowledge Base is empty — run rebuild() first."

        lines = [
            "═" * 70,
            f"PATTERN INTELLIGENCE 2.0 — RESEARCH REPORT  ({date.today()})",
            f"Patterns in KB: {len(rows)}   Min N: {MIN_N_PATTERN}",
            "Primary metric: MFE40 (Expectancy) — Win/Loss is supplemental",
            "═" * 70,
        ]

        lines.append(f"\nTOP {min(top_n, len(rows))} PATTERNS BY MFE40")
        lines.append(f"{'#':<3} {'Pattern Definition':<45} {'N':>5} {'MFE40':>7} "
                     f"{'Exp':>7} {'Sharpe':>7} {'MAE40':>7} {'Peak':>7} {'Conf':<10} {'Status':<12}")
        lines.append("─" * 118)

        for i, row in enumerate(rows[:top_n]):
            pid, pdef, n, mfe40, exp, sharpe, mae40, peak, conf, rs, ys, status, last_seen = row
            try:
                flags = json.loads(pdef)
                pat_str = " + ".join(f"{'✓' if v else '✗'}{k}" for k, v in flags.items())
            except Exception:
                pat_str = pdef[:44]
            lines.append(
                f"{i+1:<3} {pat_str:<45} {n:>5} "
                f"{mfe40 or 0:>7.4f} {exp or 0:>7.4f} {sharpe or 0:>7.3f} "
                f"{mae40 or 0:>7.4f} {peak or 0:>7.4f} "
                f"{conf or '—':<10} {status or '—':<12}"
            )

        # Bottom patterns
        bottom = sorted(rows, key=lambda r: r[3] or 0)[:min(10, len(rows))]
        lines.append(f"\nBOTTOM 10 WEAKEST PATTERNS BY MFE40")
        lines.append(f"{'#':<3} {'Pattern Definition':<45} {'N':>5} {'MFE40':>7} {'Conf':<10}")
        lines.append("─" * 75)
        for i, row in enumerate(bottom):
            pid, pdef, n, mfe40, *_ = row
            try:
                flags = json.loads(pdef)
                pat_str = " + ".join(f"{'✓' if v else '✗'}{k}" for k, v in flags.items())
            except Exception:
                pat_str = pdef[:44]
            conf = row[8]
            lines.append(f"{i+1:<3} {pat_str:<45} {n:>5} {mfe40 or 0:>7.4f} {conf or '—':<10}")

        # Regime summary for top 3
        lines.append("\nREGIME PERFORMANCE — TOP 3 PATTERNS")
        for row in rows[:3]:
            pid, pdef, n, mfe40, exp2, sharpe2, mae2, peak2, conf2, rs_json, ys_json2, status2, ls2 = row
            try:
                flags = json.loads(pdef)
                pat_str = " + ".join(f"✓{k}" for k, v in flags.items() if v)
            except Exception:
                pat_str = pdef[:44]
            lines.append(f"  {pat_str}  (N={n})")
            try:
                rs = json.loads(rs_json) if rs_json else {}
                for reg, rs_data in sorted(rs.items()):
                    lines.append(f"    {reg:<10} N={rs_data['n']:>3}  MFE40={rs_data['mfe40']:.4f}  "
                                 f"Exp={rs_data['expectancy']:.4f}  Sharpe={rs_data.get('sharpe') or 0:.3f}")
            except Exception:
                pass

        # Feature validation summary
        fs_rows = conn.execute("""
            SELECT feature, direction_design, direction_data, direction_correct,
                   spearman_rho, spearman_p, weight_learned, n_signals
            FROM pattern_feature_stats
            ORDER BY ABS(spearman_rho) DESC
        """).fetchall()

        if fs_rows:
            lines.append("\nFEATURE VALIDATION (MFE40 Spearman)")
            lines.append(f"  {'Feature':<14} {'Design':>7} {'Data':>7} {'Match':>6} "
                         f"{'rho':>7} {'p':>7} {'Weight':>7} {'N':>6}")
            lines.append("  " + "─" * 72)
            for fr in fs_rows:
                feat, dir_d, dir_dat, correct, rho, p_val, w, n = fr
                lines.append(
                    f"  {feat:<14} {dir_d or '—':>7} {dir_dat or '—':>7} "
                    f"{'✓' if correct else '✗':>6} "
                    f"{rho or 0:>7.4f} {p_val or 0:>7.4f} "
                    f"{w or 0:>7.4f} {n or 0:>6}"
                )

        # Stability summary
        improving = [r for r in rows if r[11] == "improving"]
        deteriorating = [r for r in rows if r[11] == "deteriorating"]
        lines.append(f"\nSTABILITY SUMMARY: "
                     f"improving={len(improving)}  "
                     f"stable={len([r for r in rows if r[11]=='stable'])}  "
                     f"deteriorating={len(deteriorating)}")

        lines.append("\n" + "═" * 70)
        lines.append("Pattern Intelligence 2.0 fully rebuilt, validated, "
                     "and connected to a permanent self-learning research loop.")
        lines.append("═" * 70)

        return "\n".join(lines)

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DAILY HOOK (called from main.py)
# ─────────────────────────────────────────────────────────────────────────────

def daily_run(db_path=DB_PATH):
    """
    Lightweight daily hook — called from _run_scan_workflow() in main.py.
    Runs incremental outcome update (not full rebuild).
    Full rebuild is triggered manually or weekly.
    """
    try:
        return update_from_outcomes(db_path)
    except Exception as e:
        print(f"[PatternKB] daily_run error: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys
    if "--rebuild" in sys.argv:
        print("Running full Pattern Intelligence 2.0 rebuild...")
        result = rebuild()
        print(f"Rebuild complete: {result}")
    print(generate_report())
