import os
import time
import requests
from datetime import datetime, timedelta

API_KEY = os.getenv("BALLDONTLIE_API_KEY")

BASE_URL = "https://api.balldontlie.io/v1"

HEADERS = {
    "Authorization": API_KEY
}

# --------------------------------------------------
# SAFE REQUEST (429 + 401 FIX)
# --------------------------------------------------
def safe_request(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                print(f"⚠️ Rate limited: {url}")
                time.sleep(3)

            elif r.status_code == 401:
                print(f"⚠️ Unauthorized API request: {url}")
                return None

            else:
                print(f"⚠️ API failed: {url} | status={r.status_code}")

        except Exception as e:
            print(f"Request error: {e}")
            time.sleep(2)

    return None


# --------------------------------------------------
# GET TODAY'S GAMES
# --------------------------------------------------
def get_games_today():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/games?dates[]={today}&per_page=100"

    data = safe_request(url)

    if not data:
        return []

    return data.get("data", [])


# --------------------------------------------------
# GET LAST N GAMES FOR TEAM
# --------------------------------------------------
def get_recent_games(team_id, lookback_days=10):

    games = []

    for i in range(lookback_days):
        date = datetime.utcnow() - timedelta(days=i+1)
        date = date.strftime("%Y-%m-%d")

        url = f"{BASE_URL}/games?dates[]={date}&team_ids[]={team_id}&per_page=100"

        data = safe_request(url)

        if not data:
            continue

        if data["data"]:
            games.extend(data["data"])

        if len(games) >= 3:
            break

    return games[:3]


# --------------------------------------------------
# GET PLAYER STATS FROM GAME
# --------------------------------------------------
def get_game_stats(game_id):

    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=300"

    data = safe_request(url)

    if not data:
        return []

    return data.get("data", [])


# --------------------------------------------------
# ANALYZE ROTATION
# --------------------------------------------------
def analyze_rotation(game_ids):

    minutes_map = {}

    for gid in game_ids:

        stats = get_game_stats(gid)

        for player in stats:

            name = f"{player['player']['first_name']} {player['player']['last_name']}"
            minutes = player.get("min")

            if not minutes:
                continue

            try:
                minutes = float(minutes.split(":")[0])
            except:
                continue

            minutes_map[name] = minutes_map.get(name, 0) + minutes

    # Sort by minutes played
    sorted_players = sorted(minutes_map.items(), key=lambda x: x[1], reverse=True)

    return sorted_players[:8]


# --------------------------------------------------
# MAIN ENGINE
# --------------------------------------------------
def run_engine():

    print("NBA PROP ENGINE (SAFE + VALUE)")
    print(f"UTC Date: {datetime.utcnow().strftime('%Y-%m-%d')}\n")

    games = get_games_today()

    if not games:
        print("No games found today.")
        return

    for game in games:

        home = game["home_team"]["full_name"]
        away = game["visitor_team"]["full_name"]

        home_id = game["home_team"]["id"]
        away_id = game["visitor_team"]["id"]

        print("===================================")
        print(f"{away} @ {home}")
        print("===================================\n")

        for team_name, team_id in [(away, away_id), (home, home_id)]:

            recent_games = get_recent_games(team_id)

            game_ids = [g["id"] for g in recent_games]

            print(f"--- {team_name} ---")
            print(f"Recent game IDs used (newest→older): {game_ids}\n")

            rotation = analyze_rotation(game_ids)

            print("SAFE CORE (best for props):")

            if rotation:
                for player, mins in rotation[:3]:
                    print(f"- {player} ({mins:.1f} avg mins)")
            else:
                print("- None")

            print("\nVALUE / BREAKOUT WATCH (role trending):")

            if len(rotation) > 3:
                for player, mins in rotation[3:6]:
                    print(f"- {player} ({mins:.1f} avg mins)")
            else:
                print("- None")

            print()


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    run_engine()
