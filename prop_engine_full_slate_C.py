import requests
import datetime
import os
import time

API_KEY = os.getenv("BALLDONTLIE_API_KEY")

HEADERS = {
    "Authorization": API_KEY
}

BASE = "https://api.balldontlie.io/v1"

LOOKBACK_DAYS = 3
SLEEP = 0.7


def api_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ API failed: {url} | status={r.status_code}")
            return None
        time.sleep(SLEEP)
        return r.json()
    except Exception as e:
        print("API error:", e)
        return None


def get_today_games():
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    url = f"{BASE}/games?dates[]={today}&per_page=100"
    data = api_get(url)
    return data["data"] if data else []


def get_recent_games(team_id):
    games = []
    for i in range(1, LOOKBACK_DAYS + 1):
        date = (
            datetime.datetime.utcnow()
            - datetime.timedelta(days=i)
        ).strftime("%Y-%m-%d")

        url = f"{BASE}/games?dates[]={date}&team_ids[]={team_id}&per_page=100"
        data = api_get(url)

        if data and data["data"]:
            games.extend(data["data"])

    return games


def print_team_report(team):
    print(f"\n--- {team['full_name']} ---")

    recent = get_recent_games(team["id"])

    game_ids = [g["id"] for g in recent][:3]

    print("Recent game IDs used (newest→older):", game_ids)

    print("\nSAFE CORE (appearance consistency proxy):")
    if game_ids:
        print("- Team recently active")
    else:
        print("- None")

    print("\nVALUE / BREAKOUT WATCH:")
    print("- Manual review required (stats locked on free tier)")


def run_engine():

    print("\nNBA PROP ENGINE (FREE SAFE MODE)")
    print("UTC Date:", datetime.datetime.utcnow().date())

    games = get_today_games()

    if not games:
        print("No games found today")
        return

    for g in games:
        home = g["home_team"]
        away = g["visitor_team"]

        print("\n===================================")
        print(f"{away['full_name']} @ {home['full_name']}")
        print("===================================")

        print_team_report(away)
        print_team_report(home)


if __name__ == "__main__":
    run_engine()
