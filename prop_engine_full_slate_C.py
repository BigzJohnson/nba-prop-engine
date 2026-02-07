import os
import requests
from datetime import datetime, timedelta, timezone
import time
from collections import defaultdict

API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError("Missing BALLDONTLIE_API_KEY environment variable (set as GitHub Secret).")

BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# ---------- HELPERS ----------
def safe_get(url, retries=3):
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.text.strip():
                return r.json()
        except:
            pass
        time.sleep(1)
    return {"data": []}

def utc_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_today_games():
    url = f"{BASE_URL}/games?dates[]={utc_today()}&per_page=100"
    return safe_get(url).get("data", [])

def get_recent_completed_games(team_id, target_n=5, lookback_days=14):
    games = []
    seen = set()

    for i in range(1, lookback_days + 1):
        if len(games) >= target_n:
            break

        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/games?dates[]={d}&team_ids[]={team_id}&per_page=100"
        data = safe_get(url).get("data", [])

        for g in data:
            # Completed game check
            if g.get("home_team_score") is None or g.get("visitor_team_score") is None:
                continue
            if g["id"] in seen:
                continue
            games.append(g)
            seen.add(g["id"])
            if len(games) >= target_n:
                break

    return games

def parse_minutes(min_str):
    # "34:12" -> 34
    if not min_str or ":" not in str(min_str):
        return None
    try:
        return int(str(min_str).split(":")[0])
    except:
        return None

def get_team_minutes_by_game(game_id, team_id):
    """
    Returns dict: player_name -> minutes_int (>=1 only)
    """
    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=300"
    stats = safe_get(url).get("data", [])
    out = {}

    for s in stats:
        if s.get("team", {}).get("id") != team_id:
            continue
        p = s.get("player")
        if not p:
            continue

        mins = parse_minutes(s.get("min"))
        if mins is None or mins < 1:
            continue

        name = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
        if name:
            # One row per player typically; keep max in case of weird duplicates
            out[name] = max(out.get(name, 0), mins)

    return out

# ---------- SCORING ----------
def safe_score(games_played_last3, avg_min_last3):
    """
    0–100 safe score (role stability)
    """
    score = 0
    # consistency
    score += games_played_last3 * 20  # 20/40/60
    # minutes
    if avg_min_last3 >= 34:
        score += 40
    elif avg_min_last3 >= 30:
        score += 35
    elif avg_min_last3 >= 26:
        score += 28
    elif avg_min_last3 >= 22:
        score += 20
    elif avg_min_last3 >= 18:
        score += 12
    else:
        score += 0

    return min(100, score)

def value_score(min_trend, games_played_last5, avg_min_last5):
    """
    0–100 value score (breakout potential)
    min_trend = last_game_minutes - first_game_minutes over recent sample
    """
    score = 0

    # Trend component (biggest driver)
    if min_trend >= 12:
        score += 55
    elif min_trend >= 8:
        score += 45
    elif min_trend >= 5:
        score += 35
    elif min_trend >= 3:
        score += 25
    elif min_trend >= 1:
        score += 15
    else:
        score += 0

    # Availability (avoid one-game mirages)
    if games_played_last5 >= 5:
        score += 25
    elif games_played_last5 == 4:
        score += 20
    elif games_played_last5 == 3:
        score += 12
    elif games_played_last5 == 2:
        score += 6
    else:
        score += 0

    # Baseline minutes (ensure real role)
    if avg_min_last5 >= 24:
        score += 20
    elif avg_min_last5 >= 20:
        score += 15
    elif avg_min_last5 >= 16:
        score += 10
    elif avg_min_last5 >= 12:
        score += 6
    else:
        score += 0

    return min(100, score)

def analyze_team(team):
    """
    Builds SAFE list + VALUE list using last 5 games (and last 3 subset)
    """
    team_id = team["id"]
    games = get_recent_completed_games(team_id, target_n=5, lookback_days=14)

    # For each game, collect minutes map
    minutes_by_game = []
    for g in games:
        minutes_by_game.append(get_team_minutes_by_game(g["id"], team_id))

    # Aggregate per-player minutes series across games (most recent first)
    series = defaultdict(list)
    for gm in minutes_by_game:
        for player, mins in gm.items():
            series[player].append(mins)

    # games are newest->older in our collection order
    # Ensure each series aligns with that (we appended in same order)
    safe_rows = []
    value_rows = []

    for player, mins_list in series.items():
        # mins_list: minutes in games they played among pulled games, newest-first
        games_played_last5 = len(mins_list)

        # For safe metrics, look at last 3 games window (but only games played)
        last3 = mins_list[:3]
        games_played_last3 = len(last3)
        avg_min_last3 = sum(last3) / games_played_last3 if games_played_last3 else 0

        # For value metrics, use broader last5 window
        avg_min_last5 = sum(mins_list) / games_played_last5 if games_played_last5 else 0

        # trend needs at least 2 datapoints
        if games_played_last5 >= 2:
            min_trend = mins_list[0] - mins_list[-1]
        else:
            min_trend = 0

        s_score = safe_score(games_played_last3, avg_min_last3)
        v_score = value_score(min_trend, games_played_last5, avg_min_last5)

        # SAFE LIST RULES: must be stable enough
        if games_played_last3 >= 2 and avg_min_last3 >= 20:
            safe_rows.append((s_score, player, games_played_last3, round(avg_min_last3,1)))

        # VALUE LIST RULES: trending up or emerging role
        # include if trend >= +3 OR last game minutes >= 20 with at least 2 games played
        last_game_min = mins_list[0]
        if (min_trend >= 3 and games_played_last5 >= 2) or (last_game_min >= 20 and games_played_last5 >= 2):
            value_rows.append((v_score, player, min_trend, games_played_last5, round(avg_min_last5,1), last_game_min))

    safe_rows.sort(reverse=True, key=lambda x: x[0])
    value_rows.sort(reverse=True, key=lambda x: x[0])

    return games, safe_rows[:10], value_rows[:10]

def fmt_team_block(team, games, safe_rows, value_rows):
    out = []
    out.append(f"--- {team['full_name']} ---")
    out.append(f"Recent game IDs used (newest→older): {[g['id'] for g in games]}")
    out.append("")

    out.append("SAFE CORE (best for props):")
    if not safe_rows:
        out.append("- None")
    else:
        for score, player, gp3, avgm3 in safe_rows:
            out.append(f"- {score:>3}/100 | {player} | {gp3}/3 games | {avgm3} avg min (last 3)")

    out.append("")
    out.append("VALUE / BREAKOUT WATCH (role trending):")
    if not value_rows:
        out.append("- None")
    else:
        for score, player, trend, gp5, avgm5, lastm in value_rows:
            sign = "+" if trend >= 0 else ""
            out.append(f"- {score:>3}/100 | {player} | trend {sign}{trend} min | {gp5} games | {avgm5} avg min (last 5) | last {lastm} min")

    out.append("")
    return "\n".join(out)

def main():
    games = get_today_games()
    if not games:
        print("No NBA games today.")
        return

    out = []
    out.append("NBA PROP ENGINE (SAFE + VALUE)")
    out.append(f"UTC Date: {utc_today()}")
    out.append("")

    # Deduplicate games just in case
    seen_games = set()
    for g in games:
        if g["id"] in seen_games:
            continue
        seen_games.add(g["id"])

        home = g["home_team"]
        visitor = g["visitor_team"]

        out.append("===================================")
        out.append(f"{visitor['full_name']} @ {home['full_name']}")
        out.append("===================================")
        out.append("")

        for team in [visitor, home]:
            recent_games, safe_rows, value_rows = analyze_team(team)
            out.append(fmt_team_block(team, recent_games, safe_rows, value_rows))

    report = "\n".join(out)

    os.makedirs("reports", exist_ok=True)
    with open("reports/latest.txt", "w", encoding="utf-8") as f:
        f.write(report)

    print(report)

if __name__ == "__main__":
    main()
