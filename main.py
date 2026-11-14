"""btc-cent-forecast-01 entry (r2, in-window rebuild).

Forecaster for make.fun's Bitcoin 4-hour-ahead challenge. The starting
point is persistence -- assume the price stays where it is -- because on
this pool's history almost every fancier signal fails out of sample.
Backtesting on the kit's practice recording showed exactly one tilt
that held up in every time fold: a gentle pull back toward the trailing
four-hour average, shrunk hard so it can only nudge the anchor.

    guess = last * exp(-KAPPA * g240)
    g240  = ln(last) - mean(ln(last WINDOW closes))

The log shift is bounded (see forecast()) so a brief spike at the
checkpoint cannot pull the guess far from the last traded price.

Only the standard library is used and the computation is pure
arithmetic on the case's own closes, which makes the program fully
deterministic and fast -- two grader runs produce identical bytes.

Notes on how this shape was chosen, in plain terms:

* The practice recording was cut into consecutive time folds and the
  forecaster was scored fold by fold, never on data it had tuned on.
  A tilt that only helps in one fold is treated as noise, not signal.
* Persistence survived every fold as the anchor. That is expected:
  over a four hour horizon the last close already carries most of
  the information the pool is willing to give up for free.
* The reversion tilt survived every fold as well, but only while it
  stayed small. Larger shrinkage factors looked better in sample and
  then gave the gain back as soon as the fold boundary moved.
* So the shipped constant is deliberately boring. It is the largest
  tilt that never hurt a fold by more than a rounding error, rather
  than the tilt that won the single best fold by the widest margin.
* Everything else in this file exists to protect that small edge:
  clean the inputs, bound the shift, and always emit a valid file.
"""

import json
import math
import os

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

MIN_PRICE = 0.00001
MAX_PRICE = 9_999_999.99999
WINDOW = 240
KAPPA = 0.25
ABS_CAP = 0.02
FALLBACK_PRICE = 100_000.0


def price5(x):
    """Clamp x into the scorer's open interval and snap to 5 decimals."""
    return round(min(MAX_PRICE, max(MIN_PRICE, x)) * 1e5) / 1e5


def _usable_prices(prices):
    """Return only the closes that are safe to do arithmetic on.

    The grader feeds raw pool history, and raw history is messy in
    boring ways: a feed gap can leave a null, a bad tick can leave a
    zero or a negative print, and a glitch can leave an infinity.
    None of those values can go through a logarithm, and none of
    them should be allowed to become the persistence anchor either.

    The rule here is intentionally narrow and easy to audit:

    * the value must be an int or a float, nothing else;
    * it must be finite, so NaN and both infinities are dropped;
    * it must be strictly positive, because prices are positive
      and because log of a non-positive number is undefined.

    Order is preserved. The caller still sees the closes in the
    exact sequence the case supplied them, just with the unusable
    entries removed. If everything is removed the caller decides
    what to do next; this helper never invents a price itself.
    """
    cleaned = []
    for value in prices:
        if not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value):
            continue
        if value <= 0:
            continue
        cleaned.append(value)
    return cleaned


def _horizon_sigma(tail):
    """Estimate four-hour volatility from one-minute log closes.

    ``tail`` holds log prices, oldest first, covering up to the
    trailing WINDOW minutes. Consecutive differences of that series
    are the one-minute log returns. Their dispersion is a per-minute
    volatility, and volatility grows with the square root of time,
    so multiplying by sqrt(WINDOW) rescales it to the forecast
    horizon of four hours.

    A few deliberate choices are baked into this estimate:

    * The mean return is subtracted before squaring, so a steady
      drift inside the window is not mistaken for choppiness.
    * The divisor is the count of returns themselves, keeping this
      a plain population variance with no extra tuning knobs.
    * A window with fewer than two points has no returns at all,
      so the function reports zero and lets the caller fall back
      to its hard cap instead of guessing at a volatility.

    The result is not a forecast. It is only a ruler that the
    caller uses to decide how large a reversion shift is still
    plausible for the conditions visible in this window.
    """
    if len(tail) < 2:
        return 0.0
    returns = []
    for index in range(1, len(tail)):
        returns.append(tail[index] - tail[index - 1])
    average = math.fsum(returns) / len(returns)
    squared = math.fsum((item - average) ** 2 for item in returns)
    variance = squared / len(returns)
    per_minute = math.sqrt(variance)
    return per_minute * math.sqrt(WINDOW)


def forecast(prices):
    """Return the shrunk-reversion forecast for a list of closes."""
    xs = _usable_prices(prices)
    if not xs:
        return price5(FALLBACK_PRICE)
    last = xs[-1]
    if len(xs) < 2:
        return price5(last)
    logs = [math.log(p) for p in xs]
    w = min(WINDOW, len(logs))
    tail = logs[-w:]
    g240 = logs[-1] - math.fsum(tail) / w
    sigma240 = _horizon_sigma(tail)
    shift = -KAPPA * g240
    # Two caps guard the shift, and they guard different failures.
    #
    # The volatility cap says: never move further than one horizon
    # sigma. If the recent window was quiet, even a large-looking
    # gap to the mean is probably a data quirk or a thin moment,
    # so the allowed move shrinks together with the noise level.
    #
    # The absolute cap says: never move further than two percent,
    # full stop. If the recent window was violent, one sigma can
    # be an enormous distance, and trusting it would turn a mild
    # reversion idea into a leveraged bet on a single checkpoint.
    #
    # Taking the smaller of the two means calm markets are ruled
    # by the first cap and wild markets are ruled by the second.
    # When the volatility estimate is zero or unavailable, only
    # the absolute cap remains, which is the safe direction: the
    # shift can get smaller than intended, never larger.
    cap = min(sigma240, ABS_CAP) if sigma240 > 0 else ABS_CAP
    shift = max(-cap, min(cap, shift))
    return price5(last * math.exp(shift))


def run_case(path, stem):
    """Process one .in file into its .out file; never propagates errors."""
    case_id = stem
    guess = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("case"):
            case_id = str(data["case"])
        markets = data["markets"]
        guess = forecast(markets[0]["prices"])
    except Exception:
        guess = None
    if guess is None:
        # Salvage path: a case that broke the full forecast may still
        # carry a usable last close -- persistence on it beats a blind
        # constant. Only a case with nothing usable gets the fallback.
        try:
            with open(path, "r", encoding="utf-8") as fh:
                prices = json.load(fh)["markets"][0]["prices"]
            guess = price5(float(prices[-1]))
        except Exception:
            guess = price5(FALLBACK_PRICE)
    out = {"forecasts": [{"case": case_id, "price": guess}]}
    with open(os.path.join(OUTPUT_DIR, stem + ".out"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, separators=(",", ":")) + "\n")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name in sorted(os.listdir(INPUT_DIR)):
        if name.endswith(".in"):
            run_case(os.path.join(INPUT_DIR, name), name[: -len(".in")])


if __name__ == "__main__":
    main()
