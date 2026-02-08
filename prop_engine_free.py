import requests
import time
import os

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

headers = {
    "Authorization": API_KEY
}

LAST_CALL_TIME = 0

def rate_limit_wait():
    global LAST_CALL_TIME

    elapsed = time.time() - LAST_CALL_TIME

    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)

    LAST_CALL_TIME = time.time()


def safe_get(url, retries=5):

    backoff = 2

    for attempt in range(retries):

        rate_limit_wait()

        try:
            r = requests.get(url, headers=headers, timeout=15)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                print(f"⚠️ 429 Rate limited. Sleeping {backoff}s")
                time.sleep(backoff)
                backoff *= 2
                continue

            if r.status_code == 401:
                print("❌ Unauthorized endpoint — skipping")
                return {"data": []}

            print(f"⚠️ API Error {r.status_code}: {url}")

        except Exception as e:
            print("Request error:", e)

        time.sleep(backoff)
        backoff *= 2

    return {"data": []}
