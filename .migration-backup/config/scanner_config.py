"""
Scanner configuration — extracted from main.py.
Import this module instead of duplicating these constants.
"""

STOCKS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA",
    "EAST.CA", "ABUK.CA", "ORAS.CA", "EFIH.CA",
    "ADIB.CA", "FWRY.CA", "EMFD.CA", "PHDC.CA",
    "ORHD.CA", "EFID.CA", "HRHO.CA", "JUFO.CA",
    "BTFH.CA", "RAYA.CA", "GBCO.CA", "HELI.CA",
    "ARCC.CA", "MCQE.CA", "ORWE.CA", "ISPH.CA",
    "RMDA.CA", "OIH.CA",  "CCAP.CA",
]

def get_constitutional_universe() -> list:
    """Single source of truth for the approved trading universe.

    Returns the 27 EGX symbols defined in STOCKS. All modules MUST import this
    function instead of hardcoding their own universe lists/sets. Return value is
    a fresh copy so callers cannot mutate the canonical list.
    """
    return list(STOCKS)


# Price gate threshold >= 15 (vs default 16)
WHITELIST = [
    "FWRY.CA", "EAST.CA", "ETEL.CA", "EMFD.CA",
    "PHDC.CA", "HRHO.CA", "MCQE.CA", "OIH.CA", "GBCO.CA",
]

NAMES = {
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

SECTORS = {
    "COMI.CA": "Banking",
    "TMGH.CA": "Real Estate",
    "ETEL.CA": "Telecommunications",
    "EGAL.CA": "Basic Resources",
    "EAST.CA": "Consumer Goods",
    "ABUK.CA": "Chemicals & Fertilizers",
    "ORAS.CA": "Engineering & Construction",
    "EFIH.CA": "Financial Services",
    "ADIB.CA": "Banking",
    "FWRY.CA": "Financial Technology",
    "EMFD.CA": "Real Estate",
    "PHDC.CA": "Real Estate",
    "ORHD.CA": "Real Estate",
    "EFID.CA": "Food & Beverages",
    "HRHO.CA": "Financial Services",
    "JUFO.CA": "Food & Beverages",
    "BTFH.CA": "Financial Services",
    "RAYA.CA": "Technology",
    "GBCO.CA": "Automotive",
    "HELI.CA": "Real Estate",
    "ARCC.CA": "Construction Materials",
    "MCQE.CA": "Construction Materials",
    "ORWE.CA": "Manufacturing",
    "ISPH.CA": "Healthcare",
    "RMDA.CA": "Healthcare",
    "OIH.CA":  "Industrial",
    "CCAP.CA": "Financial Services",
}

EMAIL = "shady.gad@live.com"

# Stock quality tiers — used as position sizing multipliers when live sample < 30 per symbol.
# WARNING (Independent Audit 2026-06): Spearman rho = 0.03 between halves — rankings are
# mostly noise. Multipliers are neutralized to 1.0 once ranking_engine.py has n >= 30 per cell.
STOCK_QUALITY: dict[str, float] = {
    # Tier A (expectancy > 10%)
    "MCQE.CA": 1.15, "RAYA.CA": 1.15, "ORHD.CA": 1.15, "ARCC.CA": 1.15, "OIH.CA": 1.15,
    # Tier B (expectancy 7–10%)
    "ETEL.CA": 1.07, "PHDC.CA": 1.07, "CCAP.CA": 1.07, "EFID.CA": 1.07, "ISPH.CA": 1.07,
    # Tier D (expectancy < 4%)
    "JUFO.CA": 0.88, "HRHO.CA": 0.88, "EAST.CA": 0.88, "EFIH.CA": 0.88,
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
