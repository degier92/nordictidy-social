#!/usr/bin/env python3
"""Run ONCE on your Mac to get the Pinterest refresh token for GitHub.

    python3 pinterest_login.py

It asks for your App ID and App secret (from developers.pinterest.com),
opens Pinterest in your browser, and prints a refresh token. Paste that token
into the GitHub secret PINTEREST_REFRESH_TOKEN. Nothing is saved on disk.
Requires the redirect URI http://localhost:3003/pinterest on your Pinterest app.
"""
import base64, getpass, http.server, json, secrets, threading, urllib.parse, urllib.request, webbrowser

REDIRECT = "http://localhost:3003/pinterest"
SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"

app_id = input("Pinterest App ID: ").strip()
app_secret = getpass.getpass("Pinterest App secret (hidden while typing): ").strip()
state = secrets.token_urlsafe(16)
got = {}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write("<h2>Done. Go back to Terminal.</h2>".encode())

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("localhost", 3003), H)
th = threading.Thread(target=srv.handle_request, daemon=True); th.start()
url = "https://www.pinterest.com/oauth/?" + urllib.parse.urlencode(
    {"client_id": app_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPES, "state": state})
print("\nOpening Pinterest. Log in and press 'Give access'.\nIf nothing opens, paste this link into your browser:\n" + url)
webbrowser.open(url)
th.join(timeout=300); srv.server_close()
if got.get("state") != state or "code" not in got:
    raise SystemExit(f"Login failed: {got.get('error_description') or got.get('error') or 'no answer within 5 minutes'}")

basic = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
req = urllib.request.Request("https://api.pinterest.com/v5/oauth/token",
                             data=urllib.parse.urlencode({"grant_type": "authorization_code", "code": got["code"],
                                                          "redirect_uri": REDIRECT}).encode(),
                             headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
tok = json.load(urllib.request.urlopen(req))
print("\nCopy everything on the next line into the GitHub secret PINTEREST_REFRESH_TOKEN:\n")
print(tok["refresh_token"])
days = tok.get("refresh_token_expires_in", 0) // 86400
if days:
    print(f"\n(The refresh token is valid for about {days} days. Run this script again before then.)")
