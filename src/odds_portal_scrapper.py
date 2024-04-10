import time, re, random
from utils import LEAGUES_URLS_MAPPING
from data_storage import DataStorage
from logger import LOGGER
from bs4 import BeautifulSoup
from odds_portal_odds_extractor import OddsPortalOddsExtractor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

class OddsPortalScrapper:
    def __init__(self, league: str):
        self.league = league
        self.__initialize_webdriver()
    
    def __initialize_webdriver(self):
        chrome_options = webdriver.ChromeOptions()
        #chrome_options.add_argument("--headless")
        chrome_options.add_argument("--unlimited-storage")
        chrome_options.add_argument("--full-memory-crash-report")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.driver.set_window_size(1800, 2500)

    """Scrolls down the page in a loop until no new content is loaded or a timeout is reached."""
    def __scroll_until_loaded(self, timeout=30, scroll_pause_time=1.5):
        end_time = time.time() + timeout
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            new_height = self.driver.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                break

            last_height = new_height
            if time.time() > end_time:
                break

    def __get_base_url(self, season: str) -> str:
        base_url = LEAGUES_URLS_MAPPING.get(self.league)
        if not base_url:
            raise ValueError(f"URL mapping not found for league: {self.league}")
        else:
            try:
                season_components = season.split("-")
                return f"{base_url}-{season_components[0]}-{season_components[1]}/results/"
            except IndexError:
                raise ValueError(f"Invalid season format: {season}. Expected format: 'YYYY-YYYY'")

    def __set_odds_format(self, odds_format: str = "EU Odds"):
        LOGGER.info(f"Set Odds Format {odds_format}")
        try:
            button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.group > button.gap-2")))
            button.click()
            time.sleep(2)            
            formats = self.driver.find_elements(By.CSS_SELECTOR, "div.group > div.dropdown-content > ul > li > a")
            for f in formats:
                if f.text == odds_format:
                    f.click()
                    LOGGER.info(f"Odds format changed")
                    break
        except TimeoutException:
            LOGGER.warn(f"Odds have not been changed: May be because odds are already set in the required format")
    
    def __get_match_links(self):
        LOGGER.info("Fetching match links")
        html_content = self.driver.page_source
        soup = BeautifulSoup(html_content, 'lxml')
        event_rows = soup.find_all(class_=re.compile("^eventRow"))
        hrefs = []
        for row in event_rows:
            links = row.find_all('a', href=True)
            for link in links:
                hrefs.append(link['href'])
        return hrefs
    
    def __scrape_match_data(self, match_link):
        LOGGER.info(f"Will scrape match url: {match_link}")
        self.driver.get(f"https://www.oddsportal.com{match_link}")
        time.sleep(2)

        try:
            date_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div.bg-event-start-time ~ p')
            team_elements = self.driver.find_elements(By.CSS_SELECTOR, 'span.truncate')

            if not date_elements or not team_elements:
                raise NoSuchElementException("Not on the expected page.")
            
            day, date, time_value = [element.text for element in date_elements]
            homeTeam, awayTeam = [element.text for element in team_elements]
            odds_extractor = OddsPortalOddsExtractor(self.driver)                
            ft_1x2_odds_data = odds_extractor.extract_1X2_odds(period="FullTime")
            #over_under_1_5_odds_data = odds_extractor.extract_over_under_odds(over_under_type_chosen="1.5", period="FullTime")
            #over_under_2_5_odds_data = odds_extractor.extract_over_under_odds(over_under_type_chosen="2.5", period="FullTime")
            #double_chance_odds_data = odds_extractor.extract_double_chance_odds(period="FullTime")
            scrapped_data = {
                "date": date,
                "homeTeam": homeTeam,
                "awayTeam": awayTeam,
                "ft_1x2_odds_data": ft_1x2_odds_data
            }
            return scrapped_data
        except NoSuchElementException as e:
            LOGGER.warn(f"Elements not found on page: {match_link}. Possibly not the correct page. Error: {e}")
            return None

    def __extract_matchs_data(self):
        odds_data = []
        self.__scroll_until_loaded()
        time.sleep(random.uniform(3, 5))
        try:
            match_links = self.__get_match_links()
            match_pattern = re.compile(r'.+-[A-Za-z0-9]+/$') # Filter hrefs to only include those with a detailed path (assumed to contain team names)
            filtered_match_links = [href for href in match_links if match_pattern.match(href)] # Ex link: /football/france/ligue-1-2022-2023/toulouse-auxerre-xvkheAlf/

            if not filtered_match_links:
                raise ValueError(f"No matches links found, plese check. match_links: {match_links} - filtered_match_links: {filtered_match_links}")
            LOGGER.info(f"After filtering fetched matches, remaining links: {len(filtered_match_links)}")

            ## TODO: For testing purpose only scrape the first 3 matchs
            #for link in filtered_match_links[:3]:
            for link in filtered_match_links:
                match_data = self.__scrape_match_data(match_link=link)
                if match_data:
                    odds_data.append(match_data)
        except Exception as e:
            LOGGER.error(f"While extracting data: {e}")
        finally:
            return odds_data
    
    def __scrape_odds(self):
        try:
            self.__set_odds_format()
            data = self.__extract_matchs_data()
            return data
        except Exception as e:
            LOGGER.error(f"Extracting data or setting odds format: {e}")

    def __scrape_odds_historic(self, nbr_of_pages: int = None):
        historic_odds = []
        pagination_links = self.driver.find_elements(By.CSS_SELECTOR, "a.pagination-link")
        pages = [link.text for link in pagination_links]

        if nbr_of_pages is None:
            max_pages_to_scrape = len(pages)
        else:
            max_pages_to_scrape = min(nbr_of_pages, len(pages))

        current_url = self.driver.current_url
        for page in pages[:max_pages_to_scrape]:
            if page != 'Next':
                page_url = f"{current_url}#/page/{page}"
                LOGGER.info(f"Page_url: {page_url}")
                try:
                    self.driver.get(page_url)
                    time.sleep(random.uniform(2, 5))
                    odds_data = self.__scrape_odds()
                    historic_odds.append(odds_data)
                except Exception as error:
                    LOGGER.error(f"error: {error}")
        return historic_odds

    def get_historic_odds(self, season: str, nbr_of_pages: int = None):
        LOGGER.info(f"Will grab historic odds for season: {season}")
        try:
            base_url = self.__get_base_url(season=season)
            self.driver.get(base_url)
            historic_odds = self.__scrape_odds_historic(nbr_of_pages=nbr_of_pages)
            return historic_odds
        except Exception as error:
            LOGGER.error(f"Error: {error}")
        finally:
            self.driver.quit()
    
    def get_next_matchs_odds(self):
        LOGGER.info(f"Will grab next matchs odds")