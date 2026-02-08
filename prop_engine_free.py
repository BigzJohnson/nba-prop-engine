import requests
import time
import os
import random
from collections import deque
from datetime import datetime, timedelta

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

headers = {
    "Authorization": API_KEY
}

# ================================
# GLOBAL RATE LIMIT STATE
# ================================

CALL_HISTORY = deque(maxlen=60)
GLOBAL_COOLDOWN_UNTIL = 0


def rate_limit_wait():

    global GLOBAL_COOLDOWN_UNTIL

    if time.time() < GLOBAL_COOLDOWN_UNTIL:
        wait = GLOBAL_COOLDOWN_UNTIL - time.time()
        print(f"🛑 Global cooldown {wait:.2f}s")
        time.sleep(wait)

    while True:
        now = time.time()

        if len(CALL_HISTORY) < 60:
            break

        oldest = CALL_HISTORY[0]

        if now - oldest > 60:
            break

        sleep_time = 60 - (now - oldest) + 0.25
        print(f"⏳ Window wait {sleep_time:.2f}s")
        time.sleep(sleep_time)

    CALL_HISTORY.append(time.time())

    time.sleep(random.uniform(0.05, 0.20))


def safe_get(url, retries=7):

    global GLOBAL_COOLDOWN_UNTIL

    backoff = 3

    for attempt in range(retries):

        rate_limit_wait()

        try:
            r = requests.get(url, headers=headers, timeout=20)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                cooldown = random.uniform(25, 45)
                GLOBAL_COOLDOWN_UNTIL = time.time() + cooldown

                print(f"🚨 429 cooldown {cooldown:.1f}s")

                time.sleep(backoff)
                backoff *= 2
                continue

            if r.status_code == 401:
                print("❌ Unauthorized endpoint — skipping")
                return {"data": []}

            print(f"⚠️ API Error {r.status_code}")

        except Exception as e:
            print("Request error:", e)

        time.sleep(backoff)
        backoff *= 2

    return {"data": []}


# ================================
# FETCH TODAY'S GAMES
# ================================

def get_today_games():

    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/games?dates[]={today}"

    data = safe_get(url)

    return data.get("data", [])


# ================================
# GET LAST 7 DAYS GAME IDS
# ================================

def get_recent_games(team_id):

    game_ids = []

    for i in range(1, 8):

        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/games?dates[]={date}&team_ids[]={team_id}&per_page=100"

        data = safe_get(url)

        for g in data.get("data", []):
            game_ids.append(g["id"])

    return game_ids[:3]


# ================================
# GET GAME STATS
# ================================

def get_game_stats(game_id):

    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=100"

    data = safe_get(url)

    return data.get("data", [])


# ================================
# SUM PLAYER MINUTES
# ================================

def aggregate_minutes(stats):

    player_minutes = {}

    for s in stats:

        name = f"{s['player']['first_name']} {s['player']['last_name']}"
        minutes = s.get("min")

        if not minutes:
            continue

        try:
            minutes = float(minutes.split(":")[0])
        except:
            continue

        player_minutes[name] = player_minutes.get(name, 0) + minutes

    return player_minutes


# ================================
# PROCESS TEAM ROTATION
# ================================

def analyze_team(team_id, team_name):

    recent_games = get_recent_games(team_id)

    rotation_minutes = {}

    for gid in recent_games:

        stats = get_game_stats(gid)

        mins = aggregate_minutes(stats)

        for p, m in mins.items():
            rotation_minutes[p] = rotation_minutes.get(p, 0) + m

    if not rotation_minutes:
        print("SAFE CORE:")
        print("- None")
        print("\nVALUE WATCH:")
        print("- None")
        return

    sorted_players = sorted(rotation_minutes.items(), key=lambda x: x[1], reverse=True)

    print("SAFE CORE:")
    for p, _ in sorted_players[:5]:
        print(f"- {p}")

    print("\nVALUE WATCH:")
    for p, _ in sorted_players[5:10]:
        print(f"- {p}")


# ================================
# MAIN ENGINE
# ================================

def main():

    print("\nNBA PROP ENGINE (FREE SAFE MODE)")
    print("UTC Date:", datetime.utcnow().strftime("%Y-%m-%d"))
    print("\n")

    games = get_today_games()

    for g in games:

        home = g["home_team"]
        away = g["visitor_team"]

        print("\n===================================")
        print(f"{away['full_name']} @ {home['full_name']}")
        print("===================================\n")

        print(f"--- {away['full_name']} ---")
        analyze_team(away["id"], away["full_name"])

        print(f"\n--- {home['full_name']} ---")
        analyze_team(home["id"], home["full_name"])


if __name__ == "__main__":
    main()
