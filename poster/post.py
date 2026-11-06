#!/usr/bin/env python3
"""NordicTidy posting robot.

Runs in GitHub Actions every hour. Posts the items in queue/*.json whose date is
today and whose time has passed (Europe/Copenhagen), and records them in
log/posted.json so nothing is posted twice. Items from earlier days that were
missed are skipped on purpose, so a late start never floods the accounts.

Environment (GitHub Secrets):
  PINTEREST_APP_ID, PINTEREST_APP_SECRET, PINTEREST_REFRESH_TOKEN
  IG_USER_ID, IG_TOKEN
  DRY_RUN=1 to only print what would be posted.
A platform whose secrets are missing is skipped without failing the run.
Only the Python standard library is used.
"""
import base64, datetime, glob, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "log", "posted.json")
TZ = ZoneInfo("Europe/Copenhagen")
PIN_API = os.environ.get("PINTEREST_API", "https://api.pinterest.com/v5")
IG_API = os.environ.get("IG_API", "https://graph.instagram.com/v21.0")
DRY = os.environ.get("DRY_RUN") == "1"
MAX_PER_RUN = {"pinterest": 6, "instagram": 2}


def http(method, url, headers=None, data=None, json_body=None):
    headers = dict(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode(); headers["Content-Type"] = "application/json"
    elif data is not None:
        body = urllib.parse.urlencode(data).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:600]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            raise RuntimeError(f"{method} {url.split('?')[0]} -> {e.code}: {msg}")


def load_log():
    if os.path.exists(LOG):
        return json.load(open(LOG))
    return {"pinterest": {}, "instagram": {}}


def save_log(log):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump(log, open(LOG, "w"), indent=1, sort_keys=True)


def due_items(platform, log, now):
    today = now.date().isoformat(); hm = now.strftime("%H:%M")
    items = []
    for f in sorted(glob.glob(os.path.join(ROOT, "queue", "*.json"))):
        for it in json.load(open(f)).get(platform, []):
            if it["date"] == today and it["time"] <= hm and it["id"] not in log[platform]:
                items.append(it)
    return sorted(items, key=lambda i: i["time"])[:MAX_PER_RUN[platform]]


def link_for(item):
    links = json.load(open(os.path.join(ROOT, "links.json")))
    return item.get("link") or links.get(item.get("product"), "https://nordictidy.etsy.com")


# ------------------------------------------------------------- Pinterest
def pinterest_token():
    app, secret, refresh = (os.environ.get(k, "") for k in ("PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_REFRESH_TOKEN"))
    if not (app and secret and refresh):
        return None
    basic = base64.b64encode(f"{app}:{secret}".encode()).decode()
    tok = http("POST", f"{PIN_API}/oauth/token", {"Authorization": f"Basic {basic}"},
               data={"grant_type": "refresh_token", "refresh_token": refresh})
    if tok.get("refresh_token") and tok["refresh_token"] != refresh:
        print("::warning::Pinterest issued a new refresh token. Update the PINTEREST_REFRESH_TOKEN secret (see README).")
    return tok["access_token"]


def pinterest_boards(token):
    H = {"Authorization": f"Bearer {token}"}
    boards, bookmark = {}, None
    while True:
        q = "?page_size=100" + (f"&bookmark={bookmark}" if bookmark else "")
        r = http("GET", f"{PIN_API}/boards{q}", H)
        for b in r.get("items", []):
            boards[b["name"].strip().lower()] = b["id"]
        bookmark = r.get("bookmark")
        if not bookmark:
            return boards


def post_pinterest(log, now):
    items = due_items("pinterest", log, now)
    if not items:
        print("Pinterest: nothing due"); return
    if DRY:
        for it in items: print(f"[dry] pin {it['id']} -> {it['board']}: {it['title']}")
        return
    token = pinterest_token()
    if not token:
        print("Pinterest: secrets not set, skipping"); return
    H = {"Authorization": f"Bearer {token}"}
    boards = pinterest_boards(token)
    for it in items:
        key = it["board"].strip().lower()
        if key not in boards:
            boards[key] = http("POST", f"{PIN_API}/boards", H, json_body={"name": it["board"], "privacy": "PUBLIC"})["id"]
            print(f"Pinterest: created board {it['board']}")
        with open(os.path.join(ROOT, it["image"]), "rb") as f:
            data = base64.b64encode(f.read()).decode()
        body = {"board_id": boards[key], "title": it["title"][:100], "description": it["description"][:500],
                "alt_text": it.get("alt_text", "")[:500], "link": link_for(it),
                "media_source": {"source_type": "image_base64", "content_type": "image/jpeg", "data": data}}
        pin = http("POST", f"{PIN_API}/pins", H, json_body=body)
        log["pinterest"][it["id"]] = {"pin_id": pin.get("id"), "at": now.isoformat(timespec="minutes")}
        save_log(log)
        print(f"Pinterest: posted {it['id']} as pin {pin.get('id')}")
        time.sleep(2)


# ------------------------------------------------------------- Instagram
def post_instagram(log, now):
    items = due_items("instagram", log, now)
    if not items:
        print("Instagram: nothing due"); return
    if DRY:
        for it in items: print(f"[dry] ig {it['id']}: {it['caption'][:60]!r}")
        return
    uid, token = os.environ.get("IG_USER_ID", ""), os.environ.get("IG_TOKEN", "")
    if not (uid and token):
        print("Instagram: secrets not set, skipping"); return
    repo = os.environ.get("GITHUB_REPOSITORY", "degier92/nordictidy-social")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    for it in items:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{it['image']}"
        c = http("POST", f"{IG_API}/{uid}/media", data={"image_url": url, "caption": it["caption"],
                                                        "alt_text": it.get("alt_text", ""), "access_token": token})
        cid = c["id"]
        for _ in range(20):
            st = http("GET", f"{IG_API}/{cid}?fields=status_code&access_token={urllib.parse.quote(token)}")
            if st.get("status_code") == "FINISHED": break
            if st.get("status_code") in ("ERROR", "EXPIRED"): raise RuntimeError(f"Instagram container {cid}: {st}")
            time.sleep(5)
        pub = http("POST", f"{IG_API}/{uid}/media_publish", data={"creation_id": cid, "access_token": token})
        log["instagram"][it["id"]] = {"media_id": pub.get("id"), "at": now.isoformat(timespec="minutes")}
        save_log(log)
        print(f"Instagram: posted {it['id']} as {pub.get('id')}")


def main():
    now = datetime.datetime.now(TZ)
    if os.environ.get("NOW"):  # for testing: NOW=2026-11-09T12:00
        now = datetime.datetime.fromisoformat(os.environ["NOW"]).replace(tzinfo=TZ)
    print(f"Run at {now:%Y-%m-%d %H:%M} Copenhagen{' (dry run)' if DRY else ''}")
    log = load_log()
    failed = []
    for name, fn in (("Pinterest", post_pinterest), ("Instagram", post_instagram)):
        try:
            fn(log, now)
        except Exception as e:
            print(f"::error::{name}: {e}"); failed.append(name)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
