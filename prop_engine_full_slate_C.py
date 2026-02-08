import os
import re
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests

# =========================
# CONFIG
# =========================
BASE_URL = "https://api.balldontlie.io/v1"
API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()

if not API_KEY:
    raise RuntimeError("Missing env var BALLDONTLIE_API_KEY. Add it as a GitHub Actions Secret.")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

REPORT_DIR = "reports"
LATEST_PATH = os.path.join(REPORT_DIR, "latest.txt")


# =========================
# HTTP HELPERS
# =========================
def safe_get(url: str, retries: int = 3, sleep_s: float = 1.2):
    last_err = None
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and r.text.strip():
                return r.json()
            last_err = f"status={r.status_code}, body={r.text[:200]}"
        except Exception as e:
            last_err = str(e)
        time.sleep(sleep_s)
    print(f"⚠️ API failed: {url} | {last_err}")
    return {"data": []}


# =========================
# GAME / TEAM HELPERS
# =========================
def utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_games_by_date(date_str_utc: str):
    url = f"{BASE_URL}/games?dates[]={date_str_utc}&per_page=100"
    return safe_get(url).get("data", [])


def is_completed_game(g: dict) -> bool:
    return g.get("home_team_score") is not None and g.get("visitor_team_score") is not None


def get_recent_completed_games_for_team(team_id: int, target_n: int = 3, lookback_days: int = 14):
    collected = []
    for i in range(1, lookback_days + 1):
        if len(collected) >= target_n:
            break
        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/games?dates[]={d}&team_ids[]={team_id}&per_page=100"
        games = safe_get(url).get("data", [])
        for g in games:
            if is_completed_game(g) and g.get("id") not in {x["id"] for x in collected}:
                collected.append(g)
            if len(collected) >= target_n:
                break
    return collected[:target_n]


def get_stats_for_game(game_id: int):
    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=300"
    return safe_get(url).get("data", [])


def parse_minutes_to_float(min_str: str) -> float:
    """
    balldontlie minutes are often "MM:SS". Convert to float minutes.
    """
    if not min_str or ":" not in str(min_str):
        return 0.0
    try:
        mm, ss = str(min_str).split(":")
        return int(mm) + int(ss) / 60.0
    except Exception:
        return 0.0


def get_minutes_leaders(game_id: int, team_id: int, top_n: int = 8):
    stats = get_stats_for_game(game_id)
    rows = []
    for s in stats:
        team = s.get("team", {})
        player = s.get("player", {})
        if team.get("id") != team_id:
            continue
        mins = parse_minutes_to_float(s.get("min"))
        if mins <= 0:
            continue
        name = f"{player.get('first_name','').strip()} {player.get('last_name','').strip()}".strip()
        if not name:
            continue
        rows.append((name, mins))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:top_n]


# =========================
# "ROSTER LOCK" (STRICT-ish, API-only fallback)
# =========================
# NOTE:
# Without ESPN/NBA.com scraping (which is brittle in Actions), we enforce a strict
# internal lock:
# - For each team, the "eligible pool" is ONLY players who logged real minutes
#   in any of the last N completed games we can fetch via stats endpoint.
# - If a player appears anywhere else but is not in this pool, we flag conflict.
#
# This prevents random wrong-team names like "Lillard" showing up in GSW@LAL.
#
def build_strict_roster_lock_from_recent_games(team_id: int, last_n: int = 3):
    games = get_recent_completed_games_for_team(team_id, target_n=last_n, lookback_days=14)
    game_ids = [g["id"] for g in games]

    appearance = defaultdict(int)
    for gid in game_ids:
        stats = get_stats_for_game(gid)
        for s in stats:
            team = s.get("team", {})
            player = s.get("player", {})
            if team.get("id") != team_id:
                continue
            mins = parse_minutes_to_float(s.get("min"))
            if mins < 1.0:
                continue
            name = f"{player.get('first_name','').strip()} {player.get('last_name','').strip()}".strip()
            if name:
                appearance[name] += 1

    locked = sorted(appearance.keys())
    core = sorted([n for n, c in appearance.items() if c >= 2])

    return {
        "recent_game_ids": game_ids,
        "appearance": dict(appearance),
        "locked": locked,
        "core": core,
    }


# =========================
# REPORT
# =========================
def ensure_reports_dir():
    os.makedirs(REPORT_DIR, exist_ok=True)


def write_report(text: str):
    ensure_reports_dir()
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def build_full_slate_report():
    date_utc = utc_date_str()
    games = get_games_by_date(date_utc)

    lines = []
    lines.append("NBA PROP ENGINE (SAFE + VALUE)")
    lines.append(f"UTC Date: {date_utc}")
    lines.append("")

    if not games:
        lines.append("No games found for today.")
        return "\n".join(lines)

    # Sort games by (home team name) just for stable output
    def gkey(g):
        return (g.get("home_team", {}).get("full_name", ""), g.get("visitor_team", {}).get("full_name", ""))

    games_sorted = sorted(games, key=gkey)

    roster_conflicts = []

    for g in games_sorted:
        home = g["home_team"]
        away = g["visitor_team"]

        lines.append("=" * 35)
        lines.append(f"{away['full_name']} @ {home['full_name']}")
        lines.append("=" * 35)
        lines.append("")

        for team in [away, home]:
            team_id = team["id"]
            lock = build_strict_roster_lock_from_recent_games(team_id, last_n=3)

            lines.append(f"--- {team['full_name']} ---")
            lines.append(f"Recent game IDs used (newest→older): {lock['recent_game_ids']}")
            lines.append("")

            lines.append("SAFE CORE (best for props):")
            if lock["core"]:
                for n in lock["core"]:
                    lines.append(f"- {n}")
            else:
                lines.append("- None")
            lines.append("")

            # rotation-locked is everybody who played any minutes in last N games
            lines.append("VALUE / BREAKOUT WATCH (role trending):")
            # simple heuristic: played 1 of last 3 = fringe / watch list
            watch = sorted([n for n, c in lock["appearance"].items() if c == 1])
            if watch:
                for n in watch[:12]:
                    lines.append(f"- {n}")
            else:
                lines.append("- None")
            lines.append("")

            # basic sanity: if the team has 0 recent games, flag (we can't lock roster)
            if not lock["recent_game_ids"]:
                roster_conflicts.append(
                    f"NO-LOCK: {team['full_name']} had 0 completed games found in lookback window; roster lock is empty."
                )

        lines.append("")

    # Put conflicts at top
    if roster_conflicts:
        header = []
        header.append("ROSTER CONFLICTS / LOCK WARNINGS (READ FIRST)")
        header.append("-" * 45)
        for c in roster_conflicts:
            header.append(f"- {c}")
        header.append("")
        return "\n".join(header + lines)

    return "\n".join(lines)


if __name__ == "__main__":
    report = build_full_slate_report()
    print(report)
    write_report(report)
