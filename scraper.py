"""Google Maps scraper built on Playwright (no API key needed).

NOTE: Google can change its page markup at any time, which will break the
selectors below. Scraping may also violate Google's Terms of Service.
"""
import random
import re
import urllib.parse

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
COORD_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
ID_RE = re.compile(r"!1s([^!?&]+)")
CARD_SELECTOR = 'div[role="feed"] a[href*="/maps/place/"]'


class ScrapeError(Exception):
    pass


def _accept_consent(page):
    """Click through Google's cookie/consent screen if it appears."""
    for label in ("Accept all", "Reject all", "I agree"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click(timeout=2500)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue


def _attr(page, selector, attribute):
    try:
        loc = page.locator(selector)
        if loc.count():
            return (loc.first.get_attribute(attribute, timeout=1500) or "").strip()
    except Exception:
        pass
    return ""


def _text(page, selector):
    try:
        loc = page.locator(selector)
        if loc.count():
            return loc.first.inner_text(timeout=1500).strip()
    except Exception:
        pass
    return ""


def _strip_label(value):
    """aria-labels look like 'Phone: 0300 1234567' -> '0300 1234567'."""
    return value.split(":", 1)[1].strip() if ":" in value else value.strip()


def _collect_cards(page, limit, progress):
    """Scroll the results feed and collect (name, href) for each business."""
    cards = {}
    try:
        page.wait_for_selector('div[role="feed"]', timeout=15000)
    except PWTimeout:
        # Google sometimes jumps straight to a single place page.
        if "/maps/place/" in page.url:
            return [{"name": "", "href": page.url}]
        return []

    stale_rounds = 0
    while len(cards) < limit and stale_rounds < 4:
        items = page.eval_on_selector_all(
            CARD_SELECTOR,
            "els => els.map(e => ({href: e.href, name: e.getAttribute('aria-label') || ''}))",
        )
        before = len(cards)
        for it in items:
            if it["href"] and it["href"] not in cards:
                cards[it["href"]] = it["name"]
        progress(f"Found {min(len(cards), limit)} businesses so far...")
        if page.get_by_text("You've reached the end of the list").count():
            break
        stale_rounds = stale_rounds + 1 if len(cards) == before else 0
        page.locator('div[role="feed"]').evaluate("el => el.scrollBy(0, el.scrollHeight)")
        page.wait_for_timeout(1500)
    return [{"name": n, "href": h} for h, n in list(cards.items())[:limit]]


def _scrape_place(page, card):
    href = card["href"]
    page.goto(href, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("h1", timeout=10000)
    except PWTimeout:
        pass
    page.wait_for_timeout(900)

    name = card["name"] or _text(page, "h1.DUwDvf") or _text(page, "h1")
    coord = COORD_RE.search(href) or COORD_RE.search(page.url)
    place_id = ID_RE.search(href)
    main = page.locator('div[role="main"]')

    status = "Operational"
    try:
        if main.get_by_text("Permanently closed").count():
            status = "Permanently Closed"
        elif main.get_by_text("Temporarily closed").count():
            status = "Temporarily Closed"
    except Exception:
        pass

    rating = _text(page, 'div.F7nice span[aria-hidden="true"]')
    reviews = re.sub(
        r"[^\d]", "", _attr(page, 'div.F7nice span[aria-label*="review"]', "aria-label")
    )
    if not rating:  # fallback: "4.5 stars" image label
        m = re.search(r"([\d.]+)\s*stars?", _attr(page, '[role="img"][aria-label*="star"]', "aria-label"))
        rating = m.group(1) if m else ""

    return {
        "id": place_id.group(1) if place_id else href,
        "name": name,
        "category": _text(page, 'button[jsaction*="category"]'),
        "address": _strip_label(_attr(page, 'button[data-item-id="address"]', "aria-label")),
        "phone": _strip_label(_attr(page, 'button[data-item-id^="phone:tel:"]', "aria-label")),
        "website": _attr(page, 'a[data-item-id="authority"]', "href"),
        "rating": rating,
        "reviews": reviews,
        "status": status,
        "maps_url": href,
        "latitude": coord.group(1) if coord else "",
        "longitude": coord.group(2) if coord else "",
    }


def scrape_google_maps(keyword, location, max_results, headless=True, progress=lambda m: None):
    """Return a list of business dicts scraped from Google Maps."""
    query = urllib.parse.quote_plus(f"{keyword} in {location}")
    url = f"https://www.google.com/maps/search/{query}?hl=en"
    results, seen = [], set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=["--lang=en-US"])
        try:
            ctx = browser.new_context(
                user_agent=USER_AGENT, locale="en-US", viewport={"width": 1280, "height": 900}
            )
            page = ctx.new_page()
            progress("Opening Google Maps...")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _accept_consent(page)

            if "/sorry/" in page.url or page.locator("iframe[src*='recaptcha']").count():
                raise ScrapeError("Google is showing a CAPTCHA / block page. Try again later.")

            cards = _collect_cards(page, max_results, progress)
            if not cards:
                return []

            for i, card in enumerate(cards, start=1):
                progress(f"Reading details {i}/{len(cards)}...")
                try:
                    row = _scrape_place(page, card)
                except Exception:
                    continue  # skip a place that fails, keep going
                if row["id"] in seen or not row["name"]:
                    continue
                seen.add(row["id"])
                results.append(row)
                page.wait_for_timeout(int(random.uniform(400, 1100)))
        except PWTimeout:
            raise ScrapeError("Google Maps took too long to load. Try again.")
        finally:
            browser.close()
    return results
