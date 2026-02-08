import requests
import time
import os
from datetime import datetime, timedelta

# ============================
# CONFIG
# ============================

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

headers = {
    "Authorization": API_KEY
}

# ============================
# FREE TIER RATE LIMITER
# 5 REQUESTS PER MINUTE
# ============================

LAST_CALL_TIME = 0
MIN_SECONDS_PER_CALL = 12.5


def rate_limit_wait():
    global LAST_CALL_TIME

    elapsed = time.time() - LAST_CALL_TIME

    if elapsed < MIN_SECONDS_PER_CALL:
        wait_time = MIN_SECONDS_PER_CALL - elapsed
        print(f"⏳ Rate limiting... sleeping {round(wait_time,2)}s")
        time.sleep(wait_time)

    LAST_CALL_TIME = time.time()


def safe_get(url, retries=6):

    backoff = 30

    for attempt in range(retries):

        rate_limit_wait()

        try:
            r = requests.get(url, headers=headers, timeout=20)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                print(f"🚫 429 Rate Limited. Cooling down {backoff}s")
                time.sleep(backoff)
                backoff *= 1.5
                continue

            if r.status_code == 401:
                print("❌ Unauthorized endpoint (free tier blocked)")
                return {"data": []}

            print(f"⚠️ API Error {r.status_code}: {url}")

        except Exception as e:
            print("Request error:", e)

        print(f"Retrying in {backoff}s...")
        time.sleep(backoff)
        backoff *= 1.5

    return {"data": []}


# ============================
# GET TODAY'S GAMES
# ============================

def get_today_games():

    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/games?dates[]={today}"

    data = safe_get(url)

    return data.get("data", [])


# ============================
# GET LAST N GAMES FOR TEAM
# ============================

def get_recent_games(team_id, lookback=10):

    games = []

    today = datetime.utcnow()

    for i in range(1, lookback + 1):

        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/games?dates[]={date}&team_ids[]={team_id}"

        data = safe_get(url)

        games.extend(data.get("data", []))

    return games


# ============================
# MAIN ENGINE
# ============================

def run_engine():

    print("NBA PROP ENGINE (FREE SAFE MODE)")
    print("UTC Date:", datetime.utcnow().strftime("%Y-%m-%d"))
    print()

    games = get_today_games()

    for game in games:

        home = game["home_team"]["full_name"]
        away = game["visitor_team"]["full_name"]

        home_id = game["home_team"]["id"]
        away_id = game["visitor_team"]["id"]

        print("===================================")
        print(f"{away} @ {home}")
        print("===================================")

        print("\n---", away, "---")
        away_recent = get_recent_games(away_id)
        print("Recent games found:", len(away_recent))

        print("\n---", home, "---")
        home_recent = get_recent_games(home_id)
        print("Recent games found:", len(home_recent))

        print()


# ============================
# ENTRY
# ============================

if __name__ == "__main__":
    run_engine()
