# Market Regime Web

William O'Neil-style market regime dashboard built with Streamlit.

Live app:

https://appapppy-cmks8kxu73qik7iqxaiux4.streamlit.app/

## Markets

- KOSPI 200
- KOSPI
- NASDAQ Composite
- S&P 500

Daily price data comes from Yahoo Finance. If Yahoo Finance lags or returns
empty latest rows for Korean indexes, KOSPI and KOSPI 200 are automatically
extended with Npay Securities index data and labeled in the UI.

ETF volume proxies are used for institutional-volume confirmation:

- KOSPI / KOSPI 200: `069500.KS`
- NASDAQ Composite: `QQQ`
- S&P 500: `SPY`

## Signals

- Rally-attempt tracking and resets when the day-one low is undercut
- Follow-through day timing, quality, early distribution, and later failure
- Distribution days and stalling days
- Distribution expiration after 25 sessions or a 5% index rally
- Distribution clusters during the latest 11 sessions
- Combined market-wide regime
- Separate Korea and U.S. regime summaries
- A valid follow-through day on either the Nasdaq Composite or S&P 500 can confirm the U.S. rally

## Project Structure

```text
streamlit_app.py        Streamlit Cloud entry point
market_pulse/
  data.py               Yahoo Finance and Npay Securities data loading
  rules.py              William O'Neil, trend, risk, and consensus rules
  ui.py                 Streamlit screens, cards, tabs, and styling
  __init__.py           Python package marker
.streamlit/config.toml  Streamlit runtime configuration
requirements.txt        Python dependencies
```

The root folder intentionally stays small. Most feature work should happen
inside `market_pulse/`.

## Run Locally

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The deployed Streamlit app has no account or password screen. Anyone with the
app URL can access the dashboard.
