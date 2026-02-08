import requests
import time
import os
import random
from collections import deque

# ================================
# API CONFIG
# ================================

API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"

headers = {
    "Authorization": API_KEY
}

# ================================
# GLOBAL RATE LIMIT SYSTEM
# Ensures NEVER >60 calls in 60 sec
# ================================

CALL_HISTORY = deque(maxlen=60)

def rate_limit_wait():

    while True:
        now = time.time()

        if len(CALL_HISTORY) < 60:
            break

        oldest = CALL_HISTORY[0]

        if now - oldest > 60:
            break

        sleep_time = 60 - (now - oldest) + 0.25
        print(f"⏳ Rate limit window wait {sleep_time:.2f}s")
        time.sleep(sleep_time)

    CALL_HISTORY.append(time.time())

    # small jitter prevents burst patterns
    time.sleep(random.uniform(0.05, 0.15))


# ================================
# SAFE API REQUEST
# ================================

def safe_get(url, retries=6):

    backoff = 2

    for attempt in range(retries):

        rate_limit_wait()

        try:
            r = requests.get(url, headers=headers, timeout=20)

            # SUCCESS
            if r.status_code == 200:
                return r.json()

            # RATE LIMIT
            if r.status_code == 429:
                wait = backoff + random.uniform(0.5, 1.5)
                print(f"⚠️ 429 Rate limited. Sleeping {wait:.2f}s")
                time.sleep(wait)
                backoff *= 2
                continue

            # UNAUTHORIZED ENDPOINT
            if r.status_code == 401:
                print("❌ Unauthorized endpoint — skipping")
                return {"data": []}

            # OTHER ERROR
            print(f"⚠️ API Error {r.status_code}: {url}")

        except Exception as e:
            print("Request error:", e)

        time.sleep(backoff)
        backoff *= 2

    return {"data": []}
