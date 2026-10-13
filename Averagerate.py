"""
Step 1: the SARON Average Rate formula with one added trade.

Rulebook: SIX, Reglement Swiss Reference Rates, V1.50, section 2.3:

    AR_n = (AR_(n-1) * sum_{j<n} v_j + p_n * v_n) / sum_{j<=n} v_j

We do not observe the individual trades of a day, only the end-of-day values.
But the formula only needs two numbers from "the past": the current average
AR_(n-1) and the total weight sum_{j<n} v_j so far. The SIX data give us both
at the end of the day:
    AR_(n-1)        = SARON Close
    sum_{j<n} v_j   = Rate Volume
So we can ask: what would the close have been if one more trade had come in
just before the cut-off?

Units (see CLAUDE.md): rates in bp, volumes in million CHF.
"""

from pathlib import Path

import pandas as pd

DATA_FILE = Path(__file__).parent / "SARON_Volumes.csv"

TRADE_FILTER_BP = 50.0  # section 2.1: trades outside +/- 50 bp of the previous price are ignored


def load_saron_data(path=DATA_FILE):
    """Read the SIX CSV and return one row per day, oldest first, in bp and million CHF."""
    columns = [
        "date", "close", "fixing_12", "fixing_16",
        "scron_close", "saion_close", "scion_close",
        "rate_volume", "trade_volume",
    ]
    # The file has 4 header lines (ISIN, SYMBOL, NAME, column names). We skip
    # them and set our own names, because "Close" appears several times.
    df = pd.read_csv(path, sep=";", skiprows=4, names=columns)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")

    for col in ["close", "fixing_12", "fixing_16", "scron_close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce") * 100  # percent -> bp
    for col in ["rate_volume", "trade_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 1e6  # CHF -> million CHF

    return df.sort_values("date").reset_index(drop=True)


def add_trade(ar_bp, weight_m, trade_rate_bp, trade_volume_m, previous_price_bp):
    """
    Feed one trade into the running average (rulebook 2.1 and 2.3).

    ar_bp              current average rate AR_(n-1), in bp
    weight_m           total weight so far, sum of v_j for j < n, in million CHF
    trade_rate_bp      rate of the new trade, in bp
    trade_volume_m     volume of the new trade, in million CHF (not capped, 2.1)
    previous_price_bp  reference for the 50 bp trade filter (P_(n-1))

    Returns (new_ar_bp, new_weight_m, accepted).
    """
    # Trade filter, 2.1: P_(n-1) - 50 bp <= T_p <= P_(n-1) + 50 bp. Borders count.
    if abs(trade_rate_bp - previous_price_bp) > TRADE_FILTER_BP:
        return ar_bp, weight_m, False  # filtered: average and weight unchanged

    new_weight_m = weight_m + trade_volume_m
    new_ar_bp = (ar_bp * weight_m + trade_rate_bp * trade_volume_m) / new_weight_m
    return new_ar_bp, new_weight_m, True


def outlier_on_day(df, date, deviation_bp, trade_volume_m):
    """Add one trade at (close + deviation) just before the cut-off of the given day."""
    day = df.loc[df["date"] == pd.Timestamp(date)].iloc[0]
    ar_before = day["close"]
    weight = day["rate_volume"]

    # ASSUMPTION: we do not know the last accepted price of the day, so we use
    # the close as the filter reference P_(n-1). With a constant market rate
    # these are close to each other. Open rule question 1 in CLAUDE.md.
    previous_price = ar_before
    trade_rate = ar_before + deviation_bp

    ar_after, _, accepted = add_trade(ar_before, weight, trade_rate, trade_volume_m, previous_price)

    # Rule of thumb from CLAUDE.md: shift = d * v / (V + v). Should match exactly.
    rule_of_thumb = deviation_bp * trade_volume_m / (weight + trade_volume_m) if accepted else 0.0

    return {
        "date": day["date"].date(),
        "rate_volume_m": weight,
        "close_bp": ar_before,
        "trade_rate_bp": trade_rate,
        "accepted": accepted,
        "new_close_bp": ar_after,
        "shift_bp": ar_after - ar_before,
        "rule_of_thumb_bp": rule_of_thumb,
    }


if __name__ == "__main__":
    df = load_saron_data()

    # One trade of CHF 100 million at +49 bp (just inside the filter), on
    # days from three liquidity regimes. Dates chosen near the median volume
    # of each period (see the median check printed below).
    deviation_bp = 49.0
    trade_volume_m = 100.0

    print("Median daily Rate Volume (million CHF):")
    for label, start, end in [("2012/13", "2012-01-01", "2013-12-31"),
                              ("2016-2019", "2016-01-01", "2019-12-31"),
                              ("2026", "2026-01-01", "2026-12-31")]:
        period = df[(df["date"] >= start) & (df["date"] <= end)]
        print(f"  {label:10s} {period['rate_volume'].median():>10,.0f}")
    print()

    def median_day(start, end):
        """Pick the day whose Rate Volume is closest to the period median."""
        period = df[(df["date"] >= start) & (df["date"] <= end)].dropna(subset=["close", "rate_volume"])
        idx = (period["rate_volume"] - period["rate_volume"].median()).abs().idxmin()
        return period.loc[idx, "date"]

    days = [
        median_day("2012-01-01", "2013-12-31"),
        median_day("2016-01-01", "2019-12-31"),
        df["date"].max(),  # latest day in the file
    ]

    print(f"One trade: {trade_volume_m:.0f} m CHF at close {deviation_bp:+.0f} bp, just before cut-off\n")
    for d in days:
        r = outlier_on_day(df, d, deviation_bp, trade_volume_m)
        print(f"{r['date']}  Rate Volume {r['rate_volume_m']:>9,.0f} m   "
              f"close {r['close_bp']:7.3f} bp -> {r['new_close_bp']:7.3f} bp   "
              f"shift {r['shift_bp']:+.3f} bp")

    # Filter check: a trade at +51 bp must be ignored.
    r = outlier_on_day(df, df["date"].max(), 51.0, trade_volume_m)
    print(f"\nFilter check, +51 bp on {r['date']}: accepted={r['accepted']}, shift {r['shift_bp']:+.3f} bp")
