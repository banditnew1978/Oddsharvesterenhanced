"""Utility script to capture OddsPortal match links without scraping odds data."""

import argparse
import asyncio
import logging

from src.core.browser_helper import BrowserHelper
from src.core.odds_portal_market_extractor import OddsPortalMarketExtractor
from src.core.odds_portal_scraper import OddsPortalScraper
from src.core.playwright_manager import PlaywrightManager
from src.core.sport_market_registry import SportMarketRegistrar
from src.core.url_builder import URLBuilder
from src.utils.setup_logging import setup_logger


def _split_csv_argument(raw: str) -> list[str]:
    """Split a comma-separated argument into a cleaned list."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture match links from OddsPortal.")
    parser.add_argument("--sport", required=True, help="Sport identifier (e.g., football, basketball)")
    parser.add_argument(
        "--leagues",
        required=True,
        help="Comma-separated list of league slugs (e.g., england-premier-league,spain-primera-division).",
    )
    parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated list of seasons (e.g., 2014-2015,2015-2016).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (recommended for automation).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional limit on the number of pages to inspect per season.",
    )
    parser.add_argument(
        "--browser-user-agent",
        type=str,
        default=None,
        help="Optional custom user agent for the Playwright browser.",
    )
    parser.add_argument(
        "--browser-locale-timezone",
        type=str,
        default=None,
        help="Optional locale timezone for the Playwright browser (e.g., fr-BE).",
    )
    parser.add_argument(
        "--browser-timezone-id",
        type=str,
        default=None,
        help="Optional timezone ID for the Playwright browser (e.g., Europe/Paris).",
    )

    return parser.parse_args()


async def capture_links(args: argparse.Namespace) -> None:
    logger = logging.getLogger("CaptureLinks")

    leagues = _split_csv_argument(args.leagues)
    seasons = _split_csv_argument(args.seasons)

    if not leagues:
        raise ValueError("At least one league must be provided via --leagues.")
    if not seasons:
        raise ValueError("At least one season must be provided via --seasons.")

    SportMarketRegistrar.register_all_markets()

    playwright_manager = PlaywrightManager()
    browser_helper = BrowserHelper()
    market_extractor = OddsPortalMarketExtractor(browser_helper=browser_helper)

    scraper = OddsPortalScraper(
        playwright_manager=playwright_manager,
        browser_helper=browser_helper,
        market_extractor=market_extractor,
    )

    await scraper.start_playwright(
        headless=args.headless,
        browser_user_agent=args.browser_user_agent,
        browser_locale_timezone=args.browser_locale_timezone,
        browser_timezone_id=args.browser_timezone_id,
    )

    try:
        current_page = playwright_manager.page
        if current_page is None:
            raise RuntimeError("Playwright page was not initialized correctly.")

        for league in leagues:
            for season in seasons:
                logger.info("Capturing links for sport=%s league=%s season=%s", args.sport, league, season)

                base_url = URLBuilder.get_historic_matches_url(
                    sport=args.sport,
                    league=league,
                    season=season,
                )

                await current_page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
                await scraper._prepare_page_for_scraping(page=current_page)

                pages_to_scrape = await scraper._get_pagination_info(
                    page=current_page,
                    max_pages=args.max_pages,
                )

                await scraper._collect_match_links(base_url=base_url, pages_to_scrape=pages_to_scrape)

                logger.info("Finished capturing links for %s %s %s", args.sport, league, season)

    finally:
        await scraper.stop_playwright()


def main() -> None:
    args = parse_args()
    setup_logger(log_level=logging.INFO, save_to_file=False)

    asyncio.run(capture_links(args))


if __name__ == "__main__":
    main()
