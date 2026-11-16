"""
Lead Generation Tool
Flask backend that scrapes business listings from Google Maps (Playwright,
no API key) and exports the results as CSV or Excel (.xlsx).
"""

import csv
import io
import os
import threading
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from scraper import ScrapeError, scrape_google_maps

load_dotenv()

app = Flask(__name__)

HEADLESS = os.getenv("HEADLESS", "true").strip().lower() != "false"
MAX_RESULTS_CAP = 60
JOB_TTL = 60 * 60  # keep finished jobs for 1 hour

JOBS = {}  # job_id -> {"state", "message", "results", "error", "ts"}
JOBS_LOCK = threading.Lock()
SCRAPE_LOCK = threading.Lock()  # only one browser scrape at a time

# Column definitions shared by CSV and Excel exports: (key, header)
COLUMNS = [
    ("name", "Business Name"),
    ("category", "Category"),
    ("address", "Address"),
    ("phone", "Phone"),
    ("website", "Website"),
    ("rating", "Rating"),
    ("reviews", "Reviews"),
    ("status", "Status"),
    ("maps_url", "Google Maps URL"),
    ("latitude", "Latitude"),
    ("longitude", "Longitude"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def safe_cell(value):
    """Neutralise spreadsheet formula injection (=, +, -, @ at cell start)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def timestamped(name: str, ext: str) -> str:
    return f"{name}_{datetime.now():%Y%m%d_%H%M%S}.{ext}"


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def purge_jobs():
    now = time.time()
    with JOBS_LOCK:
        for k in [k for k, v in JOBS.items() if now - v["ts"] > JOB_TTL]:
            JOBS.pop(k, None)


def run_job(job_id, keyword, location, max_results):
    def progress(msg):
        JOBS[job_id]["message"] = msg

    with SCRAPE_LOCK:
        try:
            rows = scrape_google_maps(
                keyword, location, max_results, headless=HEADLESS, progress=progress
            )
            JOBS[job_id].update(state="done", results=rows, message="Done")
        except ScrapeError as exc:
            JOBS[job_id].update(state="error", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            JOBS[job_id].update(
                state="error",
                error=f"Scraper failed: {exc}. Is Chromium installed? Run: playwright install chromium",
            )
    JOBS[job_id]["ts"] = time.time()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/search")
def search():
    data = request.get_json(silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    location = (data.get("location") or "").strip()

    if not keyword or not location:
        return jsonify(error="Enter both a business type and a location."), 400
    if len(keyword) > 100 or len(location) > 100:
        return jsonify(error="Keyword and location must be under 100 characters."), 400

    try:
        max_results = int(data.get("max_results", 20))
    except (TypeError, ValueError):
        max_results = 20
    max_results = max(1, min(max_results, MAX_RESULTS_CAP))

    if SCRAPE_LOCK.locked():
        return jsonify(error="Another search is still running. Please wait for it to finish."), 429

    purge_jobs()
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"state": "running", "message": "Starting...", "results": [], "error": "", "ts": time.time()}
    threading.Thread(target=run_job, args=(job_id, keyword, location, max_results), daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="Search not found or expired."), 404
    if job["state"] == "error":
        return jsonify(state="error", error=job["error"])
    if job["state"] == "done":
        return jsonify(state="done", count=len(job["results"]), results=job["results"])
    return jsonify(state="running", message=job["message"])


def _rows_from_request():
    data = request.get_json(silent=True) or {}
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        return None
    return [r for r in rows if isinstance(r, dict)]


@app.post("/api/export/csv")
def export_csv():
    rows = _rows_from_request()
    if rows is None:
        return jsonify(error="No results to export."), 400

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for _, header in COLUMNS])
    for row in rows:
        writer.writerow([safe_cell(row.get(key, "")) for key, _ in COLUMNS])

    # utf-8-sig adds a BOM so Excel opens non-ASCII names correctly.
    output = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name=timestamped("leads", "csv"),
    )


@app.post("/api/export/xlsx")
def export_xlsx():
    rows = _rows_from_request()
    if rows is None:
        return jsonify(error="No results to export."), 400

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"

    ws.append([header for _, header in COLUMNS])
    for row in rows:
        ws.append([safe_cell(row.get(key, "")) for key, _ in COLUMNS])

    # Header styling, frozen header row, filters and column widths
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for idx, (key, header) in enumerate(COLUMNS, start=1):
        longest = max(
            [len(header)] + [len(str(r.get(key, ""))) for r in rows]
        )
        ws.column_dimensions[get_column_letter(idx)].width = min(longest + 2, 60)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=timestamped("leads", "xlsx"),
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), threaded=True)
