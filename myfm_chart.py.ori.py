# MYFM_chart.py


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

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()  # Load environment variables from .env file

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("myfm_chart.log"),
        logging.StreamHandler()
    ]
)

# Retrieve latest MY FM Music 20 chart and save JSON

def get_myfm_chart():
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')

        driver = webdriver.Chrome(options=options)
        driver.get("https://my.syok.my")

        logging.info("Fetching SYOK homepage to locate chart link...")
        chart_link = None
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href")
            if href and "charts/my-fm-music-chart" in href:
                chart_link = href
                break

        if not chart_link:
            logging.error("Unable to find chart link on homepage.")
            driver.quit()
            return []

        logging.info(f"Following chart link: {chart_link}")
        driver.get(chart_link)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "chart-listing--items"))
            )
        except TimeoutException:
            logging.error("Timeout waiting for chart items to load. The page may have changed.")
            driver.save_screenshot("debug_chart_timeout.png")
            with open("debug_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.quit()
            return []

        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        chart_data = []
        items = soup.select("li.chart-listing--items")

        if not items:
            logging.warning("No chart items found on the page. Site structure may have changed.")
            return []

        for item in items[:20]:
            rank_tag = item.find("span", class_="chart-listing--position")
            title_tag = item.find("h2", class_="chart-listing--song")
            artist_tag = item.find("h6", class_="chart-listing--artist")
            if not (rank_tag and title_tag and artist_tag):
                continue

            rank = int(rank_tag.text.strip())
            title = title_tag.text.strip()
            artist = artist_tag.text.strip()

            spotify_link = f"https://open.spotify.com/search/{title.replace(' ', '%20')}%20{artist.replace(' ', '%20')}"

            chart_data.append({
                "rank": rank,
                "title": title,
                "artist": artist,
                "spotify_link": spotify_link
            })

        if not chart_data:
            logging.warning("Chart list is empty after parsing HTML. Check page structure.")
            return []

        # Show preview before saving
        logging.info("Retrieved the following chart data:")
        for entry in chart_data:
            logging.info(f"#{entry['rank']}: {entry['title']} by {entry['artist']} - {entry['spotify_link']}")

        output_path = os.getenv('MYFM_LOCATION')
        if not output_path:
            raise ValueError("Environment variable 'MYFM_LOCATION' is not set.")

        filename = f"myfm_{datetime.now().strftime('%Y%m%d')}.json"
        full_path = os.path.join(output_path, filename)
        logging.info("Resolved full file path: %s", full_path)

        try:
            logging.info("Saving chart data to JSON before writing...")
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(chart_data, f, ensure_ascii=False, indent=2)
            logging.info("Chart data successfully written to: %s", full_path)
        except Exception as fe:
            logging.error("Failed to write file: %s", fe)

        return chart_data

    except WebDriverException as e:
        logging.error(f"Error retrieving chart data: WebDriverException - {e}")
        return []
    except Exception as e:
        logging.error(f"Error retrieving chart data: {e}")
        return []

def publish_to_blogger(content_html, title):
    TOKEN_PATH = "token.json"
    BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET") or "client_secret.json"
    BLOG_ID = os.getenv("BLOG_ID")
    if not BLOG_ID:
        raise ValueError("Environment variable 'BLOG_ID' is not set.")

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/blogger'])
    else:
        flow = InstalledAppFlow.from_client_secrets_file(BLOGGER_CLIENT_SECRET, scopes=['https://www.googleapis.com/auth/blogger'])
        creds = flow.run_local_server(port=8080)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    service = build('blogger', 'v3', credentials=creds)

    body = {
        "title": title,
        "content": content_html
    }

    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    logging.info(f"Published blog post: {post['title']}")
    return post

def generate_html_table(chart_data):
    html = '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:sans-serif;">'
    html += '<thead><tr style="background-color:#f2f2f2;"><th>排名</th><th>歌曲</th><th>歌手</th><th>Spotify 連結</th></tr></thead><tbody>'
    for entry in chart_data:
        html += f"<tr><td>{entry['rank']}</td><td>{entry['title']}</td><td>{entry['artist']}</td><td><a href='{entry['spotify_link']}' target='_blank'>🎵</a></td></tr>"
    html += '</tbody></table>'
    return html

if __name__ == "__main__":
    chart = get_myfm_chart()
    if chart:
        print(json.dumps(chart, indent=2, ensure_ascii=False))
        try:
            output_path = os.getenv('MYFM_LOCATION')
            filename = f"myfm_{datetime.now().strftime('%Y%m%d')}.json"
            full_path = os.path.join(output_path, filename)
            with open(full_path, 'r', encoding='utf-8') as f:
                chart_data = json.load(f)
            html_content = generate_html_table(chart_data)
            title = f"MY FM Music Chart - {datetime.now().strftime('%Y-%m-%d')}"
            publish_to_blogger(html_content, title)
        except Exception as e:
            logging.error(f"Failed to publish blog post: {e}")
    else:
        logging.warning("Chart retrieval failed or returned empty result.")
