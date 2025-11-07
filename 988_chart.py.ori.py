# 988_chart.py

import os
import json
import logging
from datetime import datetime
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("988_chart.log"),
        logging.StreamHandler()
    ]
)

def get_988_chart():
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')

        driver = webdriver.Chrome(options=options)
        chart_url = "https://988.com.my/music_chart/"
        driver.get(chart_url)

        time.sleep(3)  # Allow modal to load
        try:
            modal_close_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".modal-close-button, .modal-close, .login-modal .close"))
            )
            modal_close_button.click()
            logging.info("Login modal closed.")
        except TimeoutException:
            logging.info("No login modal appeared.")
        except Exception as e:
            logging.warning(f"Unexpected error trying to close login modal: {e}")

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.song-container"))
            )
        except TimeoutException:
            logging.error("Timeout waiting for 988 chart items to load. The page may have changed.")
            driver.save_screenshot("debug_988_chart_timeout.png")
            with open("debug_988_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.quit()
            return []

        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        chart_data = []
        items = soup.select("div.song-container")

        if not items:
            logging.warning("No 988 chart items found on the page. Site structure may have changed.")
            return []

        for item in items[:20]:
            rank_tag = item.select_one("p.ranking-text")
            title_artist_tag = item.select_one("p.song-title.music-chart-song-title")
            artist_tag = item.select_one("p.artist-name")

            if not rank_tag or not title_artist_tag or not artist_tag:
                continue

            try:
                rank = int(rank_tag.text.strip())
            except ValueError:
                continue

            full_title = title_artist_tag.text.strip()
            artist = artist_tag.text.strip()

            if '｜' in full_title:
                title, _ = full_title.split('｜', 1)
                title = title.strip()
            else:
                title = full_title

            spotify_link = f"https://open.spotify.com/search/{title.replace(' ', '%20')}%20{artist.replace(' ', '%20')}"

            chart_data.append({
                "rank": rank,
                "title": title,
                "artist": artist,
                "spotify_link": spotify_link
            })

        if not chart_data:
            logging.warning("988 chart list is empty after parsing HTML. Check page structure.")
            return []

        logging.info("Retrieved the following 988 chart data:")
        for entry in chart_data:
            logging.info(f"#{entry['rank']}: {entry['title']} by {entry['artist']} - {entry['spotify_link']}")

        output_path = os.getenv('988_LOCATION')
        if not output_path:
            raise ValueError("Environment variable '988_LOCATION' is not set.")

        filename = f"988_{datetime.now().strftime('%Y%m%d')}.json"
        full_path = os.path.join(output_path, filename)
        logging.info("Resolved full file path: %s", full_path)

        try:
            logging.info("Saving 988 chart data to JSON before writing...")
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(chart_data, f, ensure_ascii=False, indent=2)
            logging.info("988 chart data successfully written to: %s", full_path)
        except Exception as fe:
            logging.error("Failed to write file: %s", fe)

        return chart_data

    except WebDriverException as e:
        logging.error(f"Error retrieving 988 chart data: WebDriverException - {e}")
        return []
    except Exception as e:
        logging.error(f"Error retrieving 988 chart data: {e}")
        return []

if __name__ == "__main__":
    chart = get_988_chart()
    if chart:
        print(json.dumps(chart, indent=2, ensure_ascii=False))
    else:
        logging.warning("988 chart retrieval failed or returned empty result.")
