# Lead Finder (Google Maps Scraper)

Flask app that scrapes Google Maps with Playwright (Chromium) and exports results to CSV or Excel. No API key needed.

## Setup (Python 3.11.9)

### 1. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright Chromium

```bash
playwright install chromium
```

### 4. Run the Application

```bash
python app.py
```

Open your browser:

[http://127.0.0.1:5000](http://127.0.0.1:5000)

## How It Works

1. `scraper.py` opens `google.com/maps/search/<type> in <location>`, scrolls the results list and collects place links.
2. It then opens each place page and reads name, category, address, phone, website, rating, reviews, status and coordinates.
3. `app.py` runs this as a background job; the page polls for progress and shows rows as they arrive. You can press Stop and keep what was collected.

## Troubleshooting

- **Nothing loads / CAPTCHA:** Run with the browser visible to see what happens:

  Windows CMD:
  ```bash
  set HEADLESS=false
  python app.py
  ```

  macOS/Linux:
  ```bash
  HEADLESS=false python app.py
  ```

- **A field comes back empty for every place:** Google changed its markup. Update the selectors in `scraper.py` (`FEED`, `PLACE_LINK`, `EXTRACT_JS`).
- Expect roughly 3–5 seconds per business. Keep result counts modest and avoid rapid repeated runs to reduce the chance of being blocked.
- Emails are not shown on Google Maps, so they are not collected.

## Important

Scraping Google Maps is against Google's Terms of Service and can get your IP temporarily blocked. Use it for low-volume, personal research, and follow applicable data-protection and anti-spam laws when contacting businesses.

The official Places API is the compliant option.

## Deploying on Render

Chromium needs system libraries, so use **Docker**, not the native Python runtime.

1. Push this folder to GitHub.
2. Render → New → Web Service → Connect the repository → **Language: Docker** (it finds the `Dockerfile`).
3. Choose an instance with at least 1–2 GB RAM (Chromium often crashes on 512 MB).
4. Deploy. No environment variables are required.

### Native Python Runtime

If you must use the native Python runtime instead:

- Set `PYTHON_VERSION=3.11.9`.
- The `.python-version` file does this too.
- Chromium will still fail to launch there because system libraries cannot be installed.

**Note:** Google often shows CAPTCHAs to cloud/datacenter IPs, so scraping may work locally but fail on a server.
