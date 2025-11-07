# Radio Music Chart (radio_chart.py)
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# Blogger settings
load_dotenv()

BLOG_ID = os.getenv('BLOG_ID')
TOKEN_FILE = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/blogger']

# Step 1: Scrape Chart Data from MY FM using Selenium
def fetch_myfm_chart():
    url = 'https://my.syok.my/charts/my-fm-music-chart-2025'

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    chrome_path = "/Users/macp/Documents/MUSIC_CHART/chromedriver_mac_arm64/chromedriver"
    service = Service(chrome_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "music-chart-list"))
        )

        chart_items = []
        rows = driver.find_elements(By.CSS_SELECTOR, ".music-chart-list li")
        for row in rows:
            try:
                title = row.find_element(By.CLASS_NAME, "music-chart-song-title").text.strip()
                artist = row.find_element(By.CLASS_NAME, "music-chart-song-artist").text.strip()
                if title and artist:
                    chart_items.append((title, artist))
            except Exception:
                continue

        if not chart_items:
            raise Exception("MY FM chart items not found or page structure has changed")

        return chart_items
    finally:
        driver.quit()

# Step 2: Scrape Chart Data from 988
def fetch_988_chart():
    url = 'https://988.com.my/music_chart/'
    res = requests.get(url)
    soup = BeautifulSoup(res.content, 'html.parser')
    chart_items = []
    for row in soup.select(".music_chart_list .music_chart_content"):
        song = row.select_one(".music_chart_title").get_text(strip=True)
        artist = row.select_one(".music_chart_singer").get_text(strip=True)
        chart_items.append((song, artist))
    return chart_items

# Step 3: Scrape Chart Data from EIGHT FM
def fetch_eightfm_chart():
    url = 'https://www.eight.audio/'
    res = requests.get(url)
    soup = BeautifulSoup(res.content, 'html.parser')
    chart_items = []
    for row in soup.select(".chart-card"):
        song = row.select_one(".chart-card-title").get_text(strip=True)
        artist = row.select_one(".chart-card-singer").get_text(strip=True)
        chart_items.append((song, artist))
    return chart_items

# Step 4: Generate HTML with Spotify links
def generate_html(title, chart_data):
    html = f"<h2>{title} – {datetime.date.today()}</h2>\n<ol>"
    for i, (song, artist) in enumerate(chart_data, 1):
        search_query = quote_plus(f"{song} {artist}")
        spotify_url = f"https://open.spotify.com/search/{search_query}"
        html += f'<li><b>{song}</b> – {artist}<br><a href="{spotify_url}" target="_blank">Listen on Spotify</a></li>'
    html += "</ol>"
    return html

# Step 5: Authenticate and Post to Blogger
def authenticate_blogger():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return build('blogger', 'v3', credentials=creds)

def post_to_blogger(service, title, content):
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": content
    }
    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    print(f"Posted successfully: {post['url']}")

# Main function
def main():
    blogger = authenticate_blogger()

    myfm_chart = fetch_myfm_chart()
    myfm_html = generate_html("MY FM Music 20", myfm_chart)
    post_to_blogger(blogger, "MY FM Music 20 – Chart Update", myfm_html)

    chart_988 = fetch_988_chart()
    chart_988_html = generate_html("988 Music Chart", chart_988)
    post_to_blogger(blogger, "988 Music Chart – Chart Update", chart_988_html)

    eightfm_chart = fetch_eightfm_chart()
    eightfm_html = generate_html("EIGHT FM 20好听榜", eightfm_chart)
    post_to_blogger(blogger, "EIGHT FM 20好听榜 – Chart Update", eightfm_html)

if __name__ == '__main__':
    main()
