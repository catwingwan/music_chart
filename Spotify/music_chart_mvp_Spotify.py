# music_chart_mvp.py
# MVP: 自動建立歌曲排行榜，生成 HTML，並自動發佈到 Blogger（含 AI 解說段落）

import requests
import pandas as pd
import urllib.parse
from dotenv import load_dotenv
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from io import StringIO
from datetime import datetime, timedelta

# === 載入環境變數 ===
load_dotenv()

# === CONFIG ===
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or "YOUR_SPOTIFY_CLIENT_ID"
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET") or "YOUR_SPOTIFY_CLIENT_SECRET"
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET") or "client_secret.json"
BLOG_ID = os.getenv("BLOG_ID") or "YOUR_BLOG_ID"
TOKEN_PATH = "token.json"

# 地區顯示名稱對應
REGION_NAMES = {
    "my": "馬來西亞",
    "sg": "新加坡",
    "ph": "菲律賓",
    "id": "印尼",
    "global": "全球"
}

# 地區對應播放清單 ID（Spotify Top 50）
REGION_PLAYLISTS = {
    "my": "37i9dQZEVXbJlfUljuZExa",
    "sg": "37i9dQZEVXbK4yq3zF3r3E",
    "ph": "37i9dQZEVXbNBz9cRCSFkY",
    "id": "37i9dQZEVXbObFQZ3JLcXt",
    "global": "37i9dQZEVXbMDoHDwVN2tF"
}

# === 初始化 log 資料夾 ===
os.makedirs("logs", exist_ok=True)
os.makedirs("logs/raw", exist_ok=True)

# === Spotify 授權 ===
def get_spotify_token():
    resp = requests.post("https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    if resp.status_code != 200:
        print(f"⚠ 無法取得 Spotify token：{resp.status_code} - {resp.text}")
        return None
    token = resp.json().get("access_token")
    print(f"🎫 成功取得 Spotify token: {token[:10]}...")
    return token

# === 使用 Spotify Charts CSV 下載 URL ===
def fetch_spotify_charts_csv(region="my", period="weekly", date="latest"):
    base_url = f"https://spotifycharts.com/regional/{region}/{period}/{date}/download"
    try:
        response = requests.get(base_url, allow_redirects=False)
        if response.status_code in [301, 302] and 'Location' in response.headers:
            redirect_url = response.headers['Location']
            print(f"🔁 發現重新導向至：{redirect_url}")
            response = requests.get(redirect_url)
        elif response.status_code == 200:
            print(f"📡 成功下載排行榜 CSV：{region}-{period}")
        else:
            print(f"⚠ 無法下載 CSV：HTTP {response.status_code}")
            return None

        if 'text/html' in response.headers.get('Content-Type', ''):
            print("⚠ 收到的是 HTML 頁面，非 CSV 格式。")
            return None

        df = pd.read_csv(StringIO(response.text), skiprows=1)
        if df.empty:
            print("⚠ CSV 為空表格")
            return None

        df = df.rename(columns={
            "Position": "排名",
            "Track Name": "歌曲",
            "Artist": "歌手",
            "Streams": "播放次數",
            "URL": "Spotify連結"
        })
        df["播放次數"] = df["播放次數"].astype(int)
        df["Spotify熱度"] = (df["播放次數"] / 10000).astype(int)
        df["總分"] = df["Spotify熱度"]
        return df

    except Exception as e:
        print(f"⚠ 發生錯誤：{e}")
        return None

# === 使用 Spotify 播放清單 API 作為備援（新的完整 playlist endpoint） ===
def fetch_spotify_playlist_backup(region="my"):
    playlist_id = REGION_PLAYLISTS.get(region)
    if not playlist_id:
        print(f"⚠ 無對應播放清單 ID：{region}")
        return None

    token = get_spotify_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}"
    resp = requests.get(url, headers=headers)
    print(f"📡 呼叫 Spotify 播放清單 API：{resp.status_code}")

    if resp.status_code != 200:
        if region != "global":
            print("🔁 嘗試改用 global 播放清單")
            return fetch_spotify_playlist_backup(region="global")
        print(f"⚠ 無法下載播放清單（{region}）: HTTP {resp.status_code}")
        print(f"⚠ 錯誤內容：{resp.text}")
        return None

    data = resp.json()
    raw_path = f"logs/raw/spotify_raw_{region}.json"
    with open(raw_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📝 原始 JSON 已儲存：{raw_path}")

    items = data.get("tracks", {}).get("items", [])
    rows = []
    for idx, item in enumerate(items, 1):
        track = item.get("track", {})
        name = track.get("name")
        artist = track.get("artists", [{}])[0].get("name")
        popularity = track.get("popularity", 0)
        url = track.get("external_urls", {}).get("spotify")
        if name and artist:
            rows.append({
                "排名": idx,
                "歌曲": name,
                "歌手": artist,
                "Spotify熱度": popularity,
                "總分": popularity,
                "Spotify連結": url
            })
    df = pd.DataFrame(rows)
    print(f"🔎 播放清單取得成功：{len(df)} 首")
    return df

# === 整合資料與排序 ===
def build_chart(source="charts", region="my"):
    df = fetch_spotify_charts_csv(region=region)
    if df is None or df.empty:
        print("🔁 嘗試改用備援地區 Spotify 播放清單 API")
        df = fetch_spotify_playlist_backup(region=region)
    if df is None or df.empty:
        print("📭 排行榜為空")
        return pd.DataFrame()
    df = df[["排名", "歌曲", "歌手", "Spotify熱度", "總分", "Spotify連結"]]
    df["排名"] = df["總分"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("排名")

# === 產生 HTML 表格 ===
def generate_html_table(df):
    html = '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:sans-serif;">'
    html += '<thead><tr style="background-color:#f2f2f2;"><th>排名</th><th>歌曲</th><th>歌手</th><th>Spotify 熱度</th><th>總分</th><th>Spotify</th></tr></thead><tbody>'
    for _, row in df.iterrows():
        html += f"<tr><td>{row['排名']}</td><td>{row['歌曲']}</td><td>{row['歌手']}</td><td>{row['Spotify熱度']}</td><td>{row['總分']}</td><td><a href='{row['Spotify連結']}' target='_blank'>🎵</a></td></tr>"
    html += '</tbody></table>'
    return html

# === 發佈至 Blogger ===
def publish_to_blogger(content_html, region):
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/blogger'])
    else:
        flow = InstalledAppFlow.from_client_secrets_file(BLOGGER_CLIENT_SECRET, scopes=['https://www.googleapis.com/auth/blogger'])
        creds = flow.run_local_server(port=8080)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    service = build('blogger', 'v3', credentials=creds)
    region_name = REGION_NAMES.get(region, region.upper())
    title = f"每週歌曲數據榜（{region_name}）"

    body = {
        "title": title,
        "content": content_html
    }

    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    print(f"✅ 已發佈：{post['title']}")

# === AI 解說生成 ===
def generate_ai_summary(df):
    top3 = df.head(3)
    summary = "\n".join([f"《{row['歌曲']}》 by {row['歌手']}" for _, row in top3.iterrows()])
    return f"本週前 3 名歌曲為：{summary}，趨勢仍以華語流行為主！"

# === 主程式 ===
if __name__ == "__main__":
    regions = ["my", "sg", "ph", "id"]
    for region in regions:
        print(f"🔄 產生 {region.upper()} 排行榜...")
        df = build_chart(region=region)
        if df.empty:
            print(f"⚠ 無法建立排行榜，來源資料為空或失敗。")
            continue
        html_table = generate_html_table(df)
        summary = generate_ai_summary(df)
        full_content = f"<p>{summary}</p>{html_table}"
        publish_to_blogger(full_content, region)
