import os
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

HEADERS = {"Authorization": f"Bearer {API_KEY}"}


# -------------------------
# API HELPERS
# -------------------------

def request_json(url):
    for _ in range(5):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        time.sleep(1)
    return {"data": []}


def get_all_pages(url):
    page = 1
    results = []

    while True:
        sep = "&" if "?" in url else "?"
        data = request_json(f"{url}{sep}page={page}")

        results.extend(data.get("data", []))

        meta = data.get("meta", {})
        if page >= meta.get("total_pages", 1):
            break

        page += 1

    return results


# -------------------------
# UTILITY
# -------------------------

def minutes_played(min_val):
    if not min_val:
        return 0

    s = str(min_val)

    if ":" in s:
        m, _ = s.split(":")
        return int(m)

    try:
        return int(float(s))
    except:
        return 0


# -------------------------
# DATA COLLECTION
# -------------------------

def today_games():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return get_all_pages(f"{BASE_URL}/games?dates[]={today}")


def recent_games(team_id):
    games = []

    # ⭐ Increased lookback window (30 → 45 days)
    for i in range(1, 45):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        g = get_all_pages(f"{BASE_URL}/games?dates[]={d}&team_ids[]={team_id}")

        for game in g:
            if game.get("home_team_score") is not None:
                games.append(game)

        if len(games) >= 3:
            break

    return games[:3]


def players_from_game(game_id, team_id):
    stats = get_all_pages(f"{BASE_URL}/stats?game_ids[]={game_id}")

    # ⭐ Lower payload guard (20 → 8 players)
    if len(stats) < 8:
        return set()

    names = set()

    for s in stats:
        if s["team"]["id"] != team_id:
            continue

        if minutes_played(s["min"]) >= 1:
            p = s["player"]
            names.add(p["first_name"] + " " + p["last_name"])

    return names


# -------------------------
# TEAM ANALYSIS
# -------------------------

def analyze_team(team):
    games = recent_games(team["id"])

    appearances = defaultdict(int)

    for g in games:
        players = players_from_game(g["id"], team["id"])
        for p in players:
            appearances[p] += 1

    core = [p for p, c in appearances.items() if c >= 2]
    value = [p for p, c in appearances.items() if c == 1]

    return [g["id"] for g in games], sorted(core), sorted(value)


# -------------------------
# REPORT BUILDER
# -------------------------

def build_report():
    games = today_games()

    lines = []
    lines.append("NBA PROP ENGINE (SAFE + VALUE)")
    lines.append(f"UTC Date: {datetime.utcnow().strftime('%Y-%m-%d')}")
    lines.append("")

    for g in games:
        home = g["home_team"]
        visitor = g["visitor_team"]

        lines.append("===================================")
        lines.append(f"{visitor['full_name']} @ {home['full_name']}")
        lines.append("===================================")

        for team in [visitor, home]:

            gids, core, value = analyze_team(team)

            lines.append(f"--- {team['full_name']} ---")
            lines.append(f"Recent game IDs used (newest→older): {gids}")

            lines.append("")
            lines.append("SAFE CORE (best for props):")
            lines.extend(["- " + p for p in core] or ["- None"])

            lines.append("")
            lines.append("VALUE / BREAKOUT WATCH:")
            lines.extend(["- " + p for p in value] or ["- None"])

            lines.append("")

    return "\n".join(lines)


# -------------------------
# SAVE OUTPUT
# -------------------------

def save_report(text):
    os.makedirs("reports", exist_ok=True)

    with open("reports/latest.txt", "w") as f:
        f.write(text)


# -------------------------
# MAIN
# -------------------------

if __name__ == "__main__":
    report = build_report()
    save_report(report)
    print(report)
