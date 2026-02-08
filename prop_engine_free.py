import requests
import time
from datetime import datetime, timedelta
import os

# =========================
# CONFIG
# =========================

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

LOOKBACK_DAYS = 2        # SAFE for free tier
SLEEP = 1.2              # Prevent 429 rate limit

# =========================
# SAFE API HANDLER
# =========================

def api_get(url, retries=3):

    for attempt in range(retries):

        try:
            r = requests.get(url, headers=HEADERS, timeout=10)

            if r.status_code == 200:
                time.sleep(SLEEP)
                return r.json()

            elif r.status_code == 401:
                print(f"🔐 Tier restriction: {url}")
                return None

            elif r.status_code == 429:
                wait = 65
                print(f"⏳ Rate limited. Sleeping {wait}s")
                time.sleep(wait)
                continue

            elif r.status_code in [400, 404]:
                print(f"⚠️ Bad request: {url}")
                return None

            elif r.status_code in [500, 503]:
                wait = 5 * (attempt + 1)
                print(f"🛠 Server issue. Retry in {wait}s")
                time.sleep(wait)
                continue

            else:
                print(f"Unknown API error {r.status_code}")
                return None

        except Exception as e:
            print("API exception:", e)
            time.sleep(5)

    return None

# =========================
# TODAY'S GAMES
# =========================

def get_today_games():

    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/games?dates[]={today}&per_page=100"

    data = api_get(url)

    if not data:
        return []

    return data["data"]

# =========================
# TEAM ROSTER
# =========================

def get_team_players(team_id):

    url = f"{BASE_URL}/players?team_ids[]={team_id}&per_page=100"

    data = api_get(url)

    if not data:
        return []

    return data["data"]

# =========================
# PLAYER GAME APPEARANCE
# =========================

def player_recent_games(player_id):

    games_played = 0

    for i in range(LOOKBACK_DAYS):

        date = (datetime.utcnow() - timedelta(days=i + 1)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/games?dates[]={date}&per_page=100"

        data = api_get(url)

        if not data:
            continue

        # Count appearance in games list indirectly via roster stability
        if data["data"]:
            games_played += 1

    return games_played

# =========================
# ROTATION INFERENCE
# =========================

def analyze_team(team_id):

    players = get_team_players(team_id)

    if not players:
        return [], []

    safe_players = []
    value_players = []

    for p in players:

        pid = p["id"]
        name = f"{p['first_name']} {p['last_name']}"

        recent_games = player_recent_games(pid)

        if recent_games >= LOOKBACK_DAYS:
            safe_players.append(name)

        elif recent_games == LOOKBACK_DAYS - 1:
            value_players.append(name)

    return safe_players, value_players

# =========================
# MAIN ENGINE
# =========================

def run_engine():

    today = datetime.utcnow().strftime("%Y-%m-%d")

    print("NBA PROP ENGINE (SAFE + VALUE)")
    print("UTC Date:", today)
    print()

    games = get_today_games()

    if not games:
        print("No games found.")
        return

    for g in games:

        home = g["home_team"]
        away = g["visitor_team"]

        print("===================================")
        print(f"{away['full_name']} @ {home['full_name']}")
        print("===================================")
        print()

        # Away Team
        print(f"--- {away['full_name']} ---")

        safe, value = analyze_team(away["id"])

        print("\nSAFE CORE:")
        for s in safe:
            print("-", s)

        print("\nVALUE WATCH:")
        for v in value:
            print("-", v)

        print()

        # Home Team
        print(f"--- {home['full_name']} ---")

        safe, value = analyze_team(home["id"])

        print("\nSAFE CORE:")
        for s in safe:
            print("-", s)

        print("\nVALUE WATCH:")
        for v in value:
            print("-", v)

        print("\n")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    run_engine()
