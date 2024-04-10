import json, requests
from logger import LOGGER
from datetime import datetime
from odds_portal_scrapper import OddsPortalScrapper
from comparateur_de_cotes_scraper import FrenchOddsScrapper
from data_storage import DataStorage

def get_current_date_time_string():
    now = datetime.now()
    date_time_string = now.strftime('%Y-%m-%d %H:%M:%S')
    return date_time_string

def lambda_handler(event, context):
    LOGGER.info(f"Lambda handler called: {event} and context: {context}")

def get_odds_portal_historic_odds():
    season = "2022-2023"
    league_name = "ligue-1"
    file_path = f"{league_name}_{season}_{get_current_date_time_string()}.json"
    odds_portal_scrapper = OddsPortalScrapper(league=league_name)
    scrapped_historic_odds = odds_portal_scrapper.get_historic_odds(season=season)
    LOGGER.info(f"Historic odds have been scrapped: {scrapped_historic_odds}")
    flattened_historic_odds = [item for sublist in scrapped_historic_odds for item in sublist]
    storage = DataStorage(file_path)
    storage.append_data(flattened_historic_odds)

def scrape_odds_portal_next_matchs_odds():
    league_name = "ligue-1"
    odds_portal_scrapper = OddsPortalScrapper(league=league_name)
    odds_portal_scrapper.get_next_matchs_odds()

def scrape_french_bookamker_odds():
    league_name = "ligue-1"
    french_odds_scrapper = FrenchOddsScrapper(league=league_name)
    french_odds_scrapper.scrape_and_store_matches()

if __name__ == "__main__":
    get_odds_portal_historic_odds()