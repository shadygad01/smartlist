"""
Extended Signal Logger
======================
يحفظ كل المتغيرات المحسوبة عند كل إشارة في extended_signal_log.json.
لا يمس signal_log.json الأصلي ولا أي منطق قائم.

التكامل مع main.py (سطران فقط):
    from extended_logger import log_extended_signals          # في أعلى الملف
    log_extended_signals(results, SECTORS, STOCK_QUALITY,    # في _run_scan_workflow
                         is_ramadan(), is_cbe_window())
"""

import json
import os
from datetime import date

EXTENDED_LOG = "extended_signal_log.json"
MIN_SCORE    = 35   # نفس حد signal_log — Skip لا يُسجَّل


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load():
    if not os.path.exists(EXTENDED_LOG):
        return {"version": "1.0", "signals": []}
    try:
        with open(EXTENDED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": "1.0", "signals": []}


def _save(data):
    with open(EXTENDED_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_rows(rows):
    """
    استخراج r1-r8 وأوصافها من قائمة rows التي يُرجعها analyze().
    rows format: [("Price Position", score, max_score, description), ...]
    """
    key_map = {
        "Price Position":      ("r1_price",     "d_price"),
        "Order Block Quality": ("r2_ob",         "d_ob"),
        "Liquidity Context":   ("r3_liquidity",  "d_liquidity"),
        "Higher Timeframe":    ("r4_htf",         "d_htf"),
        "Anchored VWAP":       ("r5_avwap",       "d_avwap"),
        "MACD vs Zero":        ("r6_macd",        "d_macd"),
        "Divergence":          ("r7_div",         "d_div"),
        "Demand Zone (SV+VP)": ("r8_demand",      "d_demand"),
    }
    scores = {}
    descs  = {}
    for row in rows:
        name, score, _mx, desc = row
        if name in key_map:
            sk, dk = key_map[name]
            scores[sk] = score
            descs[dk]  = str(desc)[:200]   # نقتطع الوصف الطويل للتوفير
    return scores, descs


def _discount_depth(price, eq, buy_hi):
    """
    نسبة عمق السعر داخل Discount Zone:
      0.0 = عند EQ (الحد الأعلى)
      1.0 = عند Swing Low (الحد الأدنى)

    الاشتقاق: lo = eq − (eq − buy_hi) / 0.70
    """
    try:
        lo    = eq - (eq - buy_hi) / 0.70
        denom = eq - lo
        if denom <= 0:
            return 0.0
        return round(max(0.0, min(1.0, (eq - price) / denom)), 4)
    except Exception:
        return 0.0


# ── Main API ──────────────────────────────────────────────────────────────────

def log_extended_signals(results: dict, sectors: dict, stock_quality: dict,
                          is_ramadan_now: bool, is_cbe_now: bool) -> int:
    """
    يُسجّل إشارات اليوم — يُستدعى مرة واحدة في نهاية _run_scan_workflow().
    يتجاهل الأسهم الي سُجِّلت في نفس اليوم (لا تكرار).
    يُرجع عدد الإشارات الجديدة المُضافة.
    """
    data     = _load()
    today    = str(date.today())
    existing = {s["id"] for s in data["signals"]}
    added    = 0

    for symbol, r in results.items():
        if not r.get("ok"):
            continue

        raw_score = r.get("raw_score", r.get("score", 0))
        if raw_score < MIN_SCORE:
            continue

        signal_id = f"{symbol}_{today}"
        if signal_id in existing:
            continue

        price  = float(r.get("price",   0) or 0)
        eq     = float(r.get("eq",      0) or 0)
        buy_hi = float(r.get("buy_hi",  0) or 0)

        smc_scores, smc_descs = _parse_rows(r.get("rows", []))
        pat = r.get("pattern") or {}
        ez  = r.get("entry_zones")

        record = {
            "id":     signal_id,
            "symbol": symbol,
            "date":   today,
            "signal": r.get("signal", ""),

            # ── الأسكور ───────────────────────────────────────────────
            "raw_score": raw_score,
            "adj_score": r.get("score", 0),

            # ── مكونات SMC الثمانية (r1→r8) ──────────────────────────
            "smc": smc_scores,

            # ── السياق السعري ─────────────────────────────────────────
            "price_ctx": {
                "price":          price,
                "target":         float(r.get("target",    0) or 0),
                "eq":             eq,
                "buy_hi":         buy_hi,
                "sell_lo":        float(r.get("sell_lo",   0) or 0),
                "avwap":          float(r.get("avwap",     0) or 0),
                "avwap_lower":    float(r.get("avwap_l",   0) or 0),
                "discount_depth": _discount_depth(price, eq, buy_hi),
            },

            # ── Pattern Engine ────────────────────────────────────────
            "pattern_indicators": pat.get("detail", {}),
            "pattern": {
                "score":     round(pat.get("pattern_score",   0), 1),
                "effective": round(pat.get("effective_score", 0), 1),
                "win_rate":  round(pat.get("win_rate",        0), 3),
                "avg_gain":  round(pat.get("avg_gain",        0), 2),
                "n_similar": pat.get("similar_count", 0),
            },

            # ── السياق الماكرو ────────────────────────────────────────
            "context": {
                "is_ramadan":  is_ramadan_now,
                "is_cbe":      is_cbe_now,
                "stock_tier":  stock_quality.get(symbol, 1.0),
                "sector":      sectors.get(symbol, ""),
                "ctx_label":   r.get("ctx_label", ""),
            },

            # ── مناطق الدخول ──────────────────────────────────────────
            "zones": {
                "z1":        ez["z1"]["center"]  if ez else None,
                "z2":        ez["z2"]["center"]  if ez else None,
                "z3":        ez["z3"]["center"]  if ez else None,
                "avg_entry": ez["avg_entry"]      if ez else None,
            },

            # ── أوصاف المكونات ────────────────────────────────────────
            "descriptions": smc_descs,

            # ── النتيجة (تُملأ لاحقاً بواسطة outcome_enricher.py) ─────
            "outcome":      "pending",
            "outcome_date": None,
            "r5d":          None,   # عائد بعد 5 أيام تداول
            "r10d":         None,   # عائد بعد 10 أيام تداول
            "r20d":         None,   # عائد بعد 20 يوم تداول
            "mfe":          None,   # Max Favorable Excursion (20d)
            "mae":          None,   # Max Adverse Excursion  (20d)
            "category":     None,   # flat / small / medium / large
        }

        data["signals"].append(record)
        existing.add(signal_id)
        added += 1

    if added:
        _save(data)
        print(f"  [ExtLog] +{added} signal(s) saved → {EXTENDED_LOG}")

    return added
