import os
import time
import requests
from datetime import datetime, timedelta

# ==============================
# CONFIG
# ==============================

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

# Hard rate limit: 60 requests/min
REQUEST_DELAY = 1.05

# Retry rules
MAX_RETRIES = 3
BACKOFF_BASE = 4

HEADERS = {
    "Authorization": API_KEY
}

# Simple cache to prevent duplicate calls
CACHE = {}

# ==============================
# SAFE REQUEST HANDLER
# ==============================
def safe_request(endpoint, params=None):

    url = f"{BASE_URL}/{endpoint}"

    cache_key = url + str(params)
    if cache_key in CACHE:
        return CACHE[cache_key]

    for attempt in range(MAX_RETRIES):

        try:
            r = requests.get(url, headers=HEADERS, params=params)

            # -----------------
            # SUCCESS
            # -----------------
            if r.status_code == 200:
                data = r.json()
                CACHE[cache_key] = data
                time.sleep(REQUEST_DELAY)
                return data

            # -----------------
            # UNAUTHORIZED (401)
            # Usually premium endpoint
            # -----------------
            if r.status_code == 401:
                print(f"❌ 401 Unauthorized -> {endpoint}")
                return None

            # -----------------
            # RATE LIMIT (429)
            # -----------------
            if r.status_code == 429:
                wait = BACKOFF_BASE * (attempt + 1)
                print(f"⚠️ 429 Rate limit. Sleeping {wait}s")
                time.sleep(wait)
                continue

            # -----------------
            # OTHER ERRORS
            # -----------------
            print(f"⚠️ API Error {endpoint} -> {r.status_code}")
            return None

        except Exception as e:
            print("Request failure:", e)
            time.sleep(3)

    return None


# ==============================
# GET TODAY'S SLATE
# ==============================
def get_today_games():

    today = datetime.utcnow().strftime("%Y-%m-%d")

    data = safe_request(
        "games",
        {"dates[]": today, "per_page": 100}
    )

    if not data:
        return []

    return data["data"]


# ==============================
# GET LAST COMPLETED GAMES
# ==============================
def get_recent_games(team_id, limit=2):

    results = []
    cursor = datetime.utcnow()

    # Only look back max 7 days (API protection)
    for _ in range(7):

        if len(results) >= limit:
            break

        date_str = cursor.strftime("%Y-%m-%d")

        data = safe_request(
            "games",
            {
                "dates[]": date_str,
                "team_ids[]": team_id,
                "per_page": 100
            }
        )

        if data:
            results.extend(data["data"])

        cursor -= timedelta(days=1)

    return results[:limit]


# ==============================
# GET ROTATION (MINUTES LEADERS)
# ==============================
def get_rotation_from_boxscore(game_id):

    data = safe_request(
        "box_scores",
        {"game_ids[]": game_id}
    )

    if not data:
        return []

    players = data["data"]

    # Sort by minutes
    players_sorted = sorted(
        players,
        key=lambda x: float(x.get("min", 0) or 0),
        reverse=True
    )

    return players_sorted[:8]


# ==============================
# BUILD ROTATION LIST
# ==============================
def build_team_rotation(team):

    print(f"\n--- {team['full_name']} ---")

    recent_games = get_recent_games(team["id"])

    game_ids = [g["id"] for g in recent_games]
    print("Recent game IDs:", game_ids)

    rotation = []

    for gid in game_ids:
        rotation.extend(get_rotation_from_boxscore(gid))

    unique_players = list({
        p["player"]["full_name"]
        for p in rotation
    })

    print("Likely Active Rotation:")
    for p in unique_players:
        print("-", p)


# ==============================
# MAIN ENGINE
# ==============================
def run_engine():

    print("\nNBA PROP ENGINE")
    print("UTC Date:", datetime.utcnow().date())

    games = get_today_games()

    if not games:
        print("No games found.")
        return

    for g in games:

        home = g["home_team"]
        away = g["visitor_team"]

        print("\n===================================")
        print(f"{away['full_name']} @ {home['full_name']}")
        print("===================================")

        build_team_rotation(home)
        build_team_rotation(away)


# ==============================
# START
# ==============================
if __name__ == "__main__":
    run_engine()
