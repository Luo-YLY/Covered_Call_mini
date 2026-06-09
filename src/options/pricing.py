from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call_price(spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return max(spot - strike, 0.0)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    return spot * _norm_cdf(d1) - strike * math.exp(-rate * years) * _norm_cdf(d2)


def black_scholes_put_price(spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return max(strike - spot, 0.0)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    return strike * math.exp(-rate * years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def black_scholes_price(
    spot: float,
    strike: float,
    years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    option_type = option_type.upper()
    if option_type == "C":
        return black_scholes_call_price(spot, strike, years, rate, vol)
    if option_type == "P":
        return black_scholes_put_price(spot, strike, years, rate, vol)
    raise ValueError(f"option_type must be C or P, got {option_type}")


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    years: float,
    rate: float = 0.02,
    option_type: str = "C",
    low: float = 1e-4,
    high: float = 5.0,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> float:
    if market_price <= 0 or spot <= 0 or strike <= 0 or years <= 0:
        return math.nan

    option_type = option_type.upper()
    discounted_strike = strike * math.exp(-rate * years)
    if option_type == "C":
        lower_bound = max(spot - discounted_strike, 0.0)
        upper_bound = spot
    elif option_type == "P":
        lower_bound = max(discounted_strike - spot, 0.0)
        upper_bound = discounted_strike
    else:
        raise ValueError(f"option_type must be C or P, got {option_type}")

    if market_price < lower_bound - tolerance or market_price > upper_bound + tolerance:
        return math.nan

    low_price = black_scholes_price(spot, strike, years, rate, low, option_type)
    high_price = black_scholes_price(spot, strike, years, rate, high, option_type)
    if market_price <= low_price:
        return low
    if market_price >= high_price:
        return high

    lo = low
    hi = high
    for _ in range(max_iterations):
        mid = (lo + hi) / 2
        price = black_scholes_price(spot, strike, years, rate, mid, option_type)
        if abs(price - market_price) <= tolerance:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
