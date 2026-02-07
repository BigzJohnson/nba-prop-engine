import requests
from datetime import datetime, timedelta
import time
from collections import defaultdict
import os

API_KEY = os.environ.get("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

# -------------------------------------------------
# SAFE PAGINATED API REQUEST
# -------------------------------------------------
def safe_get_paginated(url):
    all_data = []
    page = 1

    while True:
        paged_url = f"{url}&page={page}"
        try:
            r = requests.get(paged_url, headers=headers, timeout=10)
            if r.status_code != 200:
                print("⚠️ API status:", r.status_code, paged_url)
                break

            j = r.json()
            data = j.get("data", [])
            meta = j.get("meta", {})

            all_data.extend(data)

            if not meta or page >= meta.get("total_pages", 1):
                break

            page += 1
            time.sleep(0.4)

        except Exception as e:
            print("⚠️ API error:", e)
            break

    return all_data

# -------------------------------------------------
# MINUTES PARSER (FIXES BUG)
# -------------------------------------------------
def parse_minutes_to_float(min_val):
    if min_val is None:
        return 0.0

    s = str(min_val).strip()
    if not s or s in {"0", "00", "0:00", "00:00"}:
        return 0.0

    if ":" in s:
        try:
            mm, ss = s.split(":")
            return float(mm) + float(ss)/60
        except:
            return 0.0

    try:
        return float(s)
    except:
        return 0.0

# -------------------------------------------------
# GET TODAY GAMES
# -------------------------------------------------
def get_today_games():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    url = f"{BASE_URL}/games?dates[]={today}&per_page=100"
    return safe_get_paginated(url)

# -------------------------------------------------
# GET LAST COMPLETED GAMES
# -------------------------------------------------
def get_completed_games_for_team(team_id, target_n=3, lookback_days=12):

    collected = []

    for i in range(1, lookback_days+1):

        if len(collected) >= target_n:
            break

        d = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')

        url = f"{BASE_URL}/games?dates[]={d}&team_ids[]={team_id}&per_page=100"
        games = safe_get_paginated(url)

        for g in games:
            if g.get("home_team_score") is not None:

                if g["id"] not in {x["id"] for x in collected}:
                    collected.append(g)

    return collected[:target_n]

# -------------------------------------------------
# GET PLAYERS WHO PLAYED REAL MINUTES
# -------------------------------------------------
def get_players_from_game_for_team(game_id, team_id):

    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=100"
    stats = safe_get_paginated(url)

    names = set()

    for s in stats:

        team = s.get("team", {})
        player = s.get("player")
        mins = parse_minutes_to_float(s.get("min"))

        if player and team.get("id") == team_id:
            if mins >= 1.0:
                full = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
                names.add(full)

    return names

# -------------------------------------------------
# ROTATION ANALYSIS
# -------------------------------------------------
def analyze_team(team):

    team_id = team["id"]
    games = get_completed_games_for_team(team_id)

    appearance = defaultdict(int)
    game_ids = []

    for g in games:

        game_ids.append(g["id"])
        players = get_players_from_game_for_team(g["id"], team_id)

        for p in players:
            appearance[p] += 1

    safe_core = sorted([p for p,c in appearance.items() if c >= 2])
    value_watch = sorted([p for p,c in appearance.items() if c == 1])

    return game_ids, safe_core, value_watch

# -------------------------------------------------
# MAIN REPORT BUILDER
# -------------------------------------------------
def build_report():

    games = get_today_games()

    report = []
    report.append("NBA PROP ENGINE (SAFE + VALUE)")
    report.append(f"UTC Date: {datetime.utcnow().strftime('%Y-%m-%d')}")
    report.append("")

    for g in games:

        home = g["home_team"]
        visitor = g["visitor_team"]

        report.append("===================================")
        report.append(f"{visitor['full_name']} @ {home['full_name']}")
        report.append("===================================")

        for team in [visitor, home]:

            ids, safe, value = analyze_team(team)

            report.append("")
            report.append(f"--- {team['full_name']} ---")
            report.append(f"Recent game IDs used (newest→older): {ids}")
            report.append("")

            report.append("SAFE CORE (best for props):")
            if safe:
                for p in safe:
                    report.append(f"- {p}")
            else:
                report.append("- None")

            report.append("")
            report.append("VALUE / BREAKOUT WATCH (role trending):")
            if value:
                for p in value:
                    report.append(f"- {p}")
            else:
                report.append("- None")

            report.append("")

    return "\n".join(report)

# -------------------------------------------------
# SAVE REPORT
# -------------------------------------------------
def save_report(text):

    os.makedirs("reports", exist_ok=True)

    with open("reports/latest.txt", "w", encoding="utf-8") as f:
        f.write(text)

# -------------------------------------------------
# RUN
# -------------------------------------------------
if __name__ == "__main__":

    report = build_report()
    save_report(report)

    print(report)
