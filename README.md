# Market Regime Web

KOSPI, KOSPI 200, NASDAQ 100, S&P 500 indices are downloaded from Yahoo Finance and evaluated with a William O'Neil style follow-through day and distribution day framework.

Live Streamlit app:

https://appapppy-cmks8kxu73qik7iqxaiux4.streamlit.app/

## What It Does

- Password login for a small allow-list of users.
- Users can change their own passwords.
- The administrator can reset passwords and enable or disable users.
- Fetches daily close, volume, and traded value proxy from Yahoo Finance's chart endpoint.
- Shows market status for:
  - KOSPI: `^KS11`
  - KOSPI 200: `^KS200`
  - NASDAQ 100: `^NDX`
  - S&P 500: `^GSPC`
- Detects:
  - Follow-through days
  - Rally-attempt resets when the day-one low is undercut
  - Follow-through quality based on timing, early distribution, and later failure
  - Distribution days
  - Stalling days
  - Distribution clusters in the latest 11 sessions
  - Distribution-day expiration after 25 sessions or a 5% index rally
  - Current buy, caution, or sell regime

## Streamlit

Run locally:

```powershell
streamlit run streamlit_app.py
```

For Streamlit Community Cloud, set the main file path to:

```text
streamlit_app.py
```

Add this secret in the Streamlit app settings:

```toml
USERS_JSON = "output from: python manage_users.py json"
CACHE_SECONDS = "900"
```

## Setup

```powershell
cd market_regime_web
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage_users.py add yourname
python app.py
```

Open `http://127.0.0.1:5000`.

## Open On Your Network

Run the network server:

```powershell
.\run_network_server.ps1
```

Then open the computer's network address from Chrome or Edge:

```text
http://YOUR_COMPUTER_IP:5000
```

For internet access outside your home or office network, you still need HTTPS hosting, a VPN/tunnel, or router/firewall port forwarding.

## User Access

Users are stored in `data/users.json`. Add up to about 20 people with:

```powershell
python manage_users.py add username
```

Or create one non-interactively:

```powershell
python manage_users.py add username --password "change-this-password"
```

Disable a user:

```powershell
python manage_users.py disable username
```

## Deployment Notes

For real web access, deploy this behind HTTPS. A simple low-maintenance path is Render, Railway, Fly.io, or a small VPS.

Set these environment variables on the server:

- `SECRET_KEY`: long random string
- `USERS_FILE`: optional path to users JSON
- `USERS_JSON`: optional full user list JSON, best for free hosting where files are not persistent
- `CACHE_SECONDS`: optional Yahoo Finance cache duration

Do not commit `.env` or `data/users.json` if they contain real access details.

## Render Free Deployment

1. Put this folder in a GitHub repository.
2. Create a Render account.
3. New > Web Service > connect the repository.
4. Use these settings:
   - Build command: `pip install -r requirements.txt`
   - Start command: `waitress-serve --host=0.0.0.0 --port=$PORT app:app`
   - Health check path: `/health`
5. Add environment variables:
   - `SECRET_KEY`: any long random string
   - `CACHE_SECONDS`: `900`
   - `USERS_JSON`: output from `python manage_users.py json`

## Important Caveat

O'Neil's follow-through and distribution day rules have interpretive details. This app uses explicit, editable defaults in `market_rules.py`, so you can adjust thresholds as your preferred reading of the method evolves.
