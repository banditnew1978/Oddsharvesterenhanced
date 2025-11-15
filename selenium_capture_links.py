import argparse
import csv
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.core.url_builder import URLBuilder
from src.utils.constants import ODDSPORTAL_BASE_URL


def _split_csv_argument(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture match links from OddsPortal using Selenium.")
    parser.add_argument("--sport", required=True)
    parser.add_argument("--leagues", required=True)
    parser.add_argument("--seasons", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--browser-user-agent", type=str, default=None)
    parser.add_argument("--browser-locale-timezone", type=str, default=None)
    parser.add_argument("--browser-timezone-id", type=str, default=None)
    return parser.parse_args()


def build_driver(headless: bool, user_agent: str | None, locale: str | None, timezone_id: str | None) -> webdriver.Chrome:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    if user_agent:
        chrome_options.add_argument(f"--user-agent={user_agent}")
    if locale:
        chrome_options.add_argument(f"--lang={locale}")
        chrome_options.add_experimental_option("prefs", {"intl.accept_languages": locale})
    driver = webdriver.Chrome(options=chrome_options)
    if timezone_id:
        try:
            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": timezone_id})
        except Exception:
            pass
    driver.set_page_load_timeout(30)
    return driver


def dismiss_cookie_banner(driver: webdriver.Chrome, timeout: int = 10) -> None:
    selectors = [
        "button#onetrust-accept-btn-handler",
        "button[aria-label*='Accept']",
        "button:contains('Accept')",
        "button:contains('I agree')",
        "button:contains('Got it')",
    ]
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            for sel in selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        el.click()
                        return
                except Exception:
                    continue
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for b in buttons:
                try:
                    txt = (b.text or "").strip().lower()
                    if any(k in txt for k in ["accept", "agree", "consent", "ok", "got it"]):
                        b.click()
                        return
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.5)


def set_odds_format(driver: webdriver.Chrome, timeout: int = 10) -> None:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.group > button.gap-2"))
        )
        btn = driver.find_element(By.CSS_SELECTOR, "div.group > button.gap-2")
        current = (btn.text or "").strip()
        if current.lower().startswith("decimal"):
            return
        btn.click()
        time.sleep(1.0)
        options = driver.find_elements(By.CSS_SELECTOR, "div.group > div.dropdown-content > ul > li > a")
        for opt in options:
            t = (opt.text or "").strip().lower()
            if "decimal" in t:
                opt.click()
                time.sleep(1.0)
                return
    except Exception:
        pass


def wait_dom_loaded(driver: webdriver.Chrome, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
    )


def scroll_until_loaded(driver: webdriver.Chrome, content_selector: str, timeout: int = 30, scroll_pause_time: float = 1.5, max_scroll_attempts: int = 3) -> bool:
    end_time = time.time() + timeout
    last_height = driver.execute_script("return document.body.scrollHeight")
    attempts = 0
    content_seen = False
    while time.time() < end_time:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, content_selector)
            if elems:
                content_seen = True
        except Exception:
            pass

        if new_height == last_height:
            attempts += 1
            # If we've seen content and height stopped changing for a while, stop scrolling
            if content_seen and attempts >= max_scroll_attempts:
                break
        else:
            attempts = 0
            last_height = new_height
    
    return True


def wait_for_hash(driver: webdriver.Chrome, expected_hash: str, timeout: int = 10) -> bool:
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            current_hash = driver.execute_script("return window.location.hash || ''")
            if current_hash == expected_hash:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def wait_for_event_rows(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, "div[class*='eventRow']")
            if elems:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def extract_match_links_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    event_rows = soup.find_all(class_=re.compile("^eventRow"))
    links = {
        f"{ODDSPORTAL_BASE_URL}{a['href']}"
        for row in event_rows
        for a in row.find_all("a", href=True)
        if len(a["href"].strip("/").split("/")) > 3
    }
    return list(links)


def get_first_event_signature(driver: webdriver.Chrome) -> str | None:
    try:
        # Try to capture the first event link href as a signature of page content
        elems = driver.find_elements(By.CSS_SELECTOR, "div[class*='eventRow'] a[href]")
        for el in elems:
            href = el.get_attribute("href") or ""
            # A match link usually contains more than 3 segments
            try:
                if len(href.strip("/").split("/")) > 3:
                    return href
            except Exception:
                continue
    except Exception:
        pass
    return None


def navigate_to_page(driver: webdriver.Chrome, target_page: int, timeout: int = 12) -> None:
    # Try clicking the pagination link with exact page text
    end_time = time.time() + timeout
    attempted_js_hash = False
    while time.time() < end_time:
        try:
            # Ensure pagination is in DOM
            page_links = driver.find_elements(By.CSS_SELECTOR, "a.pagination-link")
            for a in page_links:
                txt = (a.text or "").strip()
                if txt.isdigit() and int(txt) == target_page:
                    try:
                        driver.execute_script("arguments[0].click();", a)
                    except Exception:
                        a.click()
                    return
        except Exception:
            pass
        # As a fallback, try setting the hash directly once
        if not attempted_js_hash:
            try:
                driver.execute_script("window.location.hash = arguments[0];", f"#/page/{target_page}")
                attempted_js_hash = True
            except Exception:
                pass
        time.sleep(0.3)


def get_pagination_pages(driver: webdriver.Chrome, max_pages: int | None) -> list[int]:
    try:
        # Give the page a moment and a short scroll to trigger dynamic pagination render
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.2);")
            time.sleep(0.8)
        except Exception:
            pass

        # Wait for any pagination-related elements to appear
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_any_elements_located(
                    (
                        By.CSS_SELECTOR,
                        "a.pagination-link, nav[class*='pagination'], ul[class*='pagination']",
                    )
                )
            )
        except Exception:
            # continue with best-effort parsing
            pass

        pages: list[int] = []

        # First, try via direct elements
        try:
            link_elems = driver.find_elements(By.CSS_SELECTOR, "a.pagination-link:not([rel='next'])")
            for elem in link_elems:
                try:
                    t = (elem.text or "").strip()
                    if t.isdigit():
                        pages.append(int(t))
                except Exception:
                    continue
        except Exception:
            pass

        # Fallback: parse the page HTML for pagination numbers
        if not pages:
            try:
                html = driver.page_source
                soup = BeautifulSoup(html, "lxml")
                containers = soup.select("a.pagination-link, nav[class*='pagination'], ul[class*='pagination'] a")
                for c in containers:
                    txt = (c.get_text() or "").strip()
                    if txt.isdigit():
                        pages.append(int(txt))
            except Exception:
                pass

        if not pages:
            return [1]

        pages = sorted(set(pages))
        min_p, max_p = min(pages), max(pages)
        full = list(range(min_p, max_p + 1))
        if max_pages:
            return full[:max_pages]
        return full
    except Exception:
        return [1]


def save_collected_links(base_url: str, links: list[str]) -> None:
    if not links:
        return
    project_root = Path(__file__).resolve().parent
    capture_dir = project_root / "capturelinks"
    capture_dir.mkdir(parents=True, exist_ok=True)
    parsed_url = urlparse(base_url)
    base_slug = parsed_url.path.strip("/") or "links"
    sanitized_slug = base_slug.replace("/", "_").replace(" ", "-")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = capture_dir / f"{sanitized_slug}_{timestamp}.csv"
    with file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["match_link"])
        for link in sorted(set(links)):
            writer.writerow([link])


def capture_links_selenium(args: argparse.Namespace) -> None:
    logger = logging.getLogger("SeleniumCaptureLinks")
    leagues = _split_csv_argument(args.leagues)
    seasons = _split_csv_argument(args.seasons)
    if not leagues:
        raise ValueError("At least one league must be provided via --leagues.")
    if not seasons:
        raise ValueError("At least one season must be provided via --seasons.")

    driver = build_driver(
        headless=args.headless,
        user_agent=args.browser_user_agent,
        locale=args.browser_locale_timezone,
        timezone_id=args.browser_timezone_id,
    )

    try:
        for league in leagues:
            for season in seasons:
                logger.info(f"Capturing links for sport={args.sport} league={league} season={season}")
                base_url = URLBuilder.get_historic_matches_url(
                    sport=args.sport,
                    league=league,
                    season=season,
                )
                driver.get(base_url)
                wait_dom_loaded(driver, timeout=20)
                dismiss_cookie_banner(driver, timeout=8)
                set_odds_format(driver, timeout=8)
                # Small wait to ensure React pagination is rendered
                time.sleep(1.0)
                pages_to_scrape = get_pagination_pages(driver, max_pages=args.max_pages)
                all_links: list[str] = []
                for i, page_number in enumerate(pages_to_scrape, 1):
                    try:
                        logger.info(f"[{i}/{len(pages_to_scrape)}] Navigating to page {page_number}")
                        # Ensure event rows are present on initial page
                        wait_for_event_rows(driver, timeout=10)
                        prev_sig = get_first_event_signature(driver)

                        if page_number != 1:
                            navigate_to_page(driver, target_page=page_number, timeout=12)
                            # Wait for hash and rows
                            wait_for_hash(driver, expected_hash=f"#/page/{page_number}", timeout=8)
                            wait_for_event_rows(driver, timeout=10)
                            # Wait for content signature to change
                            sig_deadline = time.time() + 10
                            while time.time() < sig_deadline:
                                cur_sig = get_first_event_signature(driver)
                                if cur_sig and cur_sig != prev_sig:
                                    break
                                time.sleep(0.3)

                        time.sleep(random.randint(6, 8))
                        scroll_until_loaded(
                            driver,
                            content_selector="div[class*='eventRow']",
                            timeout=30,
                            scroll_pause_time=2,
                            max_scroll_attempts=3,
                        )
                        html = driver.page_source
                        links = extract_match_links_from_html(html)
                        all_links.extend(links)
                    except Exception as e:
                        logger.error(f"Error on page {page_number}: {e}")
                unique_links = list(set(all_links))
                save_collected_links(base_url=base_url, links=unique_links)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    capture_links_selenium(args)


if __name__ == "__main__":
    main()
