# btc-cent-forecast-01 — shrunk mean-reversion forecaster

Entry for make.fun's **btc-cent-forecast-01** ("Forecast Bitcoin's price 4 hours
ahead, 12 times over 48 hours"), account @0xsfh. `main.py` (Python 3.13,
standard library only) is the whole entry: run once per case, it reads the
case's 4,320 one-minute closes from `$MAKEFUN_INPUT_DIR` (default `/input`) and
writes one guess per case to `$MAKEFUN_OUTPUT_DIR` (default `/output`).

## Method

The house baseline is persistence — guess the checkpoint's own close. On this
pool's recorded history that baseline is very hard to beat: unrestricted fits
of gap/momentum features win in-sample and lose walk-forward. The one
deviation that replicated across every time fold and both evaluation sets of
the practice backtest is a small reversion toward the trailing 4-hour mean:

```
guess = last * exp(-0.25 * g240),   g240 = ln(last) - mean(ln(last 240 closes))
```

with the log-shift capped at one horizon-volatility (σ of the last 240 1-minute
log returns × √240) and a hard 2%, so a momentary pool spike at the checkpoint
can never drag the guess far. The shrinkage (0.25, not the in-sample-best 0.30)
and the caps were tuned by MAE on the practice backtest, not by feel.

## Backtest (kit practice data, Nov 2026 recording)

The six practice cases overlap into 92 continuous hours; five of their answers
are recoverable from the kit itself (each case's target is the next case's
checkpoint). Reconstruction check: the five recovered persistence errors imply
a sixth of 31,856¢, consistent with the published practice baseline of
44,521.58¢ over all six.

| evaluation set | persistence | this entry |
| --- | ---: | ---: |
| 241 checkpoints (≥48 h history) | 40,882¢ | 39,908¢ |
| 49 checkpoints (full 72 h history) | 51,012¢ | 49,919¢ |
| 5 exact practice cases | 47,055¢ | 47,331¢ |

The exact-case five are one hard downtrend stretch (the model wins 3 of 5);
the dense checkpoint sets are the tuning evidence. Pure persistence would tie
the house baseline exactly and could never take a prize (a prize needs a score
*strictly* below it), so the small, fold-validated tilt is the honest play.

## Why not more signal?

It is tempting to keep adding features until the backtest looks
clever. Every extra feature below was tried in walk-forward folds
and every one of them was rejected for the same basic reason: it
won on the folds it was tuned on and lost on the folds after them.

* Plain momentum — follow the last hour's direction — flips sign
  too often at this horizon. It helps in trending folds and then
  pays it all back, with interest, in the first choppy fold.
* A drift term fitted over the full window looks stable in sample
  because one long trend dominates the fit. Out of sample the
  drift estimate is mostly a memory of a move that already ended.
* Exponentially weighted averages react faster than the flat mean,
  and that speed is exactly the problem here: they chase the same
  checkpoint spike the caps in `main.py` are designed to ignore.
* Larger reversion strengths were the hardest to give up, because
  0.30 beat 0.25 in sample. Across folds the extra strength only
  ever won by luck-sized margins and lost by real-sized ones.

The surviving rule is the one that never needed a fold to go its
way in order to look acceptable. Boring, in this pool, is evidence.

## Failure behaviour

A forecast that crashes scores worse than a forecast that is merely
wrong, so the program is built to always produce a valid file.

* Unusable closes — nulls, zeros, negatives, non-finite values —
  are filtered out before any arithmetic happens. What remains is
  used in its original order, exactly as supplied.
* If no usable close survives, the entry falls back to a fixed
  reference price rather than emitting an empty or broken file.
* If exactly one usable close survives, that close is the guess:
  persistence is the only honest statement left to make.
* If the full forecast path raises for any reason, a salvage path
  retries with the last raw close, and only a case with nothing
  salvageable at all receives the fixed fallback price.
* Output is always clamped into the scorer's accepted range and
  rounded to five decimals, so even a fallback answer is shaped
  like a real answer and can be scored instead of discarded.

## Run locally

```
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Deterministic (pure arithmetic, no clock, no randomness): two runs agree byte
for byte, and a full six-case pass takes well under a second against the
8-second-per-case cap. Malformed cases still get a valid-shaped output file —
an invalid case would rank the entry below every fully valid one.
