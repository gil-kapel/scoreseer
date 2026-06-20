"""Pre-tournament Elo seeds so the rating model isn't cold at kickoff.

Approximate World-Football-Elo strengths (~2026) by FIFA code. Exact values matter
less than the relative ordering — they give the model a sensible prior before any
WC result exists, instead of starting every team level at 1500 (which collapsed
Elo to the bare home-advantage prior for the earliest matches).
"""

DEFAULT_SEED = 1600.0  # an unseeded team starts mid-pack, not at the 1500 floor

ELO_SEEDS: dict[str, float] = {
    # Elite
    "ARG": 2090, "ESP": 2060, "FRA": 2050, "BRA": 2030, "POR": 2000, "NED": 2000,
    # Strong
    "COL": 1980, "ENG": 1980, "GER": 1960, "BEL": 1930, "CRO": 1920, "URU": 1900,
    "URY": 1900, "MAR": 1900,
    # Good
    "JPN": 1880, "SUI": 1870, "AUT": 1870, "ECU": 1850, "SEN": 1850, "MEX": 1820,
    "KOR": 1820, "SWE": 1820, "NOR": 1820, "IRN": 1820, "USA": 1800, "TUR": 1800,
    "ALG": 1790, "CAN": 1780, "EGY": 1780, "SCO": 1780, "CZE": 1780, "CIV": 1770,
    # Mid
    "AUS": 1750, "BIH": 1750, "PAR": 1720, "TUN": 1720, "GHA": 1700, "PAN": 1700,
    "UZB": 1700, "RSA": 1680, "QAT": 1680, "KSA": 1680, "COD": 1680, "IRQ": 1660,
    "JOR": 1650, "NZL": 1650, "CPV": 1650,
    # Lower
    "HAI": 1550, "CUW": 1500,
}
