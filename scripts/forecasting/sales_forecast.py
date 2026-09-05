"""Sales forecasting: decomposition, backtested forecast, honest error.

Granularity (the open question: weekly vs. monthly) is resolved here
empirically rather than picked up front -- both series are decomposed
(statsmodels seasonal_decompose, additive) and the fraction of variance
left in the residual after removing trend+seasonality is compared.
Whichever grain leaves a cleaner (lower-residual-fraction) signal is
used for the actual backtested forecast.

The forecast model (SARIMAX, seasonal ARIMA) is backtested against a
held-out tail of the real series and benchmarked against a
seasonal-naive baseline (this period's value = same period last cycle)
-- MAE/RMSE are reported for both, honestly, so a fitted line that
merely looks plausible isn't the bar.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.statespace.sarimax import SARIMAX

from scripts.utils.db import get_engine

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "reports"

# Same join pattern as sql/queries/sales_by_period.sql, at daily grain --
# weekly/monthly comparison is this phase's job, so it's done here in
# pandas via resample rather than baked into a fixed-grain SQL file.
DAILY_SALES_QUERY = """
select
    date_trunc('day', i.invoice_date)::date as day,
    sum(ii.line_total) as net_sales
from invoices i
join invoice_items ii on ii.invoice_no = i.invoice_no
group by 1
order by 1
"""


def load_daily_sales(engine) -> pd.Series:
    df = pd.read_sql(DAILY_SALES_QUERY, engine, index_col="day", parse_dates=["day"])
    full_index = pd.date_range(df.index.min(), df.index.max(), freq="D")
    daily = df["net_sales"].reindex(full_index, fill_value=0.0)
    return trim_trailing_partial_periods(daily)


def trim_trailing_partial_periods(daily: pd.Series) -> pd.Series:
    """Drop trailing days that don't complete a full week/month.

    The dataset ends mid-month (2011-12-09) -- without this, the last
    monthly bucket would hold ~9 days of sales, and a backtest that
    compared a full-month forecast against 9 days of actuals would look
    like a huge miss for reasons that have nothing to do with the model.
    """
    last_date = daily.index.max()

    month_end = last_date + pd.offsets.MonthEnd(0)
    last_full_month_end = last_date if month_end == last_date else last_date.replace(day=1) - pd.Timedelta(days=1)

    # Most recent Monday on/before last_date -- since daily data is
    # continuous back to the series start, the W-MON week ending there
    # is necessarily complete.
    last_full_week_end = last_date - pd.Timedelta(days=last_date.weekday())

    cutoff = min(last_full_month_end, last_full_week_end)
    return daily[daily.index <= cutoff]


def residual_noise_fraction(series: pd.Series, period: int) -> float:
    result = seasonal_decompose(series, model="additive", period=period)
    resid = result.resid.dropna()
    return float(resid.var() / series.var())


def choose_granularity(daily: pd.Series) -> tuple[str, pd.Series, int]:
    weekly = daily.resample("W-MON").sum()
    monthly = daily.resample("MS").sum()

    weekly_noise = residual_noise_fraction(weekly, period=52)
    monthly_noise = residual_noise_fraction(monthly, period=12)

    print("Residual noise fraction after additive decomposition (lower = cleaner signal):")
    print(f"  weekly  (period=52): {weekly_noise:.3f}  [{len(weekly)} points]")
    print(f"  monthly (period=12): {monthly_noise:.3f}  [{len(monthly)} points]")

    if weekly_noise < monthly_noise:
        print("-> Weekly is the cleaner signal; forecasting at weekly granularity.")
        return "weekly", weekly, 52
    print("-> Monthly is the cleaner signal; forecasting at monthly granularity.")
    return "monthly", monthly, 12


def backtest(series: pd.Series, seasonal_period: int, test_size: int) -> dict:
    train, test = series.iloc[:-test_size], series.iloc[-test_size:]

    # SARIMAX rather than Holt-Winters ETS: ETS's default initializer
    # hard-requires >= 2 full seasonal cycles in training data, and with
    # only ~2 years of history total, holding out any test set leaves
    # less than that. SARIMAX fits via MLE/Kalman filter instead, so it
    # runs without that gate -- worth flagging as a real limitation
    # regardless: the annual seasonal term here is estimated from barely
    # more than one full cycle of training data, so treat it as
    # directionally useful, not precise.
    model = SARIMAX(
        train,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 0, seasonal_period),
        enforce_stationarity=False,
        enforce_invertibility=False,
    ).fit(disp=False)
    forecast = model.get_forecast(steps=test_size).predicted_mean
    forecast.index = test.index

    naive = train.iloc[-seasonal_period:].to_numpy()
    naive_forecast = np.resize(naive, test_size)

    return {
        "train": train,
        "test": test,
        "forecast": forecast,
        "naive_forecast": pd.Series(naive_forecast, index=test.index),
        "model_mae": mean_absolute_error(test, forecast),
        "model_rmse": mean_squared_error(test, forecast) ** 0.5,
        "naive_mae": mean_absolute_error(test, naive_forecast),
        "naive_rmse": mean_squared_error(test, naive_forecast) ** 0.5,
    }


def plot_backtest(grain: str, result: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    result["train"].iloc[-3 * len(result["test"]) :].plot(ax=ax, label="train (recent)", color="black")
    result["test"].plot(ax=ax, label="actual (held out)", color="black", linestyle="--", marker="o")
    result["forecast"].plot(ax=ax, label="SARIMAX forecast", color="tab:blue", marker="o")
    result["naive_forecast"].plot(ax=ax, label="seasonal-naive baseline", color="tab:orange", linestyle=":")
    ax.set_title(f"Sales forecast backtest ({grain} granularity)")
    ax.set_ylabel("Net sales")
    ax.legend()
    fig.tight_layout()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "sales_forecast_backtest.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved backtest plot to {out_path}")


def main() -> None:
    engine = get_engine()
    daily = load_daily_sales(engine)
    print(f"Loaded {len(daily)} days of net sales ({daily.index.min().date()} to {daily.index.max().date()})")

    grain, series, seasonal_period = choose_granularity(daily)

    # Held out: ~3 seasonal cycles' worth of a quarter -- 12 weeks or 3 months,
    # whichever grain was chosen -- leaving enough train history for the
    # model to see at least one full seasonal cycle before the holdout.
    test_size = 12 if grain == "weekly" else 3
    result = backtest(series, seasonal_period, test_size)

    print(f"\nBacktest on last {test_size} {grain[:-2] if grain == 'weekly' else 'month'}(s)"
          f" ({result['test'].index.min().date()} to {result['test'].index.max().date()}):")
    print(f"  SARIMAX       : MAE={result['model_mae']:,.0f}  RMSE={result['model_rmse']:,.0f}")
    print(f"  Seasonal-naive: MAE={result['naive_mae']:,.0f}  RMSE={result['naive_rmse']:,.0f}")
    if result["model_mae"] < result["naive_mae"]:
        print("-> SARIMAX beats the seasonal-naive baseline on this holdout.")
    else:
        print("-> WARNING: SARIMAX does NOT beat the seasonal-naive baseline here -- reporting honestly.")

    print("\nPer-period actual vs. forecast (model error, not just best case):")
    comparison = pd.DataFrame({
        "actual": result["test"],
        "forecast": result["forecast"],
        "abs_error": (result["test"] - result["forecast"]).abs(),
    }).round(0)
    print(comparison.to_string())

    plot_backtest(grain, result)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(OUTPUT_DIR / "sales_forecast_backtest.csv")
    print(f"Saved backtest table to {OUTPUT_DIR / 'sales_forecast_backtest.csv'}")


if __name__ == "__main__":
    main()
