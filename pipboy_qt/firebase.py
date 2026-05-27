"""
firebase.py
-----------
All Firebase REST API calls. No UI dependencies.
Token management, Firestore read/write, date helpers.
"""

import json, time, math, uuid
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

API_KEY    = "AIzaSyBjGLqYROWY2FHvjli7yJRSR0hZvy2GijU"
PROJECT_ID = "health-tracker-8d57d"
TOKEN_FILE = Path.home() / ".pipboy_token.json"
CONFIG_FILE= Path.home() / ".pipboy_config.json"
FIRESTORE  = (f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
              f"/databases/(default)/documents")
TOKEN_EXPIRY_S = 55 * 60   # refresh at 55 min, expires at 60

# ── HTTP ───────────────────────────────────────────────────────
def _req(url, method="GET", data=None, token=None, form=False):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:    return None, json.loads(raw)
        except: return None, {"error": raw}
    except Exception as e:
        return None, {"error": str(e)}

# ── Firestore codec ────────────────────────────────────────────
def unwrap(v):
    if not isinstance(v, dict): return v
    if "stringValue"  in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue"  in v: return float(v["doubleValue"])
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue"    in v: return None
    if "arrayValue"   in v:
        return [unwrap(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue"     in v:
        return {k: unwrap(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return v

def wrap(val):
    if val is None:            return {"nullValue": None}
    if isinstance(val, bool):  return {"booleanValue": val}
    if isinstance(val, int):   return {"integerValue": str(val)}
    if isinstance(val, float): return {"doubleValue": val}
    if isinstance(val, str):   return {"stringValue": val}
    if isinstance(val, list):
        return {"arrayValue": {"values": [wrap(x) for x in val]}}
    if isinstance(val, dict):
        return {"mapValue": {"fields": {k: wrap(v) for k, v in val.items()}}}
    return {"stringValue": str(val)}

def parse_doc(doc):
    return {k: unwrap(v) for k, v in doc.get("fields", {}).items()}

# ── Firestore operations ───────────────────────────────────────
def fs_get(path, token):
    doc, err = _req(f"{FIRESTORE}/{path}", token=token)
    if err:
        inner  = err.get("error", err) if isinstance(err, dict) else {}
        code   = inner.get("code", 0)  if isinstance(inner, dict) else 0
        status = inner.get("status","") if isinstance(inner, dict) else str(err)
        if code in (401, 403) or "UNAUTHENTICATED" in status or "PERMISSION_DENIED" in status:
            return {"_auth_error": True}
        return {}
    if not doc or "fields" not in doc: return {}
    return parse_doc(doc)

def fs_set_field(path, data, token):
    fields = {k: wrap(v) for k, v in data.items()}
    mask   = "&".join(f"updateMask.fieldPaths={k}" for k in data)
    return _req(f"{FIRESTORE}/{path}?{mask}", "PATCH", {"fields": fields}, token)

def fs_patch_full(path, data, token):
    """Full document replace (no updateMask) — matches Android set() behaviour."""
    fields = {k: wrap(v) for k, v in data.items()}
    return _req(f"{FIRESTORE}/{path}", "PATCH", {"fields": fields}, token)

def fs_add(col, data, token):
    fields = {k: wrap(v) for k, v in data.items()}
    return _req(f"{FIRESTORE}/{col}", "POST", {"fields": fields}, token)

def fs_delete(path, token):
    return _req(f"{FIRESTORE}/{path}", "DELETE", token=token)

def fs_list(path, token, page_size=500):
    doc, err = _req(f"{FIRESTORE}/{path}?pageSize={page_size}", token=token)
    return doc or {}, err

# ── Token management ───────────────────────────────────────────
def load_session():
    if TOKEN_FILE.exists():
        try: return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except: pass
    return None

def save_session(d):
    TOKEN_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except: pass
    return {}

def save_config(d):
    CONFIG_FILE.write_text(json.dumps(d), encoding="utf-8")

def refresh_id_token(refresh_tok):
    """Exchange refresh token for new ID token. No auth header."""
    body = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": refresh_tok
    }).encode()
    req = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            return d.get("id_token"), d.get("refresh_token")
    except Exception as e:
        print(f"Token refresh error: {e}")
        return None, None

def maybe_refresh_token(session):
    """
    Synchronously refresh if token is near expiry.
    Returns (updated_session, token_string).
    Must be called from a background thread.
    """
    if not session: return session, None
    token = session.get("id_token", "")
    rtok  = session.get("refresh_token", "")
    if not rtok:
        return session, token   # no refresh token — use as-is
    issued = session.get("issued_at", 0)
    age    = int(time.time()) - issued if issued else TOKEN_EXPIRY_S + 1
    if age < TOKEN_EXPIRY_S:
        return session, token   # still fresh
    new_id, new_ref = refresh_id_token(rtok)
    if new_id:
        session = dict(session)
        session["id_token"]      = new_id
        session["refresh_token"] = new_ref or rtok
        session["issued_at"]     = int(time.time())
        save_session(session)
        return session, new_id
    return session, token   # refresh failed, return old token

# ── Date helpers ───────────────────────────────────────────────
def today_key():
    """VaultTec day rolls over at 4am."""
    now = datetime.now()
    if now.hour < 4: now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")

def day_start_ms():
    now = datetime.now()
    if now.hour < 4: now -= timedelta(days=1)
    return int(now.replace(hour=4,minute=0,second=0,microsecond=0).timestamp()*1000)

def sf(v, d=0.0):
    try: return float(v or 0)
    except: return d

# ── Data layer — single fetch of all collections ───────────────
def fetch_all(uid, token):
    """
    Fetch everything needed to render the app.
    Returns a dict of all data, plus '_auth_error' key if token is bad.
    """
    today    = today_key()
    daily    = fs_get(f"users/{uid}/daily/{today}", token)

    if daily.get("_auth_error"):
        return {"_auth_error": True}

    goals     = fs_get(f"users/{uid}/settings/goals",      token)
    thesis    = fs_get(f"users/{uid}/settings/thesis",     token)
    todos_doc = fs_get(f"users/{uid}/settings/todos",      token)
    tc_doc    = fs_get(f"users/{uid}/settings/trackers",   token)
    lg_doc    = fs_get(f"users/{uid}/settings/lifegoals",  token)
    dl_doc    = fs_get(f"users/{uid}/settings/deadlines",  token)

    # Today's logs
    logs_raw, _ = fs_list(f"users/{uid}/logs", token)
    start_ms    = day_start_ms()
    logs = []
    for raw in logs_raw.get("documents", []):
        f = parse_doc(raw)
        ts = f.get("ts", 0)
        if isinstance(ts, str):
            try: ts = int(ts)
            except: ts = 0
        if ts >= start_ms:
            logs.append(f)

    return {
        "daily":      daily,
        "goals":      goals,
        "thesis":     thesis,
        "todos":      todos_doc.get("items", []) or [],
        "trackers":   tc_doc.get("configs", []) or [],
        "life_goals": lg_doc.get("items", []) or [],
        "deadlines":  dl_doc.get("items", []) or [],
        "logs":       logs,
    }

def tracker_totals(logs):
    totals = {}
    for log in logs:
        k = str(log.get("tracker","")).lower().strip()
        try: v = float(log.get("value",0) or 0)
        except: v = 0
        totals[k] = totals.get(k, 0) + v
    return totals

# ── Write helpers ─────────────────────────────────────────────
def log_activity(uid, token, tracker, value, unit=""):
    """Matches Android logActivity: add to logs + update daily total."""
    ts  = int(time.time() * 1000)
    key = tracker.lower().strip()
    fs_add(f"users/{uid}/logs", {
        "tracker": key, "value": str(value),
        "unit": unit, "type": key,
        "ts": ts, "timestamp": ts
    }, token)
    fresh = fs_get(f"users/{uid}/daily/{today_key()}", token)
    cur   = sf(fresh.get(key))
    new_v = max(0.0, round(cur + float(value), 3))
    fs_set_field(f"users/{uid}/daily/{today_key()}", {key: new_v}, token)

def save_todos(uid, token, todos):
    items_w = [wrap(t) for t in todos]
    _req(f"{FIRESTORE}/users/{uid}/settings/todos?updateMask.fieldPaths=items",
         "PATCH",
         {"fields": {"items": {"arrayValue": {"values": items_w}}}},
         token)

def save_thesis(uid, token, thesis):
    """Full replace — matches Android saveThesisData."""
    fs_patch_full(f"users/{uid}/settings/thesis", thesis, token)

def save_note(uid, token, date_key, text):
    if text.strip():
        fs_patch_full(f"users/{uid}/notes/{date_key}", {"text": text.strip()}, token)
    else:
        fs_delete(f"users/{uid}/notes/{date_key}", token)

def load_note(uid, token, date_key):
    doc = fs_get(f"users/{uid}/notes/{date_key}", token)
    return str(doc.get("text",""))

def save_life_goals(uid, token, goals):
    items_w = [wrap(g) for g in goals]
    _req(f"{FIRESTORE}/users/{uid}/settings/lifegoals?updateMask.fieldPaths=items",
         "PATCH",
         {"fields": {"items": {"arrayValue": {"values": items_w}}}},
         token)

def save_deadlines(uid, token, deadlines):
    items_w = [wrap(d) for d in deadlines]
    _req(f"{FIRESTORE}/users/{uid}/settings/deadlines?updateMask.fieldPaths=items",
         "PATCH",
         {"fields": {"items": {"arrayValue": {"values": items_w}}}},
         token)

def save_focus_session(uid, token, start_ms, end_ms, duration_mins, label):
    fs_add(f"users/{uid}/focusSessions", {
        "startMs": start_ms, "endMs": end_ms,
        "durationMins": duration_mins, "label": label
    }, token)

# ── Condition helpers ──────────────────────────────────────────
STATUS_LABELS = [
    (95, "OPTIMAL CONDITION"),
    (80, "FULLY OPERATIONAL"),
    (65, "SLIGHTLY IRRADIATED"),
    (50, "NEEDS STIMPAK"),
    (35, "CRITICAL CONDITION"),
    (20, "SEVERELY DAMAGED"),
    (0,  "SEEK VAULT MEDIC"),
]

def condition_label(score):
    for t, l in STATUS_LABELS:
        if score >= t: return l
    return "UNKNOWN"

RANK_TITLES = [
    (20, "PROFESSOR EMERITUS"),
    (16, "DEPARTMENT HEAD"),
    (12, "PRINCIPAL INVESTIGATOR"),
    (8,  "SENIOR ANALYST"),
    (5,  "FIELD OPERATIVE"),
    (3,  "JUNIOR SCHOLAR"),
    (1,  "FRESHMAN RESEARCHER"),
]

def academic_rank(total_xp):
    level = max(1, int(math.floor(math.sqrt(total_xp / 100.0))))
    xp_cur  = (level * level) * 100
    xp_next = ((level+1)*(level+1)) * 100
    rank = "FRESHMAN RESEARCHER"
    for min_lv, title in reversed(RANK_TITLES):
        if level >= min_lv: rank = title; break
    return level, xp_cur, xp_next, rank
