# Market Regime Web

William O'Neil-style market regime dashboard built with Streamlit.

Live app:

https://appapppy-cmks8kxu73qik7iqxaiux4.streamlit.app/

## Markets

- KOSPI 200
- KOSPI
- NASDAQ Composite
- S&P 500

Daily price data is loaded in this priority order:

1. Korea Investment & Securities Open API, when credentials are configured
2. Npay Securities for Korean indexes
3. Yahoo Finance

If Korea Investment credentials are missing or an API call fails, the app
automatically falls back to Npay/Yahoo and labels the active source in the UI.

For Korea Investment & Securities Open API, add these values to Streamlit
Secrets or environment variables:

```toml
KIS_APP_KEY = "..."
KIS_APP_SECRET = "..."
KIS_ENV = "prod" # optional: prod or demo
```

Korea Investment index codes used by the app:

- KOSPI: `0001`
- KOSPI 200: `2001`
- NASDAQ Composite: `.IXIC` by default, override with `KIS_IXIC_CODE` if needed
- S&P 500: `.SPX` by default, override with `KIS_GSPC_CODE` if needed

ETF volume proxies are used when the active source is Yahoo Finance:

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

## Product Candidates

The `상품 추천` tab shows two rule-based candidate areas:

- Korea Investment & Securities index-linked ELS candidates, when the public
  subscription screen can be read. If the screen requires a login session or is
  blocked, the app shows official ELS subscription links instead.
- ETF candidates derived from the William O'Neil signal already calculated for
  each index. Candidates are split into Korea-listed ETFs and U.S.-listed ETFs,
  and include the investment country and tracked or proxy index.

This tab is not personalized investment advice. It does not consider investor
suitability, account type, tax, FX cost, fees, liquidity, or product risk grade.

## Project Structure

```text
streamlit_app.py        Streamlit Cloud entry point
market_pulse/
  data.py               Yahoo Finance and Npay Securities data loading
  products.py           ELS and ETF candidate logic
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
