import os
import json
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def scrape_eightfm_chart():
    url = "https://www.eight.audio/eight-fm-20好听榜/"
    output_path = os.getenv("EIGHT_LOCATION")

    if not output_path:
        raise ValueError("Environment variable 'EIGHT_LOCATION' is not set.")

    # Setup Selenium
    options = Options()
    HEADLESS = False  # Set to False to run browser in non-headless mode for debugging
    if HEADLESS:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,3000")
    driver = webdriver.Chrome(options=options)

    logging.info("Opening EIGHT FM chart page...")
    driver.get(url)

    try:
        # Wait for today-list-wrapper elements to appear
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "today-list-wrapper"))
        )
    except Exception as e:
        logging.warning(f"Wait for today-list-wrapper failed: {e}")
        logging.info("Falling back to wait for body element...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception as e2:
            logging.error(f"Wait for body element also failed: {e2}")

    time.sleep(2)  # Additional wait for full rendering

    # Check for iframes and switch to first iframe if present
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if iframes:
        logging.info(f"Found {len(iframes)} iframe(s), switching to the first one.")
        driver.switch_to.frame(iframes[0])
        time.sleep(5)  # Wait after switching to iframe
    else:
        logging.info("No iframes found on the page.")

    # Save screenshot for debugging
    screenshot_path = "debug_screenshot.png"
    driver.save_screenshot(screenshot_path)
    logging.info(f"Saved screenshot to {screenshot_path}")

    chart_elements = driver.find_elements(By.CLASS_NAME, "song-wrapper")
    logging.info(f"Found {len(chart_elements)} song-wrapper elements.")
    chart_data = []

    for i, elem in enumerate(chart_elements):
        try:
            rank = elem.find_element(By.CLASS_NAME, "song-index-num").text.strip()
            song = elem.find_element(By.CLASS_NAME, "song-detail-name").text.strip()
            artist = elem.find_element(By.CLASS_NAME, "song-detail-artist").text.strip()
            logging.info(f"Entry {i+1}: rank={rank}, song={song}, artist={artist}")
            chart_data.append({
                "rank": int(rank),
                "song": song,
                "artist": artist
            })
        except Exception as e:
            logging.warning(f"Skipping a song entry due to error: {e}")
            continue

    chart_json = {
        "source": "EIGHT FM 20好听榜",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "chart": chart_data
    }

    filename = f"eightfm_{datetime.now().strftime('%Y%m%d')}.json"
    full_path = os.path.join(output_path, filename)

    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(chart_json, f, ensure_ascii=False, indent=2)

    logging.info(f"✅ Chart saved to {full_path} with {len(chart_data)} entries.")

    driver.quit()

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

def upload_to_blogger():
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

    output_path = os.getenv("EIGHT_LOCATION")
    DATE_STR = datetime.now().strftime("%Y%m%d")
    json_path = os.path.join(output_path, f"eightfm_{DATE_STR}.json")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            chart_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load chart data: {e}")
        return

    content = "<h2>EIGHT FM 20好听榜 - {}</h2>".format(chart_data['date'])
    for item in chart_data["chart"]:
        content += f"<p><b>{item['rank']}. {item['song']}</b><br><i>{item['artist']}</i></p>"

    title = f"EIGHT FM Chart - {chart_data['date']}"

    try:
        posts = service.posts()
        new_post = posts.insert(blogId=BLOG_ID, body={"title": title, "content": content}, isDraft=False).execute()
        logging.info(f"✅ Blog post published: {new_post.get('url')}")
    except HttpError as error:
        logging.error(f"❌ Failed to publish post to Blogger: {error}")

if __name__ == "__main__":
    scrape_eightfm_chart()
    upload_to_blogger()
