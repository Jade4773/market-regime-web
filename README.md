# Market Regime Web

William O'Neil-style market regime dashboard built with Streamlit.

Live app:

https://appapppy-cmks8kxu73qik7iqxaiux4.streamlit.app/

## Markets

- KOSPI 200
- KOSPI
- NASDAQ 100
- S&P 500

Daily price data comes from Yahoo Finance. ETF volume proxies are used for
institutional-volume confirmation:

- KOSPI / KOSPI 200: `069500.KS`
- NASDAQ 100: `QQQ`
- S&P 500: `SPY`

## Signals

- Rally-attempt tracking and resets when the day-one low is undercut
- Follow-through day timing, quality, early distribution, and later failure
- Distribution days and stalling days
- Distribution expiration after 25 sessions or a 5% index rally
- Distribution clusters during the latest 11 sessions
- Combined market-wide regime

## Run Locally

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The deployed Streamlit app has no account or password screen. Anyone with the
app URL can access the dashboard.
