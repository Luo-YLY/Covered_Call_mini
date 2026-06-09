from __future__ import annotations

import math

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call_delta(spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return 1.0 if spot > strike else 0.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))
    return float(_norm_cdf(d1))


def black_scholes_put_delta(spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return -1.0 if spot < strike else 0.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))
    return float(_norm_cdf(d1) - 1.0)


def black_scholes_delta(
    spot: float,
    strike: float,
    years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    option_type = option_type.upper()
    if option_type == "C":
        return black_scholes_call_delta(spot, strike, years, rate, vol)
    if option_type == "P":
        return black_scholes_put_delta(spot, strike, years, rate, vol)
    raise ValueError(f"option_type must be C or P, got {option_type}")
