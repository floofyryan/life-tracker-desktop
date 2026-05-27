"""
pipboy_auth.py
--------------
Connects to your Vault-Tec Health Tracker Firebase project.
Uses Google Device Flow -- no redirect URI, no browser popup issues.

Requirements: Python 3.8+  (zero pip installs -- stdlib only)
Run:          python pipboy_auth.py
"""

import json, sys, time, webbrowser, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────
API_KEY    = "AIzaSyBjGLqYROWY2FHvjli7yJRSR0hZvy2GijU"
PROJECT_ID = "health-tracker-8d57d"
TOKEN_FILE = Path.home() / ".pipboy_token.json"
FIRESTORE  = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    f"/databases/(default)/documents"
)

# OAuth credentials — set these once. Shared with the root pipboy_auth.py.
# If you have already filled them in the root pipboy_auth.py you can import
# from there instead, but keeping them here makes this module self-contained.
CLIENT_ID     = ""
CLIENT_SECRET = ""

# Try to inherit credentials from the root module if this file's own are blank.
try:
    import sys as _sys, os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    import importlib as _il
    _root_auth = _il.import_module("pipboy_auth")
    if not CLIENT_ID:
        CLIENT_ID     = getattr(_root_auth, "CLIENT_ID",     "")
        CLIENT_SECRET = getattr(_root_auth, "CLIENT_SECRET", "")
except Exception:
    pass

# ── Safe print (handles Windows cp1252 terminals) ──────────────
def p(text=""):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))

# ── HTTP helpers ───────────────────────────────────────────────
def http_post(url, data, form=False):
    body = (urllib.parse.urlencode(data).encode() if form
            else json.dumps(data).encode())
    ct   = ("application/x-www-form-urlencoded" if form
            else "application/json")
    req  = urllib.request.Request(
        url, data=body, headers={"Content-Type": ct}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:    parsed = json.loads(raw)
        except: parsed = {"error": raw}
        return None, parsed
    except Exception as e:
        return None, {"error": str(e)}

def http_get(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:    parsed = json.loads(raw)
        except: parsed = {"error": raw}
        return None, parsed
    except Exception as e:
        return None, {"error": str(e)}

# ── Firestore unwrapping ───────────────────────────────────────
def unwrap(v):
    if not isinstance(v, dict):            return v
    if "stringValue"  in v:               return v["stringValue"]
    if "integerValue" in v:               return int(v["integerValue"])
    if "doubleValue"  in v:               return float(v["doubleValue"])
    if "booleanValue" in v:               return v["booleanValue"]
    if "nullValue"    in v:               return None
    if "arrayValue"   in v:
        return [unwrap(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue"     in v:
        return {k: unwrap(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return v

def parse_doc(doc):
    return {k: unwrap(v) for k, v in doc.get("fields", {}).items()}

# ── Date helpers ───────────────────────────────────────────────
def today_key():
    """VaultTec day rolls over at 4am."""
    now = datetime.now()
    if now.hour < 4:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")

def start_of_day_ms():
    now = datetime.now()
    if now.hour < 4:
        now -= timedelta(days=1)
    cutoff = now.replace(hour=4, minute=0, second=0, microsecond=0)
    return int(cutoff.timestamp() * 1000)

# ── Token persistence ──────────────────────────────────────────
def load_saved():
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return None

def save_token(d):
    TOKEN_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

# ── Google Device Flow ─────────────────────────────────────────
def device_login(client_id, client_secret):
    """
    Asks Google for a short user code, opens the browser,
    then polls until approved. Returns an access_token string.
    """
    resp, err = http_post(
        "https://oauth2.googleapis.com/device/code",
        {"client_id": client_id, "scope": "openid email profile"},
        form=True
    )
    if err or not resp:
        msg = (err.get("error_description") or err.get("error") or str(err)
               if isinstance(err, dict) else str(err))
        raise RuntimeError(f"Device code request failed: {msg}")

    device_code = resp["device_code"]
    user_code   = resp["user_code"]
    verify_url  = resp.get("verification_url", "https://google.com/device")
    interval    = int(resp.get("interval", 5))
    expires_in  = int(resp.get("expires_in", 300))

    p()
    p("  +--------------------------------------------------+")
    p("  |  STEP 1 - Your browser will open to:            |")
    p(f"  |  {verify_url:<48}|")
    p("  |                                                  |")
    p("  |  STEP 2 - Enter this code when asked:           |")
    p(f"  |  {user_code:<48}|")
    p("  |                                                  |")
    p("  |  STEP 3 - Come back here when done              |")
    p("  +--------------------------------------------------+")
    p()

    webbrowser.open(verify_url)

    # Poll until approved or expired
    deadline = time.time() + expires_in
    dot_count = 0
    while time.time() < deadline:
        time.sleep(interval)

        token_resp, poll_err = http_post(
            "https://oauth2.googleapis.com/token",
            {"client_id":     client_id,
             "client_secret": client_secret,
             "device_code":   device_code,
             "grant_type":    "urn:ietf:params:oauth:grant-type:device_code"},
            form=True
        )

        # Success
        if token_resp and "access_token" in token_resp:
            p()
            return token_resp["access_token"]

        # Get the error code from whichever dict has it
        err_code = None
        if token_resp and isinstance(token_resp, dict):
            err_code = token_resp.get("error")
        if not err_code and isinstance(poll_err, dict):
            err_code = poll_err.get("error")

        if err_code == "authorization_pending":
            dot_count += 1
            dots = "." * (dot_count % 4)
            print(f"  Waiting for you to approve in the browser{dots}   ", end="\r")
            continue
        elif err_code == "slow_down":
            interval += 5
            continue
        elif err_code == "expired_token":
            raise RuntimeError("Code expired. Run the script again.")
        elif err_code == "access_denied":
            raise RuntimeError("Sign-in was declined.")
        elif err_code:
            raise RuntimeError(f"Auth error: {err_code}")
        # No error code and no access_token — keep waiting
    raise TimeoutError("Sign-in timed out. Run the script again.")

# ── Firebase sign-in ───────────────────────────────────────────
def firebase_sign_in(access_token):
    """Exchange Google access_token for Firebase ID token + UID."""
    resp, err = http_post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={API_KEY}",
        {"postBody":            f"access_token={access_token}&providerId=google.com",
         "requestUri":          "http://localhost",
         "returnIdpCredential": True,
         "returnSecureToken":   True}
    )
    if err or not resp or "idToken" not in resp:
        # err can be a dict with nested error or a flat string error
        if isinstance(err, dict):
            inner = err.get("error", err)
            msg = (inner.get("message") if isinstance(inner, dict)
                   else str(inner))
        else:
            msg = str(err)
        raise RuntimeError(f"Firebase sign-in failed: {msg}")
    return {
        "id_token":      resp["idToken"],
        "refresh_token": resp.get("refreshToken", ""),
        "uid":           resp["localId"],
        "email":         resp.get("email", ""),
        "issued_at":     int(__import__("time").time())
    }

# ── Firestore fetchers ─────────────────────────────────────────
def fs_get(path, token):
    doc, err = http_get(f"{FIRESTORE}/{path}", token)
    if err or not doc or "fields" not in doc:
        return {}
    return parse_doc(doc)

def fs_logs_today(uid, token):
    start_ms = start_of_day_ms()
    docs, err = http_get(f"{FIRESTORE}/users/{uid}/logs?pageSize=500", token)
    if err or not docs:
        return []
    logs = []
    for raw in docs.get("documents", []):
        f  = parse_doc(raw)
        ts = f.get("ts", 0)
        if isinstance(ts, str):
            try:   ts = int(ts)
            except: ts = 0
        if ts >= start_ms:
            logs.append(f)
    return logs

# ── Terminal display (ASCII only for Windows compat) ───────────
def segbar(val, mx, width=10):
    try:
        filled = int(min(1.0, float(val) / max(1.0, float(mx))) * width)
    except (TypeError, ValueError, ZeroDivisionError):
        filled = 0
    return "#" * filled + "-" * (width - filled)

def row(label, value, warn=False):
    flag = "!" if warn else " "
    p(f"  {flag} {label:<20} {value}")

def print_report(uid, token):
    today = today_key()
    divider = "  " + "=" * 50

    p()
    p(divider)
    p(f"  VAULT-TEC DAILY REPORT  //  {today}")
    p(divider)

    # ── Daily totals ──────────────────────────────────────────
    daily = fs_get(f"users/{uid}/daily/{today}", token)
    if not daily:
        p()
        p("  No data synced for today yet.")
        p("  Open the app and log something, then run this again.")
    else:
        try:
            water  = float(daily.get("water")  or 0)
            sleep  = float(daily.get("sleep")  or 0)
            steps  = float(daily.get("steps")  or 0)
            active = float(daily.get("active") or 0)
            cond   = float(daily.get("condition") or daily.get("overall") or 0)
        except (TypeError, ValueError):
            water = sleep = steps = active = cond = 0

        p()
        p("  // VITALS")
        row("HYDRATION", f"{water:.1f} L   [{segbar(water, 3.0)}]",  warn=water < 1.5)
        row("SLEEP",     f"{sleep:.1f} H   [{segbar(sleep, 8.0)}]",  warn=sleep < 6)
        row("STEPS",     f"{int(steps):,}  [{segbar(steps, 10000)}]", warn=steps < 5000)
        row("ACTIVE",    f"{int(active)} MIN [{segbar(active, 30)}]", warn=active < 15)

        if cond:
            STATUS = [
                (95, "OPTIMAL CONDITION"),   (80, "FULLY OPERATIONAL"),
                (65, "SLIGHTLY IRRADIATED"), (50, "NEEDS STIMPAK"),
                (35, "CRITICAL CONDITION"),  (20, "SEVERELY DAMAGED"),
                (0,  "SEEK VAULT MEDIC"),
            ]
            label = next((l for t, l in STATUS if cond >= t), "UNKNOWN")
            p()
            p("  // CONDITION")
            row("OVERALL", f"{int(cond)}%  --  {label}", warn=cond < 50)

        PILLARS = [
            ("strength",   "STR"), ("endurance", "END"),
            ("perception", "PER"), ("agility",   "AGI"),
            ("focus",      "FOC"), ("tasks",     "TSK"),
        ]
        scores = {}
        for key, _ in PILLARS:
            try:   scores[key] = float(daily.get(key) or 0)
            except: scores[key] = 0.0
        if any(scores.values()):
            p()
            p("  // S.P.E.C.I.A.L.")
            for key, abbr in PILLARS:
                v = scores[key]
                p(f"     {abbr}  [{segbar(v, 100)}]  {int(v)}")

    # ── Goals ─────────────────────────────────────────────────
    goals = fs_get(f"users/{uid}/settings/goals", token)
    if goals:
        p()
        p("  // YOUR GOALS")
        try:   row("WATER",  f"{float(goals.get('waterGoalL', 3.0) or 3.0):.1f} L")
        except: pass
        try:   row("STEPS",  f"{int(float(goals.get('stepGoal', 10000) or 10000)):,}")
        except: pass
        try:   row("SLEEP",  f"{float(goals.get('sleepGoalH', 8.0) or 8.0):.1f} H")
        except: pass
        try:   row("ACTIVE", f"{int(float(goals.get('activeGoalMin', 30) or 30))} MIN")
        except: pass

    # ── Custom trackers ───────────────────────────────────────
    tc_cfg  = fs_get(f"users/{uid}/settings/trackers", token)
    configs = tc_cfg.get("configs", []) or []
    if configs:
        logs   = fs_logs_today(uid, token)
        totals = {}
        for log in logs:
            k = str(log.get("tracker", "")).lower().strip()
            try:    v = float(log.get("value", 0) or 0)
            except: v = 0.0
            totals[k] = totals.get(k, 0.0) + v
        p()
        p("  // CUSTOM TRACKERS")
        for t in configs:
            name       = str(t.get("name", ""))
            val        = totals.get(name.lower().strip(), 0.0)
            unit       = str(t.get("unit", ""))
            goal       = t.get("goal")
            is_toggle  = bool(t.get("isToggle", False))
            is_integer = bool(t.get("isInteger", False))
            if is_toggle:
                display = "ON" if val > 0 else "OFF"
            elif is_integer:
                display = str(int(val))
            else:
                display = f"{val:.1f}"
            bar_str = ""
            if goal:
                try:
                    g = float(goal)
                    if g > 0:
                        bar_str = f"  [{segbar(val, g)}]"
                except (TypeError, ValueError):
                    pass
            row(name.upper(), f"{display} {unit}{bar_str}")

    # ── Tasks ─────────────────────────────────────────────────
    todos_doc = fs_get(f"users/{uid}/settings/todos", token)
    todos     = todos_doc.get("items", []) or []
    if todos:
        done  = sum(1 for t in todos if t.get("done"))
        carry = 0
        for t in todos:
            if not t.get("done"):
                try:   carry += int(t.get("weight", 1) or 1)
                except: carry += 1
        p()
        p("  // TASKS")
        row("COMPLETED",    f"{done}/{len(todos)}")
        row("CARRY WEIGHT", f"{carry}/20", warn=carry > 20)
        pending = [t for t in todos if not t.get("done")][:5]
        if pending:
            p("     NEXT UP:")
            for t in pending:
                txt = str(t.get("text", ""))[:48]
                wgt = t.get("weight", 1)
                p(f"       [ ] {txt}  (W{wgt})")

    # ── Thesis ────────────────────────────────────────────────
    thesis   = fs_get(f"users/{uid}/settings/thesis", token)
    chapters = thesis.get("chapters", []) or []
    if chapters:
        try:
            total_w  = sum(int(c.get("currentWords", 0) or 0) for c in chapters)
            target_w = sum(int(c.get("targetWords",  0) or 0) for c in chapters)
            pct      = round(total_w / max(1, target_w) * 100)
        except (TypeError, ValueError):
            total_w = target_w = pct = 0

        today_w = 0
        for l in (thesis.get("writingLogs") or []):
            if l.get("date") == today:
                try:   today_w = int(l.get("words", 0) or 0)
                except: today_w = 0
                break

        p()
        p("  // THESIS")
        row("WORDS",   f"{total_w:,} / {target_w:,}  ({pct}%)")
        row("TODAY",   f"{today_w:,} words" if today_w else "-- not logged yet")
        defence = str(thesis.get("defenceDate") or "").strip()
        if defence:
            try:
                days = (datetime.strptime(defence, "%Y-%m-%d") - datetime.now()).days
                row("DEFENCE IN", f"{days} days  ({defence})", warn=days < 60)
            except:
                pass

    p()
    p(divider)
    p()

# ── Setup instructions ─────────────────────────────────────────
SETUP_MSG = """
  +======================================================+
  |           ONE-TIME SETUP REQUIRED                    |
  +======================================================+

  You need a Desktop OAuth Client from Google Cloud.
  Takes about 3 minutes. Only done once ever.

  STEP 1 - Open this URL in your browser:
    https://console.cloud.google.com/apis/credentials

    Make sure "health-tracker-8d57d" is selected in the
    project dropdown at the top of the page.

  STEP 2 - Create the credential:
    Click  + CREATE CREDENTIALS
    Choose   OAuth client ID
    Type:    Desktop app
    Name:    Pip-Boy Desktop  (can be anything)
    Click    CREATE

  STEP 3 - Copy your credentials:
    A popup shows Client ID and Client Secret. Copy both.

  STEP 4 - Paste them into this file:
    Open pipboy_auth.py in Notepad (right-click -> Edit)
    Find these two lines near the top:
      CLIENT_ID     = ""
      CLIENT_SECRET = ""
    Paste your values inside the quotes and save.

  STEP 5 - Run again:
    python pipboy_auth.py
"""

# ── Main ───────────────────────────────────────────────────────
def main():
    p()
    p("  VAULT-TEC HEALTH COMPANION  //  Pip-Boy Data Link v1.0")
    p("  " + "-" * 50)

    if not CLIENT_ID or not CLIENT_SECRET:
        p(SETUP_MSG)
        sys.exit(0)

    # --reauth flag forces a fresh login regardless of saved session
    force_reauth = "--reauth" in sys.argv

    # Try saved session first
    saved = load_saved()
    if not force_reauth and saved and saved.get("id_token") and saved.get("uid"):
        p()
        p(f"  Saved session found: {saved.get('email', 'unknown')}")
        p(f"  Has refresh token: {'YES' if saved.get('refresh_token') else 'NO -- run with --reauth'}")
        p(f"  (Run with --reauth to sign in with a different account)")
        p()
        # If no refresh_token, warn user
        if not saved.get("refresh_token"):
            p("  WARNING: No refresh token saved. Token will expire after 1 hour.")
            p("  Run: python pipboy_auth.py --reauth   to fix this.")
            p()
        uid   = saved["uid"]
        token = saved["id_token"]
    else:
        p()
        p("  No saved session found. Starting Google sign-in...")
        p()
        try:
            access = device_login(CLIENT_ID, CLIENT_SECRET)
            p()
            p("  Authenticating with Firebase...")
            auth  = firebase_sign_in(access)
            uid   = auth["uid"]
            token = auth["id_token"]
            save_token(auth)
            p(f"  OK Signed in as: {auth['email']}")
            p(f"  OK UID: {uid}")
            p(f"  OK Session saved to: {TOKEN_FILE}")
        except Exception as e:
            p()
            p(f"  ERROR: {e}")
            sys.exit(1)

    p()
    p("  Fetching your Firestore data...")
    try:
        print_report(uid, token)
        p("  OK Connection successful! All data is linking correctly.")
        p("  Ready to build the UI on top of this.")
        p()
    except Exception as e:
        p()
        p(f"  ERROR fetching data: {e}")
        p()
        p(f"  Your Firebase token may have expired.")
        p(f"  Fix: delete {TOKEN_FILE} and run again to re-authenticate.")
        p()
        sys.exit(1)

if __name__ == "__main__":
    main()
