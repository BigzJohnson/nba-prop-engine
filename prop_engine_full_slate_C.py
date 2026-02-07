import os
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict

API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
BASE_URL = "https://api.balldontlie.io/v1"

if not API_KEY:
    raise RuntimeError("Missing BALLDONTLIE_API_KEY env var. Add it as a GitHub Actions secret.")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}


# -----------------------------
# HTTP + Pagination Helpers
# -----------------------------
def _request_json(url: str, retries: int = 5, backoff: float = 1.2) -> dict:
    """
    Robust GET with retries + basic rate-limit handling.
    """
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            # Handle rate limiting / transient errors
            if r.status_code in (429, 500, 502, 503, 504):
                sleep_s = backoff * (attempt + 1)
                time.sleep(sleep_s)
                continue

            if r.status_code != 200:
                # Print the first ~200 chars to help debugging without spamming logs
                body = (r.text or "")[:200]
                raise RuntimeError(f"HTTP {r.status_code} for {url} | body: {body}")

            return r.json()

        except Exception as e:
            last_err = e
            time.sleep(backoff * (attempt + 1))

    raise RuntimeError(f"Failed after retries for {url}. Last error: {last_err}")


def get_paginated(url: str) -> list:
    """
    Fetch all pages from a Balldontlie v1 endpoint.
    Expects response shape: { data: [...], meta: { total_pages, ... } }
    """
    all_data = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        page_url = f"{url}{sep}page={page}"
        j = _request_json(page_url)
        data = j.get("data", []) or []
        meta = j.get("meta", {}) or {}

        all_data.extend(data)

        total_pages = int(meta.get("total_pages", 1) or 1)
        if page >= total_pages:
            break

        page += 1
        time.sleep(0.25)  # be nice to the API

    return all_data


# -----------------------------
# Minutes Parsing (FIXED)
# -----------------------------
def parse_minutes_to_float(min_val) -> float:
    """
    Accepts formats like:
      - "34:12"
      - "34"
      - 34
      - "0:00", "0", None
    Returns minutes as float.
    """
    if min_val is None:
        return 0.0

    s = str(min_val).strip()
    if not s or s in {"0", "00", "0:00", "00:00"}:
        return 0.0

    if ":" in s:
        try:
            mm, ss = s.split(":")
            return float(mm) + float(ss) / 60.0
        except Exception:
            return 0.0

    try:
        return float(s)
    except Exception:
        return 0.0


# -----------------------------
# NBA Data Fetch
# -----------------------------
def utc_today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_today_games() -> list:
    today = utc_today_str()
    url = f"{BASE_URL}/games?dates[]={today}&per_page=100"
    games = get_paginated(url)

    # Keep only NBA games (defensive; should already be NBA if your account is NBA only)
    # If needed later, we can filter by league/season fields.
    return games


def is_completed_game(g: dict) -> bool:
    """
    Balldontlie sometimes uses different signals.
    Prefer final scores, fallback to 'status' if present.
    """
    hs = g.get("home_team_score")
    vs = g.get("visitor_team_score")
    if hs is not None and vs is not None:
        return True

    status = (g.get("status") or "").lower()
    # Common-ish patterns:
    if "final" in status:
        return True

    return False


def get_recent_completed_games_for_team(team_id: int, target_n: int = 3, lookback_days: int = 18) -> list:
    """
    Collect up to target_n most recent completed games for a team by scanning backwards.
    Returns list of game dicts, newest first.
    """
    collected = []
    seen_ids = set()

    for i in range(1, lookback_days + 1):
        if len(collected) >= target_n:
            break

        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/games?dates[]={d}&team_ids[]={team_id}&per_page=100"
        games = get_paginated(url)

        # games from that date; keep only completed
        for g in games:
            gid = g.get("id")
            if not gid or gid in seen_ids:
                continue
            if is_completed_game(g):
                collected.append(g)
                seen_ids.add(gid)
                if len(collected) >= target_n:
                    break

    # “newest first” — scanning backwards already tends to do that, but ensure stable order
    # If API includes 'date', use it; else keep insertion order.
    def _date_key(x):
        return x.get("date") or ""

    collected.sort(key=_date_key, reverse=True)
    return collected[:target_n]


def get_players_who_played_for_team_in_game(game_id: int, team_id: int) -> set:
    """
    Uses /stats to find players who logged >= 1.0 minute for team_id in game_id.
    """
    url = f"{BASE_URL}/stats?game_ids[]={game_id}&per_page=100"
    stats = get_paginated(url)

    names = set()
    for s in stats:
        t = s.get("team") or {}
        p = s.get("player") or {}
        if (t.get("id") != team_id) or (not p):
            continue

        mins = parse_minutes_to_float(s.get("min"))
        if mins >= 1.0:
            full = f"{p.get('first_name', '').strip()} {p.get('last_name', '').strip()}".strip()
            if full:
                names.add(full)

    return names


# -----------------------------
# SAFE / VALUE Logic
# -----------------------------
def analyze_team_rotation(team: dict, last_n: int = 3):
    team_id = team["id"]
    recent_games = get_recent_completed_games_for_team(team_id, target_n=last_n, lookback_days=18)
    game_ids = [g["id"] for g in recent_games]

    appearance = defaultdict(int)
    for g in recent_games:
        players = get_players_who_played_for_team_in_game(g["id"], team_id)
        for name in players:
            appearance[name] += 1

    games_used = len(recent_games)

    # Threshold:
    # - If we only found 1 game, "core" is >=1 (otherwise everything is None)
    # - If 2 games, core is >=2
    # - If 3 games, core is >=2
    if games_used <= 1:
        core_threshold = 1
    elif games_used == 2:
        core_threshold = 2
    else:
        core_threshold = 2

    safe_core = sorted([n for n, c in appearance.items() if c >= core_threshold])
    value_watch = sorted([n for n, c in appearance.items() if c == 1])

    return game_ids, safe_core, value_watch


# -----------------------------
# Report Build + Save
# -----------------------------
def build_report() -> str:
    games = get_today_games()

    lines = []
    lines.append("NBA PROP ENGINE (SAFE + VALUE)")
    lines.append(f"UTC Date: {utc_today_str()}")
    lines.append("")

    for g in games:
        home = g.get("home_team") or {}
        visitor = g.get("visitor_team") or {}
        if not home or not visitor:
            continue

        lines.append("===================================")
        lines.append(f"{visitor.get('full_name','Visitor')} @ {home.get('full_name','Home')}")
        lines.append("===================================")

        for team in (visitor, home):
            game_ids, safe_core, value_watch = analyze_team_rotation(team, last_n=3)

            lines.append(f"--- {team['full_name']} ---")
            lines.append(f"Recent game IDs used (newest→older): {game_ids}")

            lines.append("SAFE CORE (best for props):")
            if safe_core:
                for p in safe_core:
                    lines.append(f"- {p}")
            else:
                lines.append("- None")

            lines.append("VALUE / BREAKOUT WATCH (role trending):")
            if value_watch:
                for p in value_watch:
                    lines.append(f"- {p}")
            else:
                lines.append("- None")

            lines.append("")  # blank line between teams

    return "\n".join(lines)


def save_report(text: str):
    os.makedirs("reports", exist_ok=True)
    with open("reports/latest.txt", "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    report = build_report()
    save_report(report)
    print(report)
