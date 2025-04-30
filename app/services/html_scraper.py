import aiohttp
from selenium.webdriver import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from utils.logger import setup_logger
import os
from bs4 import BeautifulSoup
from selenium.common import WebDriverException, TimeoutException
from selenium import webdriver
from typing import Dict

SELENIUM_REMOTE_URL = os.getenv("SELENIUM_REMOTE_URL")
STATE = os.getenv("STATE")
logger = setup_logger("scraper")

async def get_cookies_from_website(url: str) -> Dict[str, str]:
    cookies_dict = {}
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.headless = True
        options.page_load_strategy = 'eager'
        driver = webdriver.Remote(
            command_executor=SELENIUM_REMOTE_URL,
            options=options
        )
        try:
            driver.get("https://businessfilings.sc.gov/BusinessFiling/Entity/Search")
            input_field = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.TAG_NAME, "input")))
            input_field.send_keys("moon")
            input_field.send_keys(Keys.RETURN)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,
                                                         "#EntitySearchResultsTable > tbody")))
            driver.execute_script(f"window.location.href='{url}';")
            cookies_raw = driver.get_cookies()
            cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies_raw}
        except TimeoutException as e:
            logger.error(f"Page load error {url}: {e}")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
    except Exception as e:
        logger.error(f"Ошибка при запуске Selenium: {e}")
    finally:
        if driver:
            driver.quit()
    return cookies_dict
async def fetch_company_details(url: str) -> dict:
    try:

        cookies = await get_cookies_from_website(url)
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                html = await response.text()
                return await parse_html_details(html)
    except Exception as e:
        logger.error(f"Error fetching data for query '{url}': {e}")
        return {}
async def fetch_company_data(query: str) -> list[dict]:
    url = "https://businessfilings.sc.gov/BusinessFiling/Entity/Search"
    payload = f"EntitySearchTypeEnumId=2&EntityName={query}&EntityNameIsRequired=True"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=payload) as response:
                response.raise_for_status()
                html = await response.text()
                return await parse_html_search(html)
    except Exception as e:
        logger.error(f"Error fetching data for query '{query}': {e}")
        return []

async def parse_html_search(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for row in soup.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) >= 5:
            link_tag = cols[0].find("a")
            if link_tag and link_tag.get("href"):
                results.append({
                    "state": STATE,
                    "name": link_tag.get_text(strip=True),
                    "status": cols[3].get_text(strip=True),
                    "url": "https://businessfilings.sc.gov" + link_tag["href"],
                })
    return results

async def parse_html_details(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    name = soup.find("legend").get_text(strip=True) if soup.find("legend") else None
    def get_params(label):
        tag = soup.find("span", string=label)
        return tag.find_next_sibling("span").get_text(strip=True) if tag else None

    expiration_date = get_params("Expiration Date")
    term_end_date = get_params("Term End Date")
    dissolved_date = get_params("Dissolved Date")
    status = get_params("Status")
    entity_type = get_params("Entity Type")
    registration_number = get_params("Entity ID")
    date_registered = get_params("Effective Date")
    agent_name = get_params("Agent")
    agent_address = get_params("Address")

    return {
        "state": STATE,
        "name": name,
        "status": status,
        "registration_number": registration_number,
        "date_registered": date_registered,
        "expiration_date": expiration_date,
        "term_end_date": term_end_date,
        "dissolved_date": dissolved_date,
        "entity_type": entity_type,
        "agent_name": agent_name,
        "agent_address": agent_address,
        "principal_address": None,
        "mailing_address": None,
        "document_images": []
    }