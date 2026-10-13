"""
Dashboard: place one trade just before the cut-off of a chosen day and see
how it moves the SARON close.

Run locally with:  streamlit run dashboard.py

This file contains no model logic. The formula and the filter live in
Averagerate.py, so the dashboard and the thesis scripts use the same code.
"""

import streamlit as st

from Averagerate import TRADE_FILTER_BP, add_trade, load_saron_data

st.set_page_config(page_title="SARON trade simulator", layout="centered")
st.title("SARON: one trade before cut-off")


@st.cache_data
def get_data():
    # Cached, so the CSV is read once and not on every click.
    return load_saron_data()


df = get_data()
available_dates = set(df["date"].dt.date)

# 1. Choose the day
chosen_date = st.date_input(
    "Trading day",
    value=df["date"].max().date(),
    min_value=df["date"].min().date(),
    max_value=df["date"].max().date(),
    format="DD.MM.YYYY",
)

if chosen_date not in available_dates:
    st.warning("No SARON value on this date (weekend or holiday). Please choose another day.")
    st.stop()

day = df.loc[df["date"].dt.date == chosen_date].iloc[0]
close_bp = day["close"]
weight_m = day["rate_volume"]

col1, col2 = st.columns(2)
col1.metric("SARON Close", f"{close_bp:.3f} bp")
col2.metric("Rate Volume", f"{weight_m:,.0f} m CHF")

st.divider()

# 2. Choose the trade
col1, col2 = st.columns(2)
trade_volume_m = col1.number_input("Trade volume (million CHF)", min_value=0.1, value=100.0, step=10.0)
trade_rate_bp = col2.number_input("Trade rate (bp)", value=round(float(close_bp), 1), step=1.0, format="%.3f")

# ASSUMPTION: the last accepted price of the day is unknown, so the close is
# used as the reference P_(n-1) for the 50 bp trade filter (see Averagerate.py).
lower, upper = close_bp - TRADE_FILTER_BP, close_bp + TRADE_FILTER_BP
st.caption(f"Trade filter (rulebook 2.1): accepted between {lower:.3f} and {upper:.3f} bp")

new_close_bp, _, accepted = add_trade(close_bp, weight_m, trade_rate_bp, trade_volume_m, close_bp)

if not accepted:
    st.warning(
        f"The trade rate is more than {TRADE_FILTER_BP:.0f} bp away from the previous price. "
        "The trade is filtered out and does not enter the average rate."
    )

st.divider()

# 3. Result
st.metric(
    "New average rate (close)",
    f"{new_close_bp:.3f} bp",
    delta=f"{new_close_bp - close_bp:+.3f} bp",
    delta_color="off",
)

st.caption(
    "Assumptions: the trade is the last event before the cut-off. "
    "Rate Volume is used as the total weight. "
    "The close is used as the previous price for the trade filter."
)
