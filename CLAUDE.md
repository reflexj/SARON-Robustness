# CLAUDE.md: SARON fixing robustness simulation

This file tells Claude Code what this repository is, what to build, and how to work on it. Read it fully before making changes.

## 1. Project context

- **Author:** Simon Fröhlich, BSc Economics (minor Computer Science), University of Bern. Supervisor: Lukas Altermatt (VWI, University of Bern).
- **Thesis topic:** How robust is the SARON (Swiss Average Rate Overnight) fixing against outlier trades, outlier quotes and erroneous inputs, especially when the market is thin?
- **Research question:** At what level of market thinness do the SARON's filter and weighting rules stop protecting the fixing against a single outlier?
- **Gap in the literature:** Duffie & Stein (2015) and Brugler, Khomyn & Putniņš (2025) describe average behaviour over realised fixings. This project looks at rare, adverse constellations (edge cases) that cannot be observed in public data.
- **Framing:** A robustness and integrity analysis in the spirit of the IOSCO principles. It is not a manipulation guide. Code, comments and the dashboard must keep this framing.
- **Deliverable:** The simulation is a separate product next to the written thesis. It gets an interactive dashboard, and all code is published on GitHub.
- **Agreed with the supervisor:** AI help is allowed and encouraged, as long as Simon understands the code.

## 2. How Claude should work in this repo

- **Explain what you build.** Simon has to understand every part of the code. For each change, briefly explain the logic and why it matches the SARON rules. Prefer readable code over clever code.
- **Small steps.** One module or feature at a time, each ending with passing tests. Ask before large refactors or new dependencies.
- **Never invent rules.** If the rulebook is unclear, implement the reading as a configurable switch (see section 4) and say so. Do not silently pick one.
- **Flag uncertainty.** Mark assumptions in code comments (`# ASSUMPTION:`) and in the config.
- **Writing style:** No em dashes or en dashes used as punctuation. Plain, factual language.
- **Public repository:** Never commit confidential information (informal hints from SNB or SIX contacts) or licensed data (e.g. MDDX feeds). Only public data goes into `data/`.

## 3. What to build

### Approach: build broadly parametrised first, then add realism step by step

Version 1 exposes many free parameters, so any market condition can be set by hand. Later versions replace these hand-set parameters with better estimates (calibrated order books, intraday profiles, real data where available). The architecture must make this easy: every assumption is a parameter or a swappable component, never hard-coded.

### Stack

- Python 3.12, numpy, pandas, pytest.
- Streamlit for the dashboard (hosting via Streamlit Community Cloud from the public GitHub repo).
- Plotly or matplotlib for charts.
- If speed becomes a problem: first cache the state just before the outlier, then consider numba. Correctness first.

### Structure

```
src/saronsim/
  events.py       data types: Trade, QuoteUpdate, Cancel
  fixing.py       the SARON fixing function (rulebook logic only)
  generator.py    synthetic trading days (event streams)
  experiment.py   paired runs with/without outlier, parameter grids
  config.py       liquidity levels, generator parameters, rule-variant switches
app/
  dashboard.py    Streamlit app; imports from saronsim, contains no model logic
tests/
  test_fixing.py  hand-calculated examples
scripts/          analyses and figures for the thesis
results/          outputs, always saved together with the config and git hash
data/             public SIX data (CSV)
```

The core (`src/saronsim`) must be usable without the dashboard, so the same code produces the thesis results and drives the app.

### Conventions

- **Units:** rates in basis points (bp), volumes in million CHF, time in minutes since start of the trading window.
- **Reproducibility:** fixed seeds; every result file stores its config and the git commit hash.
- **Paired comparison:** each simulated day is generated once and run through the fixing twice, without and with the outlier, using the same random numbers.

## 4. SARON rules to implement

Source: SIX, *Reglement Swiss Reference Rates*, Version 1.50, 2 December 2024. Section numbers refer to that document.

- **Data basis:** CHF repo trades and binding quotes on the SIX Repo platform, standardised GC contracts, overnight tenor.
- **Formula (2.3):** running volume-weighted average over all events of the day:
  `AR_n = (AR_(n-1) * sum_{j<n} v_j + p_n * v_n) / sum_{j<=n} v_j`
  n counts events within one day (accepted trades and quote reference price recalculations), not days. The weights include both trades and quote reference prices.
- **Trades (2.1):**
  - A trade counts only if its rate is within ±50 bp of the previous price.
  - Trade volume is not capped.
  - Intra-group trades and trades with the SNB are excluded.
  - Cancelled trades are not removed from the average retroactively.
- **Quotes (2.2):**
  - Mid price = volume-weighted average of best bid and best ask.
  - Only quotes within ±3 bp of the mid count.
  - At most the 10 best quotes per side, one quote per bank per side.
  - Quote volume is capped at CHF 100 million.
  - No recalculation if only one side of the book is filled, if the best bid-ask spread exceeds 20 bp, or if the reference price does not change.
  - If no quote lies within the range, the mid price is used.
- **Publication (2.5):** continuous calculation, published every 10 minutes from 08:30. Fixings at 12:00, 16:00 and 18:00. The 18:00 fixing is the reference for derivatives. With no data, the previous day's value is used.
- **Corrections (7.2):** errors of ±2 bp or more versus the 18:00 fixing are corrected by 22:00 if identified by 20:00. This is a useful benchmark threshold for "material" shifts.

### Open rule questions: implement each as a config switch

1. What exactly is the "previous price" for the 50 bp trade filter?
   - Option A: the last accepted price (trade or quote reference). Default.
   - Option B: the running average. Brugler et al. 2025 describe it this way.
2. Do filtered trades update the filter reference? Default: no.
3. What is the first reference of the day (start value for the filter)? Options: previous day's close, or the first event.
4. Quote reference price and its weight: the exact definition is unclear. Default assumption: volume-weighted mean of the eligible quotes, weighted by the average volume of those quotes. This is unconfirmed.
5. Trading window and cut-off of the overnight segment: unknown, so it is a parameter (default 08:00 to 18:00).

Results should be checked against both options where an option could change conclusions. If a reading matters, that is itself a finding.

## 5. The simulation

### Fixing function (build and test first)

The input is a time-sorted list of events. The output is the path of AR, the 10-minute values, the three fixings, the accepted/filtered status of each event, and the total weight. It is a pure function with no randomness.

### Generator (reduced form, no matching engine)

A trading day is an event stream built from swappable components:

1. **Market rate path:** constant (v1), later with drift or a small random walk.
2. **Trade arrival times:** Poisson process with a time-varying intensity. Profiles: flat (v1), morning-heavy, U-shaped.
3. **Trade sizes:** lognormal. The number of trades follows from the target daily volume divided by the mean size.
4. **Trade rates:** market rate plus noise, rounded to a 0.5 bp tick (public data show rates on a 0.5 bp grid). Noise is roughly 1 to 2 bp.
5. **Quote book:** K banks per side, one quote each; rate = market rate ± half spread + noise; volume lognormal, capped at 100 million; updates and withdrawals arrive randomly.

### Liquidity levels

A liquidity level is a parameter set, not a single order book. Real reference points from public SIX data (median daily Rate Volume):

| Period | Median daily Rate Volume |
|---|---|
| 2026 | about CHF 25 bn (trades about 21 bn) |
| 2016 to 2019 | 4 to 5 bn |
| 2012/13 | below 1 bn; the thinnest day was 8 million |

### Outlier experiments

Vary:
- **type:** executed trade, cancelled trade, later quote
- **volume**
- **deviation** (e.g. just under 50 bp)
- **time of day:** this is a key variable of its own and must never be dropped

Each combination runs over hundreds to thousands of simulated days. Report the mean, quantiles and worst case of the fixing shift.

### Outputs

- **Cost-to-move curve:** the volume or interest cost needed to move the 18:00 fixing by 1, 5 or 10 bp, per liquidity level. The cost of an executed overnight trade is volume × deviation / 360. A cancelled trade costs nothing but still moves the fixing.
- **Surface:** liquidity level × time of day.
- **Sensitivity:** how results change with the unidentified parameters (trade size, intraday profile, number of banks, rule-variant switches).

## 6. Build order

1. Data types (`events.py`).
2. Fixing function, trades only: running average, 50 bp filter, exclusions, 10-minute values, fixings, empty-day fallback.
3. Hand-calculated tests (see below).
4. Quote logic with one test per rule.
5. Cancelled trades.
6. Generator v1: trades only, constant rate, flat profile, lognormal sizes, seeded.
7. Paired experiment runner. Check that it reproduces the rule of thumb below.
8. Extend the generator: quotes, intraday profile, 0.5 bp tick, rate noise. Calibrate to public moments (section 7).
9. Streamlit dashboard: sliders for all parameters, one simulated day with/without outlier, cost-to-move curves.
10. Analysis scripts and sensitivity runs for the thesis.

### First tests

| Test | Input | Expected |
|---|---|---|
| Average | 100 m at 0 bp, then 200 m at 3 bp | 2.0 bp |
| Filter | then a trade at 60 bp | filtered; average stays 2.0 bp |
| Rule switch (moving filter) | instead a trade at 52 bp (+49 vs last price 3 bp), then one at 100 bp | Option A: 100 bp is accepted (only +48 vs 52). Option B: filtered (vs running average 14.5 bp) |
| Empty day | no events | previous day's value |
| Rule of thumb | one trade v at deviation d against total weight V | shift = d × v / (V + v) |

## 7. Public data for calibration and plausibility checks

`data/` contains the SIX historical reference rates CSV, with daily values from 30.06.1999 to 08.10.2026:
- SARON Close, Fixing 12:00, Fixing 16:00
- SCRON, SAION, SCION
- Rate Volume and Trade Volume

Format notes:
- Semicolon-separated, with 3 header rows before the column names.
- Dates are DD.MM.YYYY, newest first.
- Rates are in **percent** (convert to bp).

Content notes:
- Trade Volume exists only from 29.02.2016.
- Rate Volume is probably the total weight (trades plus quote weights) in the formula. This is unconfirmed.

Useful targets:
- Trades are 71 to 82 % of Rate Volume.
- Since autumn 2022, the close differs from the 12:00 fixing by a median of 0.25 bp (99th percentile 1.2 bp).
- SCRON minus SARON has a median absolute value of 0.2 to 1.2 bp, depending on the period.
- **Rule of thumb:** 100 m at +50 bp shifts the close by about 0.2 bp at today's volume, about 1 bp at 2016 to 2019 volume, and 5 to 6 bp at 2012/13 volume.

## 8. References

- SIX, Reglement Swiss Reference Rates, V1.50 (2024).
- Duffie, D. & Stein, J. C. (2015). Reforming LIBOR and Other Financial Market Benchmarks. *Journal of Economic Perspectives* 29(2).
- Brugler, J., Khomyn, M. & Putniņš, T. (2025). Benchmarking benchmarks. *Journal of Financial Economics* 168, 104018.
- Fuhrer, L. M. (2017). Liquidity in the Repo Market. SNB Working Paper 2017-06.
