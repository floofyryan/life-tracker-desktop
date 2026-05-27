"""
pipboy_app.py  -- Pip-Boy Health Companion (PyQt6)
--------------------------------------------------
Small always-on-top bar that expands to a full panel.
Run: python pipboy_app.py

Requires: pip install PyQt6
Auth:     run pipboy_auth.py first to create ~/.pipboy_token.json
"""

import sys, json, time, threading, math, uuid
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QScrollArea, QFrame, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QTabWidget, QButtonGroup,
    QRadioButton, QSystemTrayIcon, QMenu, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore  import Qt, QTimer, QThread, pyqtSignal, QPoint, QPropertyAnimation, QRect, QEasingCurve
from PyQt6.QtGui   import QPainter, QColor, QPen, QFont, QIcon, QPixmap, QCursor, QLinearGradient

# ?? Config ??????????????????????????????????????????????????????
API_KEY     = "AIzaSyBjGLqYROWY2FHvjli7yJRSR0hZvy2GijU"
PROJECT_ID  = "health-tracker-8d57d"
TOKEN_FILE  = Path.home() / ".pipboy_token.json"
CONFIG_FILE = Path.home() / ".pipboy_config.json"
FIRESTORE   = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
TOKEN_EXPIRY = 55 * 60

# ?? Palette ??????????????????????????????????????????????????????
BK = "#071109"; SF = "#0A1A0A"; SM = "#1A4A1A"
G  = "#00FF66"; GD = "#00AA44"; AM = "#FFB000"; RD = "#FF3333"
TD = "#00CC55"; TM = "#004422"

# ?? Sizes ????????????????????????????????????????????????????????
BAR_W, BAR_H     = 340, 52   # compact bar
PANEL_W, PANEL_H = 340, 580  # expanded panel

# ????????????????????????????????????????????????????????????????
# FIREBASE LAYER
# ????????????????????????????????????????????????????????????????
def _req(url, method="GET", data=None, token=None, form=False):
    headers = {}
    if token: headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
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

def _unwrap(v):
    if not isinstance(v, dict): return v
    if "stringValue"  in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue"  in v: return float(v["doubleValue"])
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue"    in v: return None
    if "arrayValue"   in v: return [_unwrap(x) for x in v["arrayValue"].get("values",[])]
    if "mapValue"     in v: return {k:_unwrap(x) for k,x in v["mapValue"].get("fields",{}).items()}
    return v

def _wrap(val):
    if val is None:           return {"nullValue": None}
    if isinstance(val,bool):  return {"booleanValue": val}
    if isinstance(val,int):   return {"integerValue": str(val)}
    if isinstance(val,float): return {"doubleValue": val}
    if isinstance(val,str):   return {"stringValue": val}
    if isinstance(val,list):  return {"arrayValue":{"values":[_wrap(x) for x in val]}}
    if isinstance(val,dict):  return {"mapValue":{"fields":{k:_wrap(v) for k,v in val.items()}}}
    return {"stringValue": str(val)}

def _parse(doc):
    return {k:_unwrap(v) for k,v in doc.get("fields",{}).items()}

def fs_get(path, token):
    doc, err = _req(f"{FIRESTORE}/{path}", token=token)
    if err:
        inner  = err.get("error",err) if isinstance(err,dict) else {}
        code   = inner.get("code",0)  if isinstance(inner,dict) else 0
        status = inner.get("status","") if isinstance(inner,dict) else str(err)
        if code in (401,403) or "UNAUTHENTICATED" in status or "PERMISSION_DENIED" in status:
            return {"_auth_error": True}
        return {}
    if not doc or "fields" not in doc: return {}
    return _parse(doc)

def fs_set(path, data, token, full=False):
    fields = {k:_wrap(v) for k,v in data.items()}
    if full:
        return _req(f"{FIRESTORE}/{path}", "PATCH", {"fields":fields}, token)
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in data)
    return _req(f"{FIRESTORE}/{path}?{mask}", "PATCH", {"fields":fields}, token)

def fs_add(col, data, token):
    return _req(f"{FIRESTORE}/{col}", "POST",
                {"fields":{k:_wrap(v) for k,v in data.items()}}, token)

def fs_save_array(path, field, items, token):
    vals = [_wrap(x) for x in items]
    mask = f"updateMask.fieldPaths={field}"
    return _req(f"{FIRESTORE}/{path}?{mask}", "PATCH",
                {"fields":{field:{"arrayValue":{"values":vals}}}}, token)

def refresh_token(rtok):
    body = urllib.parse.urlencode(
        {"grant_type":"refresh_token","refresh_token":rtok}).encode()
    req = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
        data=body, headers={"Content-Type":"application/x-www-form-urlencoded"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            return d.get("id_token"), d.get("refresh_token")
    except Exception as e:
        print(f"Token refresh failed: {e}")
        return None, None

def today_key():
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

def ensure_fresh_token(session):
    """
    Synchronously refresh token if near expiry.
    Always returns (session, token) — never raises.
    Must be called from a background thread.
    """
    if not session: return session, None
    token = session.get("id_token", "")
    rtok  = session.get("refresh_token", "")

    # No refresh token — can't auto-refresh, use token as-is
    # (will fail at Firestore and trigger inline retry)
    if not rtok:
        print("WARNING: no refresh_token in session -- run pipboy_auth.py --reauth")
        return session, token

    # If issued_at is missing, treat as expired so we proactively refresh
    # rather than waiting for Firestore to return a 401.
    issued = session.get("issued_at", 0) or 0

    age = int(time.time()) - issued
    if issued and age < TOKEN_EXPIRY:
        return session, token  # Still fresh

    # Token is old — refresh now before making any Firestore calls
    print(f"Token age {age}s >= {TOKEN_EXPIRY}s, refreshing...")
    new_id, new_ref = refresh_token(rtok)
    if new_id:
        session = dict(session)  # Don't mutate the original
        session["id_token"]      = new_id
        session["refresh_token"] = new_ref or rtok
        session["issued_at"]     = int(time.time())
        save_session(session)
        print("Token refreshed successfully")
        return session, new_id

    # Refresh failed (network issue?) — return old token and let
    # Firestore reject it, triggering the inline retry in _fetch
    print("Token refresh failed -- will retry inline")
    return session, token

def fetch_all(uid, token):
    today = today_key()
    daily = fs_get(f"users/{uid}/daily/{today}", token)
    if daily.get("_auth_error"): return {"_auth_error":True}

    goals     = fs_get(f"users/{uid}/settings/goals",     token)
    thesis    = fs_get(f"users/{uid}/settings/thesis",    token)
    todos_doc = fs_get(f"users/{uid}/settings/todos",     token)
    tc_doc    = fs_get(f"users/{uid}/settings/trackers",  token)
    lg_doc    = fs_get(f"users/{uid}/settings/lifegoals", token)
    dl_doc    = fs_get(f"users/{uid}/settings/deadlines", token)
    ja_doc    = fs_get(f"users/{uid}/settings/jobapps",   token)

    logs_raw,_ = _req(f"{FIRESTORE}/users/{uid}/logs?pageSize=500", token=token)
    start_ms   = day_start_ms()
    logs = []
    for raw in (logs_raw or {}).get("documents",[]):
        f = _parse(raw)
        ts = f.get("ts",0)
        if isinstance(ts,str):
            try: ts=int(ts)
            except: ts=0
        if ts >= start_ms: logs.append(f)

    totals = {}
    for log in logs:
        k = str(log.get("tracker","")).lower().strip()
        try: v = float(log.get("value",0) or 0)
        except: v = 0
        totals[k] = totals.get(k,0)+v

    return {
        "daily":      daily,
        "goals":      goals,
        "thesis":     thesis,
        "todos":      todos_doc.get("items",[]) or [],
        "trackers":   tc_doc.get("configs",[]) or [],
        "life_goals": lg_doc.get("items",[]) or [],
        "deadlines":  dl_doc.get("items",[]) or [],
        "job_apps":   ja_doc.get("apps",[]) or [],
        "logs":       logs,
        "totals":     totals,
        "theme_color": str(goals.get("themeColor") or "#00FF66"),
    }

STATUS = [(95,"OPTIMAL CONDITION",G),(80,"FULLY OPERATIONAL",G),
          (65,"SLIGHTLY IRRADIATED",AM),(50,"NEEDS STIMPAK",AM),
          (35,"CRITICAL CONDITION",RD),(20,"SEVERELY DAMAGED",RD),
          (0,"SEEK VAULT MEDIC",RD)]
def cond_info(s):
    for t,l,c in STATUS:
        if s>=t: return l,c
    return "UNKNOWN",RD

RANKS = [(20,"PROFESSOR EMERITUS"),(16,"DEPARTMENT HEAD"),
         (12,"PRINCIPAL INVESTIGATOR"),(8,"SENIOR ANALYST"),
         (5,"FIELD OPERATIVE"),(3,"JUNIOR SCHOLAR"),(1,"FRESHMAN RESEARCHER")]
def acad_rank(xp):
    lv = max(1,int(math.floor(math.sqrt(xp/100.0))))
    rank = "FRESHMAN RESEARCHER"
    for ml,t in reversed(RANKS):
        if lv >= ml: rank=t; break
    return lv, (lv*lv)*100, ((lv+1)*(lv+1))*100, rank

# ????????????????????????????????????????????????????????????????
# DATA WORKER THREAD
# ????????????????????????????????????????????????????????????????
class Worker(QThread):
    got_data   = pyqtSignal(dict)
    got_status = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._alive    = True
        self._do_fetch = threading.Event()
        self._session  = None
        self._token    = None
        self._uid      = None

    def set_session(self, session):
        self._session = session
        self._token   = session.get("id_token","") if session else None
        self._uid     = session.get("uid","")      if session else None

    def trigger(self):
        self._do_fetch.set()

    def run(self):
        while self._alive:
            # Wait up to 30s for a manual trigger, then auto-fetch
            self._do_fetch.wait(timeout=30)
            self._do_fetch.clear()
            if not self._alive: break
            if not self._uid:   continue
            self._fetch()
            # Small sleep to prevent hammering if something triggers rapidly
            time.sleep(0.5)

    def _fetch(self):
        self.got_status.emit("SYNCING...", AM)
        try:
            self._session, self._token = ensure_fresh_token(self._session)
            if not self._token:
                self.got_status.emit("NO TOKEN -- RUN pipboy_auth.py", RD)
                return

            data = fetch_all(self._uid, self._token)

            if data.get("_auth_error"):
                # Firestore rejected — force a token refresh and retry once
                self.got_status.emit("TOKEN EXPIRED -- REFRESHING...", AM)
                rtok = (self._session or {}).get("refresh_token", "")
                if not rtok:
                    self.got_status.emit(
                        "NO REFRESH TOKEN -- RUN pipboy_auth.py --reauth", RD)
                    return
                new_id, new_ref = refresh_token(rtok)
                if new_id:
                    # Update session in place AND save to disk
                    self._session = dict(self._session or {})
                    self._session["id_token"]      = new_id
                    self._session["refresh_token"] = new_ref or rtok
                    self._session["issued_at"]     = int(time.time())
                    save_session(self._session)
                    self._token = new_id
                    # Retry the full fetch with fresh token
                    data = fetch_all(self._uid, self._token)
                    if not data.get("_auth_error"):
                        self.got_status.emit("TOKEN REFRESHED", GD)
                if data.get("_auth_error"):
                    self.got_status.emit(
                        "SESSION EXPIRED -- RUN pipboy_auth.py --reauth", RD)
                    return

            data["_token"] = self._token
            self.got_data.emit(data)
            self.got_status.emit(f"SYNCED {datetime.now().strftime('%H:%M:%S')}", GD)
        except Exception as e:
            self.got_status.emit(f"FETCH ERROR: {str(e)[:40]}", RD)
            import traceback; traceback.print_exc()

    def stop(self):
        self._alive = False
        self._do_fetch.set()

# ????????????????????????????????????????????????????????????????
# WIDGET HELPERS
# ????????????????????????????????????????????????????????????????
def lbl(text, color=G, size=10, bold=False, wrap=False):
    l = QLabel(text)
    w = "bold" if bold else "normal"
    l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{w};"
                    "background:transparent;font-family:'Courier New';")
    if wrap: l.setWordWrap(True)
    return l

def hline():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background:{SM};max-height:1px;border:none;"); return f

class SecHdr(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._t = text; self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(TD)); p.setFont(QFont("Courier New",9))
        p.drawText(2,4,self.width()-4,16,Qt.AlignmentFlag.AlignLeft,self._t)
        p.setPen(QColor(SM)); p.drawLine(0,22,self.width(),22)

class SegBar(QWidget):
    def __init__(self, v=0, mx=100, color=G, segs=20, h=8, parent=None):
        super().__init__(parent)
        self._v=v; self._mx=mx; self._c=color; self._segs=segs
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    def set(self, v, mx=None, color=None):
        self._v=v
        if mx is not None:    self._mx=mx
        if color is not None: self._c=color
        self.update()
    def paintEvent(self,e):
        p=QPainter(self); w=self.width(); h=self.height()
        pct=min(1.0,float(self._v)/max(1.0,float(self._mx)))
        filled=int(pct*self._segs)
        sw=(w-self._segs)//self._segs
        if sw<3: sw=3
        for i in range(self._segs):
            x=i*(sw+1)
            p.fillRect(x,0,sw,h, QColor(self._c if i<filled else SM))

class PipBtn(QPushButton):
    def __init__(self, text, color=G, parent=None):
        super().__init__(text.upper(), parent)
        self.set_color(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def set_color(self, c):
        def blend(b,t,a):
            def h(s): return tuple(int(s.lstrip("#")[i:i+2],16) for i in (0,2,4))
            bb=h(b);tt=h(t); r=tuple(int(bb[i]*(1-a)+tt[i]*a) for i in range(3))
            return "#{:02x}{:02x}{:02x}".format(*r)
        bg=blend(BK,c,0.08)
        self.setStyleSheet(f"""
            QPushButton{{background:{bg};color:{c};border:1px solid {c};
                font-family:'Courier New';font-size:10px;font-weight:bold;
                padding:5px 12px;letter-spacing:1px;}}
            QPushButton:hover{{background:{blend(SF,c,0.18)};}}
            QPushButton:pressed{{background:{c};color:{BK};}}
            QPushButton:disabled{{color:{TM};border-color:{SM};background:{SF};}}
        """)

class Panel(QFrame):
    def __init__(self, border=None, parent=None):
        super().__init__(parent)
        bc=border or SM
        self.setStyleSheet(f"QFrame{{background:{SF};border:1px solid {bc};}}")
        self._lay=QVBoxLayout(self)
        self._lay.setContentsMargins(10,8,10,8)
        self._lay.setSpacing(5)
    def lay(self): return self._lay

def scrolled(widget):
    sa=QScrollArea()
    sa.setWidget(widget); sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setStyleSheet("QScrollArea{border:none;background:transparent;}")
    return sa


class MiniIcon(QWidget):
    """Small QPainter-drawn icon for use in the compact bar."""
    def __init__(self, kind, color=G, size=14, parent=None):
        super().__init__(parent)
        self._kind = kind; self._color = color; self._size = size
        self.setFixedSize(size, size)
    def set_color(self, c): self._color = c; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size; h = s // 2; c = QColor(self._color)
        p.setPen(QPen(c, max(1, s//8))); p.setBrush(c)
        k = self._kind
        if k == "water":
            path = __import__("PyQt6.QtGui", fromlist=["QPainterPath"]).QPainterPath()
            path.moveTo(h, 1)
            path.cubicTo(h+s*0.6, h*0.5, h+s*0.7, h+s*0.3, h, s-1)
            path.cubicTo(h-s*0.7, h+s*0.3, h-s*0.6, h*0.5, h, 1)
            p.fillPath(path, c)
        elif k == "sleep":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, s-2, s-2)
            p.setBrush(QColor(BK)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(3, 0, s-1, s-2)
            p.setPen(QPen(c, 1))
            p.setFont(QFont("Courier New", 5)); p.drawText(s-5, 5, "*")
        elif k == "steps":
            pts = [(h,1),(h+4,7),(h+2,7),(h+2,s-1),(h-2,s-1),(h-2,7),(h-4,7)]
            from PyQt6.QtGui import QPainterPath as PP
            path = PP(); path.moveTo(*pts[0])
            for pt in pts[1:]: path.lineTo(*pt)
            path.closeSubpath(); p.fillPath(path, c)
        elif k == "active":
            pts = [(h+3,0),(h-1,h),(h+2,h),(h-3,s),(h+1,h+3),(h-2,h+3)]
            from PyQt6.QtGui import QPainterPath as PP
            path = PP(); path.moveTo(*pts[0])
            for pt in pts[1:]: path.lineTo(*pt)
            path.closeSubpath(); p.fillPath(path, c)
        elif k == "condition":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(h-4, 0, 8, 8)
            p.drawRect(h-3, 8, 6, s-10)
            p.drawLine(h-3, s-3, h-6, s-1)
            p.drawLine(h+3, s-3, h+6, s-1)

# ????????????????????????????????????????????????????????????????
# COMPACT BAR  (always visible)
# ????????????????????????????????????????????????????????????????
class CompactBar(QWidget):
    """
    Always-visible compact bar drawn with QPainter.
    Shows condition score, 4 vital segbars, defence countdown, sync status.
    CRT scanline overlay and phosphor glow border.
    """
    expand_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_H)
        self._expanded       = False
        self._cond_score_val = "--"
        self._cond_range     = ""
        self._cond_col       = G
        self._cond_label     = "LOADING..."
        self._status_text    = "CONNECTING..."
        self._status_col     = GD
        self._def_days       = None
        self._def_col        = GD
        self._vital_data     = {
            "water":  ("--", 0.0, G),
            "sleep":  ("--", 0.0, AM),
            "steps":  ("--", 0.0, G),
            "active": ("--", 0.0, G),
        }
        # Only child widget: the expand toggle button (positioned via layout)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addStretch()
        self._toggle = QPushButton(">")
        self._toggle.setFixedSize(20, 20)
        self._toggle.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{GD};border:none;font-size:10px;}}
            QPushButton:hover{{color:{G};}}
        """)
        self._toggle.clicked.connect(self.expand_clicked)
        lay.addWidget(self._toggle)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self._toggle.setText("v" if expanded else ">")
        self.update()

    def update_data(self, data):
        d = data.get("daily",{}); g = data.get("goals",{})
        water  = sf(d.get("water")); wg  = sf(g.get("waterGoalL"), 3.0)
        sleep_ = sf(d.get("sleep")); slg = sf(g.get("sleepGoalH"), 8.0)
        steps  = sf(d.get("steps")); stg = sf(g.get("stepGoal"),   7500)
        active = sf(d.get("active")); ag = sf(g.get("activeGoalMin"), 30)
        cond   = int(sf(d.get("condition") or d.get("overall")))
        lbl_t, col = cond_info(cond)
        lo=max(0,cond-4); hi=min(100,cond+4)
        self._cond_score_val = str(cond) if cond else "--"
        self._cond_range     = f"{lo}-{hi}" if cond else ""
        self._cond_col       = col
        self._cond_label     = lbl_t.split(" ")[0]  # "OPTIMAL" not "OPTIMAL CONDITION"

        def fmt(v): return f"{v/1000:.1f}K" if v>=1000 else str(int(v))
        self._vital_data = {
            "water":  (f"{water:.1f}L", min(1.0, water/max(0.01,wg)),
                       RD if water<wg*0.25 else G),
            "sleep":  (f"{sleep_:.1f}H", min(1.0, sleep_/max(0.01,slg)),
                       RD if sleep_<5 else AM),
            "steps":  (fmt(steps), min(1.0, steps/max(1,stg)),
                       RD if steps<stg*0.25 else G),
            "active": (f"{int(active)}M", min(1.0, active/max(1,ag)),
                       RD if active<10 else G),
        }
        thesis  = data.get("thesis", {})
        defence = str(thesis.get("defenceDate") or "").strip()
        if defence:
            try:
                days = (datetime.strptime(defence, "%Y-%m-%d") - datetime.now()).days
                self._def_days = days
                self._def_col  = RD if days<14 else AM if days<60 else G
            except: self._def_days = None
        else:
            self._def_days = None
        self.update()

    def set_status(self, text, color):
        self._status_text = text[:44]
        self._status_col  = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        W = self.width(); H = self.height()

        # --- Background ---
        p.fillRect(0, 0, W, H, QColor(BK))

        # --- CRT phosphor border glow (layered) ---
        for offset, alpha in [(3, 15), (2, 40), (1, 90), (0, 200)]:
            c = QColor(GD); c.setAlpha(alpha)
            p.setPen(QPen(c, 1))
            p.drawRect(offset, offset, W-1-offset*2, H-1-offset*2)

        # === LEFT: condition score ===
        score_x, score_w = 8, 50
        p.setPen(QColor(self._cond_col))
        p.setFont(QFont("Courier New", 19, QFont.Weight.Bold))
        p.drawText(score_x, 4, score_w, H//2+2,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._cond_score_val)
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.drawText(score_x, H//2, score_w, H//2-8,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   self._cond_label)

        # Divider
        div1 = score_x + score_w + 2
        p.setPen(QColor(SM))
        p.drawLine(div1, 6, div1, H-6)

        # === MIDDLE: 4 vitals ===
        RIGHT_W = 72  # space for right section
        vitals_x = div1 + 4
        vitals_w = W - vitals_x - RIGHT_W - 4
        vkeys = [("water","H2O",G),("sleep","ZZZ",AM),("steps","STP",G),("active","ACT",G)]
        vw = vitals_w // 4

        for i, (key, short, base_col) in enumerate(vkeys):
            disp, pct, col = self._vital_data[key]
            x = vitals_x + i * vw

            # Short label
            p.setFont(QFont("Courier New", 7))
            p.setPen(QColor(col))
            p.drawText(x, 5, vw-1, 11,
                       Qt.AlignmentFlag.AlignLeft, short)

            # Value
            p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            p.drawText(x, 15, vw-1, 14,
                       Qt.AlignmentFlag.AlignLeft, disp)

            # Mini segbar (6 segs)
            BY = H - 11; BH = 5
            seg_n = 6; gap = 1
            sw = max(2, (vw - 2 - seg_n * gap) // seg_n)
            filled = int(pct * seg_n)
            for s in range(seg_n):
                sx = x + s * (sw + gap)
                fc = QColor(col) if s < filled else QColor(SM)
                p.fillRect(sx, BY, sw, BH, fc)

        # Divider before right
        div2 = W - RIGHT_W
        p.setPen(QColor(SM))
        p.drawLine(div2, 6, div2, H-6)

        # === RIGHT: defence or branding ===
        rx = div2 + 4; rw = RIGHT_W - 8
        if self._def_days is not None:
            p.setPen(QColor(self._def_col))
            p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            p.drawText(rx, 4, rw, 11,
                       Qt.AlignmentFlag.AlignHCenter, "DEFENCE")
            p.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
            p.drawText(rx, 13, rw, 18,
                       Qt.AlignmentFlag.AlignHCenter, str(self._def_days))
            p.setFont(QFont("Courier New", 7))
            p.drawText(rx, 29, rw, 11,
                       Qt.AlignmentFlag.AlignHCenter, "DAYS")
        else:
            p.setPen(QColor(GD))
            p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            p.drawText(rx, 8, rw, 14,
                       Qt.AlignmentFlag.AlignHCenter, "PIP-BOY")
            p.setFont(QFont("Courier New", 7))
            p.drawText(rx, 22, rw, 12,
                       Qt.AlignmentFlag.AlignHCenter, "3000")

        # === STATUS line at bottom ===
        p.setPen(QColor(self._status_col))
        p.setFont(QFont("Courier New", 7))
        status_with_range = (f"[{self._cond_range}]  " if self._cond_range else "") + self._status_text
        p.drawText(4, H-12, W-30, 11,
                   Qt.AlignmentFlag.AlignLeft, status_with_range[:46])

        # --- Scanline overlay ---
        scan = QColor(0, 0, 0, 22)
        for y in range(0, H, 3):
            p.fillRect(0, y, W, 1, scan)


# ????????????????????????????????????????????????????????????????
# EXPANDED PANEL  (shows/hides below the bar)
# ????????????????????????????????????????????????????????????????
class ExpandedPanel(QWidget):
    def __init__(self, uid_fn, token_fn, on_action, parent=None):
        super().__init__(parent)
        self._get_uid   = uid_fn
        self._get_token = token_fn
        self._on_action = on_action
        self._data      = {}
        self.setFixedWidth(PANEL_W)
        self.setStyleSheet(f"background:{BK};border:1px solid {GD};"
                           "border-top:none;")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:none;background:{BK};}}
            QTabBar{{background:{SF};}}
            QTabBar::tab{{background:{SF};color:{GD};font-family:'Courier New';
                font-size:9px;font-weight:bold;padding:6px 8px;border:none;
                border-bottom:2px solid transparent;letter-spacing:1px;}}
            QTabBar::tab:selected{{color:{G};background:{BK};border-bottom:2px solid {G};}}
            QTabBar::tab:hover:!selected{{color:{G};background:rgba(0,255,102,0.05);}}
        """)

        self._health_tab    = self._build_health()
        self._condition_tab = self._build_condition()
        self._log_tab       = self._build_log()
        self._tasks_tab     = self._build_tasks()
        self._writing_tab   = self._build_writing()
        self._focus_tab     = self._build_focus()

        self._goals_tab  = self._build_goals()
        self._notes_tab  = self._build_notes()
        self._jobs_tab   = self._build_jobs()

        tabs.addTab(self._health_tab,    "HEALTH")
        tabs.addTab(self._condition_tab, "SPECIAL")
        tabs.addTab(self._log_tab,       "LOG")
        tabs.addTab(self._tasks_tab,     "TASKS")
        tabs.addTab(self._writing_tab,   "WRITING")
        tabs.addTab(self._goals_tab,     "GOALS")
        tabs.addTab(self._jobs_tab,      "JOBS")
        tabs.addTab(self._notes_tab,     "NOTES")
        tabs.addTab(self._focus_tab,     "FOCUS")
        lay.addWidget(tabs)

    # ?? HEALTH ?????????????????????????????????????????????????
    def _build_health(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        # Condition
        lay.addWidget(SecHdr("// CONDITION"))
        cp=Panel(GD); cr=QHBoxLayout(); cr.setSpacing(10)
        self._h_score=QLabel("--")
        self._h_score.setStyleSheet(f"color:{G};font-size:24px;font-weight:bold;"
                                    "font-family:'Courier New';background:transparent;")
        cr.addWidget(self._h_score)
        rr=QVBoxLayout(); rr.setSpacing(3)
        self._h_clbl=QLabel("LOADING"); self._h_clbl.setStyleSheet(
            f"color:{G};font-size:11px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        rr.addWidget(self._h_clbl)
        self._h_cbar=SegBar(0,100,G,20,6); rr.addWidget(self._h_cbar)
        cr.addLayout(rr); cr.addStretch(); cp.lay().addLayout(cr); lay.addWidget(cp)

        # 2x2 vitals
        lay.addWidget(SecHdr("// VITALS"))
        grid=QGridLayout(); grid.setSpacing(4)
        self._h_vitals={}
        for i,(key,title,icon,col) in enumerate([
            ("water","HYDRATION","~",G),("sleep","SLEEP","?",AM),
            ("steps","STEPS","^",G),("active","ACTIVE","^",G)
        ]):
            cell=Panel(); cl=cell.lay()
            hr=QHBoxLayout(); hr.setSpacing(4)
            ico=QLabel(icon); ico.setStyleSheet(
                f"color:{col};font-size:12px;font-family:'Courier New';background:transparent;")
            hr.addWidget(ico); hr.addWidget(lbl(title,TD,9)); hr.addStretch(); cl.addLayout(hr)
            vl=QLabel("--"); vl.setStyleSheet(
                f"color:{col};font-size:16px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            cl.addWidget(vl)
            bar=SegBar(0,100,col,10,5); cl.addWidget(bar)
            grid.addWidget(cell,i//2,i%2); self._h_vitals[key]=(vl,bar,col)
        lay.addLayout(grid)

        # HR + weight
        extra=QHBoxLayout(); extra.setSpacing(4)
        for key,title,icon in [("hr","HEART RATE","+"),("weight","WEIGHT","=")]:
            cell=Panel(); cl=cell.lay()
            cl.addWidget(lbl(f"{icon} {title}",TD,9))
            vl=QLabel("--"); vl.setStyleSheet(
                f"color:{GD};font-size:14px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            cl.addWidget(vl); extra.addWidget(cell); self._h_vitals[key]=(vl,None,GD)
        lay.addLayout(extra)

        # Custom trackers
        lay.addWidget(SecHdr("// CUSTOM TRACKERS"))
        self._tc_panel=Panel(); lay.addWidget(self._tc_panel)
        lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # ?? CONDITION ??????????????????????????????????????????????
    def _build_condition(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        lay.addWidget(SecHdr("// OVERALL"))
        op=Panel(GD); or_=QHBoxLayout(); or_.setSpacing(10)
        self._c_score=QLabel("--"); self._c_score.setStyleSheet(
            f"color:{G};font-size:24px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        or_.addWidget(self._c_score)
        rr=QVBoxLayout(); rr.setSpacing(3)
        self._c_lbl=QLabel("LOADING"); self._c_lbl.setStyleSheet(
            f"color:{G};font-size:11px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._c_streak=lbl("",AM,9)
        self._c_bar=SegBar(0,100,G,20,6)
        rr.addWidget(self._c_lbl); rr.addWidget(self._c_streak); rr.addWidget(self._c_bar)
        or_.addLayout(rr); or_.addStretch(); op.lay().addLayout(or_); lay.addWidget(op)

        lay.addWidget(SecHdr("// S.P.E.C.I.A.L."))
        grid=QGridLayout(); grid.setSpacing(4)
        self._pillars={}
        PILLARS=[("strength","STR","STEPS + ACTIVE","Log steps or exercise"),
                 ("endurance","END","HYDRATION + WEIGHT","Drink water, log weight"),
                 ("perception","PER","SLEEP + QUALITY","Log sleep or energy"),
                 ("agility","AGI","ACTIVE MINUTES","Get 30+ active mins"),
                 ("focus","FOC","THESIS + WRITING","Log a writing session"),
                 ("tasks","TSK","CARRY WEIGHT","Complete or drop tasks"),
                 ("charisma","CHA","SOCIAL + CREATIVE","Log time with friends/art")]
        for i,(key,abbr,sub,action) in enumerate(PILLARS):
            cell=Panel(); cl=cell.lay()
            hr=QHBoxLayout(); hr.setSpacing(4)
            hr.addWidget(lbl(abbr,TD,9,bold=True))
            sv=QLabel("--"); sv.setStyleSheet(
                f"color:{G};font-size:13px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            hr.addStretch(); hr.addWidget(sv); cl.addLayout(hr)
            bar=SegBar(0,100,G,10,4); cl.addWidget(bar)
            cl.addWidget(lbl(sub,TM,8))
            al=QLabel(""); al.setStyleSheet(
                f"color:{AM};font-size:8px;font-family:'Courier New';"
                "background:transparent;"); al.setWordWrap(True)
            cl.addWidget(al)
            grid.addWidget(cell,i//2,i%2); self._pillars[key]=(sv,bar,al)
        lay.addLayout(grid)
        lay.addWidget(SecHdr("// ADVISORY"))
        ap=Panel(); self._advisory=lbl("AWAITING DATA...",GD,10,wrap=True)
        ap.lay().addWidget(self._advisory); lay.addWidget(ap); lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # ?? LOG ????????????????????????????????????????????????????
    def _build_log(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        # Water
        lay.addWidget(SecHdr("// WATER"))
        wp=Panel(); wr=QHBoxLayout(); wr.setSpacing(4)
        for amt,t in [(0.25,"250ml"),(0.33,"330ml"),(0.5,"500ml"),(0.75,"750ml"),(1.0,"1L")]:
            btn=PipBtn(t,G); btn.clicked.connect(lambda _,a=amt:self._log("water",a,"L"))
            wr.addWidget(btn)
        wr.addStretch(); wp.lay().addLayout(wr); lay.addWidget(wp)

        # Sleep
        lay.addWidget(SecHdr("// SLEEP"))
        sp=Panel(); sr=QHBoxLayout(); sr.setSpacing(6)
        sr.addWidget(lbl("HOURS:",TD,10))
        self._sleep_e=QLineEdit("7.0"); self._sleep_e.setFixedWidth(60)
        self._sleep_e.setStyleSheet(f"background:{SF};color:{G};border:1px solid {SM};"
                                    "font-family:'Courier New';font-size:10px;padding:3px 6px;")
        sr.addWidget(self._sleep_e)
        btn_sl=PipBtn("LOG",G)
        btn_sl.clicked.connect(lambda:self._log_sleep())
        sr.addWidget(btn_sl); sr.addStretch(); sp.lay().addLayout(sr); lay.addWidget(sp)

        # Weight
        lay.addWidget(SecHdr("// WEIGHT"))
        wtp=Panel(); wtr=QHBoxLayout(); wtr.setSpacing(6)
        wtr.addWidget(lbl("WEIGHT:",TD,10))
        self._weight_e=QLineEdit(); self._weight_e.setPlaceholderText("value")
        self._weight_e.setFixedWidth(70)
        self._weight_e.setStyleSheet(f"background:{SF};color:{G};border:1px solid {SM};"
                                     "font-family:'Courier New';font-size:10px;padding:3px 6px;")
        wtr.addWidget(self._weight_e)
        self._weight_unit=QComboBox(); self._weight_unit.addItems(["lbs","kg"])
        self._weight_unit.setFixedWidth(54)
        self._weight_unit.setStyleSheet(f"background:{SF};color:{GD};border:1px solid {SM};"
                                        "font-family:'Courier New';font-size:9px;")
        wtr.addWidget(self._weight_unit)
        btn_wt=PipBtn("LOG",AM); btn_wt.clicked.connect(self._log_weight)
        wtr.addWidget(btn_wt); wtr.addStretch(); wtp.lay().addLayout(wtr); lay.addWidget(wtp)

        # Morning energy
        lay.addWidget(SecHdr("// MORNING CHECK-IN"))
        self._morning_panel=Panel(AM)
        self._morning_done=lbl("",G,10,wrap=True); self._morning_done.hide()
        self._morning_panel.lay().addWidget(self._morning_done)
        self._morning_prompt=QWidget(); self._morning_prompt.setStyleSheet("background:transparent;")
        ml=QVBoxLayout(self._morning_prompt); ml.setContentsMargins(0,0,0,0); ml.setSpacing(4)
        ml.addWidget(lbl("HOW DO YOU FEEL ON WAKING?",GD,9))
        mr=QHBoxLayout(); mr.setSpacing(3)
        for n,t in [(1,"ROUGH"),(2,"TIRED"),(3,"OK"),(4,"GOOD"),(5,"GREAT")]:
            c2=RD if n<=2 else AM if n==3 else G
            b=PipBtn(f"{n} {t}",c2); b.setFixedWidth(58)
            b.clicked.connect(lambda _,v=n:self._log_morning(v)); mr.addWidget(b)
        mr.addStretch(); ml.addLayout(mr)
        self._morning_panel.lay().addWidget(self._morning_prompt)
        lay.addWidget(self._morning_panel)

        # Evening check-in (hidden until 7pm)
        self._evening_panel = Panel(AM)
        self._evening_panel.hide()
        self._evening_done = lbl("",G,10,wrap=True)
        self._evening_done.hide()
        self._evening_panel.lay().addWidget(self._evening_done)
        self._evening_prompt = QWidget(); self._evening_prompt.setStyleSheet("background:transparent;")
        el2 = QVBoxLayout(self._evening_prompt); el2.setContentsMargins(0,0,0,0); el2.setSpacing(4)
        el2.addWidget(lbl("HOW WAS YOUR DAY? (FEEDS TOMORROW'S PERCEPTION)",AM,9))
        er = QHBoxLayout(); er.setSpacing(3)
        for n,t in [(1,"ROUGH"),(2,"TIRED"),(3,"OK"),(4,"GOOD"),(5,"GREAT")]:
            c2=RD if n<=2 else AM if n==3 else G
            b=PipBtn(f"{n} {t}",c2); b.setFixedWidth(58)
            b.clicked.connect(lambda _,v=n:self._log_evening(v)); er.addWidget(b)
        er.addStretch(); el2.addLayout(er)
        self._evening_panel.lay().addWidget(self._evening_prompt)
        lay.addWidget(self._evening_panel)

        # Custom trackers
        lay.addWidget(SecHdr("// CUSTOM TRACKERS"))
        self._log_tc=Panel(); lay.addWidget(self._log_tc)

        # Manual
        lay.addWidget(SecHdr("// MANUAL ENTRY"))
        mp=Panel(); mr2=QHBoxLayout(); mr2.setSpacing(6)
        self._man_name=QLineEdit(); self._man_name.setPlaceholderText("tracker")
        self._man_name.setFixedWidth(100)
        self._man_val=QLineEdit("1"); self._man_val.setFixedWidth(55)
        for e in [self._man_name,self._man_val]:
            e.setStyleSheet(f"background:{SF};color:{G};border:1px solid {SM};"
                            "font-family:'Courier New';font-size:10px;padding:3px 6px;")
        btn_m=PipBtn("LOG",G); btn_m.clicked.connect(self._log_manual)
        mr2.addWidget(self._man_name); mr2.addWidget(self._man_val)
        mr2.addWidget(btn_m); mr2.addStretch(); mp.lay().addLayout(mr2); lay.addWidget(mp)

        self._log_fb=lbl("",G,10); lay.addWidget(self._log_fb)
        lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # ?? TASKS ??????????????????????????????????????????????????
    def _build_tasks(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        outer=QVBoxLayout(w); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Filter row
        fb_bar=QWidget(); fb_bar.setStyleSheet(f"background:{BK};")
        fl=QHBoxLayout(fb_bar); fl.setContentsMargins(8,6,8,4); fl.setSpacing(3)
        self._task_filter="ALL"; self._task_filter_btns={}
        for cat in ["ALL","THESIS","JOBS","ADMIN","MISC"]:
            btn=PipBtn(cat,GD); btn.clicked.connect(lambda _,c=cat:self._set_task_filter(c))
            self._task_filter_btns[cat]=btn; fl.addWidget(btn)
        fl.addStretch(); outer.addWidget(fb_bar)

        # Carry weight
        cw=QWidget(); cw.setStyleSheet(f"background:{BK};")
        cwl=QHBoxLayout(cw); cwl.setContentsMargins(8,2,8,2); cwl.setSpacing(6)
        cwl.addWidget(lbl("CARRY:",GD,9))
        self._carry_lbl=lbl("0/20",GD,10,bold=True); cwl.addWidget(self._carry_lbl)
        self._carry_bar=SegBar(0,20,GD,10,4); self._carry_bar.setFixedWidth(100)
        cwl.addWidget(self._carry_bar); cwl.addStretch(); outer.addWidget(cw)

        # Task list scroll
        self._task_scroll=QScrollArea()
        self._task_scroll.setWidgetResizable(True)
        self._task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._task_scroll.setStyleSheet("QScrollArea{border:none;}")
        self._task_list=QWidget(); self._task_list.setStyleSheet(f"background:{BK};")
        self._task_lay=QVBoxLayout(self._task_list)
        self._task_lay.setContentsMargins(8,4,8,4); self._task_lay.setSpacing(2)
        self._task_lay.addStretch(); self._task_scroll.setWidget(self._task_list)
        outer.addWidget(self._task_scroll)

        # Add task
        add=QWidget(); add.setStyleSheet(f"background:{SF};border-top:1px solid {SM};")
        al=QHBoxLayout(add); al.setContentsMargins(8,5,8,5); al.setSpacing(5)
        self._task_entry=QLineEdit(); self._task_entry.setPlaceholderText("new task...")
        self._task_entry.setStyleSheet(f"background:{BK};color:{G};border:1px solid {SM};"
                                       "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        self._task_entry.returnPressed.connect(self._add_task); al.addWidget(self._task_entry)
        self._task_wgt=QComboBox()
        self._task_wgt.addItems(["W1","W2","W3","W4","W5"]); self._task_wgt.setFixedWidth(46)
        self._task_wgt.setStyleSheet(f"background:{BK};color:{GD};border:1px solid {SM};"
                                     "font-family:'Courier New';font-size:9px;")
        al.addWidget(self._task_wgt)
        self._task_cat=QComboBox(); self._task_cat.addItems(["THESIS","JOBS","ADMIN","PERSONAL"])
        self._task_cat.setFixedWidth(80)
        self._task_cat.setStyleSheet(f"background:{BK};color:{GD};border:1px solid {SM};"
                                     "font-family:'Courier New';font-size:9px;")
        al.addWidget(self._task_cat)
        add_btn=PipBtn("ADD",G); add_btn.clicked.connect(self._add_task); al.addWidget(add_btn)
        outer.addWidget(add); return w

    # ?? WRITING ????????????????????????????????????????????????
    def _build_writing(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        lay.addWidget(SecHdr("// ACADEMIC RANK"))
        rp=Panel(); rr=QHBoxLayout(); rr.setSpacing(10)
        lf=QFrame(); lf.setStyleSheet(f"background:{SM};border:none;")
        ll=QVBoxLayout(lf); ll.setContentsMargins(8,5,8,5)
        self._rank_lv=QLabel("LV1"); self._rank_lv.setStyleSheet(
            f"color:{G};font-size:16px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        ll.addWidget(self._rank_lv); rr.addWidget(lf)
        rc=QVBoxLayout(); rc.setSpacing(2)
        self._rank_title=QLabel("FRESHMAN RESEARCHER")
        self._rank_title.setStyleSheet(
            f"color:{G};font-size:10px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._rank_xp=lbl("XP: 0 / 100",GD,9)
        self._rank_bar=SegBar(0,100,G,20,5)
        rc.addWidget(self._rank_title); rc.addWidget(self._rank_xp); rc.addWidget(self._rank_bar)
        rr.addLayout(rc); rr.addStretch(); rp.lay().addLayout(rr); lay.addWidget(rp)

        lay.addWidget(SecHdr("// DEFENCE COUNTDOWN"))
        dp=Panel(); dr=QHBoxLayout(); dr.setSpacing(10)
        self._def_days=QLabel("--"); self._def_days.setStyleSheet(
            f"color:{G};font-size:24px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        dr.addWidget(self._def_days)
        dc=QVBoxLayout(); dc.setSpacing(2)
        dc.addWidget(lbl("DAYS REMAINING",GD,9))
        self._def_date=lbl("",TM,8); dc.addWidget(self._def_date)
        dr.addLayout(dc); dr.addStretch(); dp.lay().addLayout(dr)
        self._def_bar=SegBar(0,100,RD,20,5); dp.lay().addWidget(self._def_bar)
        lay.addWidget(dp)

        lay.addWidget(SecHdr("// CHAPTERS"))
        self._ch_panel=Panel(); lay.addWidget(self._ch_panel)

        lay.addWidget(SecHdr("// LOG SESSION"))
        sp=Panel(); sl=QHBoxLayout(); sl.setSpacing(6)
        sl.addWidget(lbl("WORDS:",TD,10))
        self._sess_words=QSpinBox(); self._sess_words.setRange(0,99999)
        self._sess_words.setValue(500); self._sess_words.setSingleStep(100)
        self._sess_words.setStyleSheet(
            f"background:{SF};color:{G};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:3px;")
        self._sess_words.setFixedWidth(90); sl.addWidget(self._sess_words)
        sp.lay().addLayout(sl)
        ql=QHBoxLayout(); ql.setSpacing(3); ql.addWidget(lbl("QUALITY:",TD,9))
        self._qual_grp=QButtonGroup(sp)
        for n,t in [(1,"1"),(2,"2"),(3,"3"),(4,"4"),(5,"5")]:
            col=RD if n<=2 else AM if n==3 else G
            rb=QRadioButton(f"{n}"); rb.setStyleSheet(
                f"color:{col};font-size:9px;font-family:'Courier New';background:transparent;")
            self._qual_grp.addButton(rb,n); ql.addWidget(rb)
            if n==3: rb.setChecked(True)
        ql.addStretch(); sp.lay().addLayout(ql)
        save_btn=PipBtn("SAVE WRITING SESSION",G)
        save_btn.clicked.connect(self._save_writing); sp.lay().addWidget(save_btn)
        self._writing_fb=lbl("",G,9); sp.lay().addWidget(self._writing_fb)
        lay.addWidget(sp); lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # ?? FOCUS ??????????????????????????????????????????????????

    # -- GOALS ------------------------------------------
    def _build_goals(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        lay.addWidget(SecHdr("// LIFE GOALS"))
        self._lg_panel=Panel(); lay.addWidget(self._lg_panel)

        lay.addWidget(SecHdr("// ADD LIFE GOAL"))
        ap=Panel()
        self._lg_title=QLineEdit(); self._lg_title.setPlaceholderText("goal title...")
        self._lg_title.setStyleSheet(f"background:{BK};color:{G};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        self._lg_desc=QLineEdit(); self._lg_desc.setPlaceholderText("description (optional)...")
        self._lg_desc.setStyleSheet(f"background:{BK};color:{GD};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        add_btn=PipBtn("ADD LIFE GOAL",G); add_btn.clicked.connect(self._add_goal)
        ap.lay().addWidget(self._lg_title); ap.lay().addWidget(self._lg_desc)
        ap.lay().addWidget(add_btn); lay.addWidget(ap)

        lay.addWidget(SecHdr("// UPCOMING DEADLINES"))
        self._dl_panel=Panel(); lay.addWidget(self._dl_panel)

        lay.addWidget(SecHdr("// ADD DEADLINE"))
        dp=Panel(); dr=QHBoxLayout(); dr.setSpacing(6)
        self._dl_title=QLineEdit(); self._dl_title.setPlaceholderText("deadline title...")
        self._dl_title.setStyleSheet(f"background:{BK};color:{G};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        dr.addWidget(self._dl_title)
        self._dl_date=QLineEdit(today_key()); self._dl_date.setFixedWidth(100)
        self._dl_date.setStyleSheet(f"background:{BK};color:{G};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        dr.addWidget(self._dl_date)
        add_dl=PipBtn("ADD",AM); add_dl.clicked.connect(self._add_deadline)
        dr.addWidget(add_dl); dp.lay().addLayout(dr); lay.addWidget(dp)

        self._goals_fb=lbl("",G,9); lay.addWidget(self._goals_fb)
        lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # -- NOTES ------------------------------------------
    def _build_notes(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        lay.addWidget(SecHdr("// VAULT-TEC DAILY NOTES"))
        np=Panel()
        dr=QHBoxLayout(); dr.setSpacing(8)
        dr.addWidget(lbl("DATE:",TD,10))
        self._note_date_lbl=lbl(today_key(),G,10,bold=True)
        dr.addWidget(self._note_date_lbl); dr.addStretch(); np.lay().addLayout(dr)

        self._note_text=QTextEdit()
        self._note_text.setMinimumHeight(180)
        self._note_text.setPlaceholderText("VAULT-TEC PERSONAL LOG ENTRY...")
        self._note_text.setStyleSheet(f"""
            QTextEdit{{background:{BK};color:{G};border:1px solid {SM};
                font-family:'Courier New';font-size:10px;padding:6px;}}
            QTextEdit:focus{{border:1px solid {G};}}
        """)
        np.lay().addWidget(self._note_text)

        br=QHBoxLayout(); br.setSpacing(6)
        save_btn=PipBtn("SAVE NOTE",G); save_btn.clicked.connect(self._save_note)
        load_btn=PipBtn("LOAD TODAY",GD); load_btn.clicked.connect(self._load_note)
        br.addWidget(save_btn); br.addWidget(load_btn); br.addStretch()
        np.lay().addLayout(br)
        self._note_fb=lbl("",G,9); np.lay().addWidget(self._note_fb)
        lay.addWidget(np); lay.addStretch()

        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    def _build_focus(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        self._pomo_mins=25; self._pomo_running=False
        self._pomo_elapsed=0; self._pomo_start=0; self._pomo_sessions=[]
        self._pomo_timer=QTimer(); self._pomo_timer.timeout.connect(self._pomo_tick)

        lay.addWidget(SecHdr("// FOCUS TIMER"))
        tp=Panel(AM)
        self._pomo_clock=QLabel("25:00"); self._pomo_clock.setStyleSheet(
            f"color:{AM};font-size:36px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._pomo_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.lay().addWidget(self._pomo_clock)
        self._pomo_task_lbl=lbl("FOCUS TIMER",GD,9); self._pomo_task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.lay().addWidget(self._pomo_task_lbl)
        self._pomo_bar=SegBar(0,100,G,20,6); tp.lay().addWidget(self._pomo_bar)
        self._pomo_sess_lbl=lbl("0 SESSIONS TODAY",TM,8); self._pomo_sess_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.lay().addWidget(self._pomo_sess_lbl)
        lay.addWidget(tp)

        lay.addWidget(SecHdr("// WORKING ON"))
        lp=Panel()
        self._pomo_label=QLineEdit("THESIS WRITING")
        self._pomo_label.setStyleSheet(
            f"background:{BK};color:{G};border:1px solid {SM};"
            "font-family:'Courier New';font-size:10px;padding:4px 6px;")
        lp.lay().addWidget(self._pomo_label); lay.addWidget(lp)

        lay.addWidget(SecHdr("// DURATION"))
        dp=Panel(); dr=QHBoxLayout(); dr.setSpacing(3)
        for m in [15,25,45,60]:
            btn=PipBtn(f"{m}M",AM); btn.clicked.connect(lambda _,x=m:self._pomo_set(x))
            dr.addWidget(btn)
        dr.addSpacing(6)
        m_btn=PipBtn("-",GD); m_btn.clicked.connect(lambda:self._pomo_set(max(1,self._pomo_mins-5)))
        dr.addWidget(m_btn)
        self._pomo_mins_lbl=QLabel("25"); self._pomo_mins_lbl.setStyleSheet(
            f"color:{G};font-size:13px;font-weight:bold;font-family:'Courier New';background:transparent;")
        dr.addWidget(self._pomo_mins_lbl)
        p_btn=PipBtn("+",GD); p_btn.clicked.connect(lambda:self._pomo_set(self._pomo_mins+5))
        dr.addWidget(p_btn); dr.addStretch(); dp.lay().addLayout(dr); lay.addWidget(dp)

        lay.addWidget(SecHdr("// CONTROLS"))
        cp=Panel(); cr=QHBoxLayout(); cr.setSpacing(6)
        self._pomo_toggle=PipBtn("START TIMER",G); self._pomo_toggle.clicked.connect(self._pomo_toggle_fn)
        cr.addWidget(self._pomo_toggle)
        reset_btn=PipBtn("RESET",RD); reset_btn.clicked.connect(self._pomo_reset)
        cr.addWidget(reset_btn); cr.addStretch(); cp.lay().addLayout(cr); lay.addWidget(cp)

        lay.addWidget(SecHdr("// SESSION LOG"))
        self._pomo_log=Panel(); lay.addWidget(self._pomo_log); lay.addStretch()
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    # ?? UPDATE DATA ????????????????????????????????????????????
    def update_data(self, data):
        self._data = data
        self._render_health(data)
        self._render_condition(data)
        self._render_log(data)
        self._render_tasks(data)
        self._render_writing(data)
        self._render_goals(data)
        self._render_jobs(data)

    def _render_health(self, data):
        d=data.get("daily",{}); g=data.get("goals",{})
        water=sf(d.get("water")); wg=sf(g.get("waterGoalL"),3.0)
        sleep=sf(d.get("sleep")); slg=sf(g.get("sleepGoalH"),8.0)
        steps=sf(d.get("steps")); stg=sf(g.get("stepGoal"),7500)
        active=sf(d.get("active")); ag=sf(g.get("activeGoalMin"),30)
        cond=int(sf(d.get("condition") or d.get("overall")))
        lbl_t,col=cond_info(cond)
        lo=max(0,cond-4); hi=min(100,cond+4)
        score_txt = f"{cond}%" if cond else "--"
        range_txt = f"[{lo}-{hi}]" if cond else ""
        self._h_score.setText(score_txt)
        self._h_score.setStyleSheet(
            f"color:{col};font-size:24px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._h_clbl.setText(f"{lbl_t}  {range_txt}")
        self._h_clbl.setStyleSheet(
            f"color:{col};font-size:10px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._h_cbar.set(cond,100,col)

        def fmt_steps(v): return f"{v/1000:.1f}K" if v>=1000 else str(int(v))
        for key,val,mx,base in [("water",water,wg,G),("sleep",sleep,slg,AM),
                                  ("steps",steps,stg,G),("active",active,ag,G)]:
            vl,bar,_=self._h_vitals[key]
            c=RD if val<mx*0.25 else base
            disp=f"{val:.1f}L" if key=="water" else f"{val:.1f}H" if key=="sleep" else \
                 fmt_steps(val) if key=="steps" else f"{int(val)}M"
            vl.setText(disp); vl.setStyleSheet(
                f"color:{c};font-size:16px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            if bar: bar.set(val,mx,c)

        hr=sf(d.get("heartRateAvg") or d.get("heartRate"))
        wt=sf(d.get("weightKg") or d.get("weight"))
        self._h_vitals["hr"][0].setText(f"{int(hr)}BPM" if hr else "--")
        self._h_vitals["weight"][0].setText(f"{wt:.1f}kg" if wt else "--")

        # Custom trackers
        lay=self._tc_panel.lay()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        trackers=data.get("trackers",[]); totals=data.get("totals",{})
        if not trackers:
            lay.addWidget(lbl("NO CUSTOM TRACKERS -- CONFIGURE IN APP",TM,9)); return
        grid=QGridLayout(); grid.setSpacing(3)
        period_totals = data.get("period_totals", totals)  # period-aware totals if available
        for i,t in enumerate(trackers):
            name=str(t.get("name","")); key=name.lower().strip()
            freq=str(t.get("frequency","daily"))
            val=period_totals.get(key, totals.get(key,0))
            is_tog=bool(t.get("isToggle",False))
            is_int=bool(t.get("isInteger",False)); unit=str(t.get("unit",""))
            goal=sf(t.get("goal"))
            if is_tog: disp=("ON" if val>0 else "OFF"); c=G if val>0 else GD
            elif is_int: disp=str(int(val)); c=G
            else: disp=f"{val:.1f}"; c=G
            # Colour overdue periodic trackers amber
            if freq!="daily" and val<=0: c=AM
            cell=Panel(); cl=cell.lay()
            hr2=QHBoxLayout(); hr2.setSpacing(4)
            hr2.addWidget(lbl(name.upper(),TD,9))
            hr2.addStretch()
            if freq=="weekly":  hr2.addWidget(lbl("WK",AM,7))
            elif freq=="monthly": hr2.addWidget(lbl("MO",AM,7))
            cl.addLayout(hr2)
            cl.addWidget(lbl(f"{disp} {unit}".strip(),c,13,bold=True))
            if goal>0:
                bar=SegBar(val,goal,c,8,3); cl.addWidget(bar)
            grid.addWidget(cell,i//3,i%3)
        lay.addLayout(grid)

    def _render_condition(self, data):
        d=data.get("daily",{})
        overall=int(sf(d.get("condition") or d.get("overall")))
        lbl_t,col=cond_info(overall)
        self._c_score.setText(str(overall) if overall else "--")
        self._c_score.setStyleSheet(
            f"color:{col};font-size:24px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._c_lbl.setText(lbl_t)
        self._c_lbl.setStyleSheet(
            f"color:{col};font-size:11px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._c_bar.set(overall,100,col)
        streak=d.get("streakBonus")
        self._c_streak.setText(f"LUCK BONUS: +{streak}%" if streak else "")

        PILLARS=[("strength","STEPS + ACTIVE","Log steps or exercise"),
                 ("endurance","HYDRATION + WEIGHT","Drink water, log weight"),
                 ("perception","SLEEP + QUALITY","Log sleep or energy"),
                 ("agility","ACTIVE MINUTES","Get 30+ active mins"),
                 ("focus","THESIS + WRITING","Log a writing session"),
                 ("tasks","CARRY WEIGHT","Complete or drop tasks"),
                 ("charisma","SOCIAL + CREATIVE","Log time with friends/art")]
        weak=[]
        for (key,sub,action),(pk,pbr,al) in zip(PILLARS,self._pillars.values()):
            score=int(sf(d.get(key))); pc=G if score>=80 else AM if score>=50 else RD
            pk.setText(str(score) if score else "--")
            pk.setStyleSheet(f"color:{pc};font-size:13px;font-weight:bold;"
                             "font-family:'Courier New';background:transparent;")
            pbr.set(score,100,pc)
            al.setText(f"-> {action}" if score<70 else "")
            al.setStyleSheet(f"color:{AM};font-size:8px;font-family:'Courier New';"
                             "background:transparent;")
            if score<50: weak.append(key.upper()[:3])
        self._advisory.setText(
            f"! DEFICIENCIES: {', '.join(weak)}. ACTION REQUIRED." if weak
            else "ALL SYSTEMS NOMINAL. VAULT-TEC COMMENDS YOUR EFFICIENCY.")
        self._advisory.setStyleSheet(
            f"color:{RD if weak else GD};font-size:10px;font-family:'Courier New';"
            "background:transparent;")

    def _render_log(self, data):
        # Morning check-in
        today=today_key(); thesis=data.get("thesis",{})
        el=thesis.get("energyLogs") or []
        entry=next((l for l in el if l.get("date")==today),None)
        logged=entry and entry.get("morning") is not None
        lvl=entry.get("morning",0) if entry else 0
        lbls={1:"ROUGH",2:"TIRED",3:"OK",4:"GOOD",5:"GREAT"}
        self._morning_done.hide(); self._morning_prompt.hide()
        if logged:
            self._morning_done.setText(
                f"LOGGED: {lvl}/5 -- {lbls.get(lvl,'')}  (AFFECTS PERCEPTION)")
            self._morning_done.show()
        else:
            self._morning_prompt.show()

        # Evening check-in (show after 7pm if not yet logged)
        from datetime import datetime as _dt
        now_hour = _dt.now().hour
        eve_logged = entry and entry.get("evening") is not None
        if hasattr(self, "_evening_panel"):
            if now_hour >= 19 and not eve_logged:
                self._evening_panel.show()
                self._evening_done.hide()
                self._evening_prompt.show()
            elif eve_logged:
                ev_lvl = entry.get("evening",0)
                self._evening_done.setText(
                    f"EVENING LOGGED: {ev_lvl}/5 -- {lbls.get(ev_lvl,'')}  (FEEDS TOMORROW)")
                self._evening_done.show()
                self._evening_prompt.hide()
                self._evening_panel.show()
            else:
                self._evening_panel.hide()

        # Custom tracker buttons
        trackers=data.get("trackers",[]); totals=data.get("totals",{})
        lay=self._log_tc.lay()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not trackers:
            lay.addWidget(lbl("NO CUSTOM TRACKERS",TM,9)); return
        row=None
        for i,t in enumerate(trackers):
            if i%3==0:
                row=QWidget(); row.setStyleSheet("background:transparent;")
                rl=QHBoxLayout(row); rl.setContentsMargins(0,0,0,0); rl.setSpacing(3)
                lay.addWidget(row)
            name=str(t.get("name","")); key=name.lower().strip()
            val=totals.get(key,0); is_tog=bool(t.get("isToggle",False))
            is_int=bool(t.get("isInteger",False)); unit=str(t.get("unit",""))
            if is_tog: disp=("ON" if val>0 else "OFF"); c=G if val>0 else GD
            elif is_int: disp=str(int(val)); c=G
            else: disp=f"{val:.1f}"; c=G
            btn=PipBtn(f"{name[:7].upper()}\n{disp}{unit[:3]}",c)
            btn.setFixedWidth(86)
            btn.clicked.connect(lambda _,n=name,tog=is_tog,v=val:self._log_tracker(n,tog,v))
            row.layout().addWidget(btn)
        if row: row.layout().addStretch()

    def _render_tasks(self, data):
        todos=data.get("todos",[])
        cat=self._task_filter; cat_key="PERSONAL" if cat=="MISC" else cat
        filtered=[t for t in todos if cat=="ALL" or str(t.get("category","")).upper()==cat_key]
        filtered.sort(key=lambda t:(t.get("done",False),-(int(t.get("weight",1) or 1))))
        while self._task_lay.count()>1:
            item=self._task_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not filtered:
            self._task_lay.insertWidget(0,lbl("NO TASKS",TM,10))
        else:
            for i,t in enumerate(filtered):
                row=self._task_row(t,data.get("todos",[]))
                self._task_lay.insertWidget(i,row)
        carry=sum(int(t.get("weight",1) or 1) for t in todos if not t.get("done"))
        c=RD if carry>20 else AM if carry>15 else GD
        self._carry_lbl.setText(f"{carry}/20")
        self._carry_lbl.setStyleSheet(f"color:{c};font-size:10px;font-weight:bold;"
                                      "font-family:'Courier New';background:transparent;")
        self._carry_bar.set(min(carry,20),20,c)
        for cat2,btn in self._task_filter_btns.items():
            btn.set_color(G if cat2==cat else GD)

    def _task_row(self, t, all_todos):
        tid=t.get("id",""); text=str(t.get("text",""))
        done=bool(t.get("done",False)); wgt=int(t.get("weight",1) or 1)
        cat=str(t.get("category","")).upper(); age=0
        try:
            cr=t.get("createdDate","") or ""
            if cr: age=(datetime.now()-datetime.strptime(cr,"%Y-%m-%d")).days
        except: pass
        col=TD if done else RD if age>=7 else AM if age>=3 else G
        row=QWidget(); row.setStyleSheet(f"background:{SF};border:1px solid {SM};")
        rl=QHBoxLayout(row); rl.setContentsMargins(8,5,8,5); rl.setSpacing(8)
        cb=QLabel("[x]" if done else "[ ]")
        cb.setStyleSheet(f"color:{col};font-size:11px;font-family:'Courier New';"
                         "background:transparent;cursor:pointer;")
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.mousePressEvent=lambda e,i=tid,d=done:self._toggle_task(i,not d)
        rl.addWidget(cb)
        mid=QVBoxLayout(); mid.setSpacing(1)
        disp=text[:28]+".." if len(text)>28 else text
        tl=QLabel(disp.upper()); tl.setStyleSheet(
            f"color:{TD if done else col};font-size:10px;font-family:'Courier New';"
            "background:transparent;"+ ("text-decoration:line-through;" if done else ""))
        mid.addWidget(tl)
        ml=QLabel(cat+(f"  OVERDUE {age}D" if age>=7 else ""))
        ml.setStyleSheet(f"color:{TM};font-size:8px;font-family:'Courier New';background:transparent;")
        mid.addWidget(ml); rl.addLayout(mid); rl.addStretch()
        wf=QFrame(); wf.setStyleSheet(f"background:{SM};border:none;")
        wfl=QHBoxLayout(wf); wfl.setContentsMargins(5,2,5,2)
        wl=QLabel(f"W{wgt}"); wl.setStyleSheet(
            f"color:{GD};font-size:9px;font-family:'Courier New';background:transparent;")
        wfl.addWidget(wl); rl.addWidget(wf); return row

    def _render_writing(self, data):
        thesis=data.get("thesis",{}); todos=data.get("todos",[])
        chapters=thesis.get("chapters") or []; today=today_key()
        writing_xp=sum(int(l.get("words",0) or 0) for l in (thesis.get("writingLogs") or []))
        task_xp=sum(int(t.get("weight",1) or 1)*100 for t in todos
                    if t.get("done") and str(t.get("category","")).upper() in ("THESIS","THESIS_ADMIN"))
        total_xp=writing_xp+task_xp
        lv,xpc,xpn,rank=acad_rank(total_xp)
        self._rank_lv.setText(f"LV{lv}")
        self._rank_title.setText(rank)
        self._rank_xp.setText(f"XP: {total_xp-xpc:,} / {xpn-xpc:,}")
        self._rank_bar.set(total_xp-xpc,max(1,xpn-xpc),G)
        defence=str(thesis.get("defenceDate") or "").strip()
        if defence:
            try:
                days=(datetime.strptime(defence,"%Y-%m-%d")-datetime.now()).days
                dc=RD if days<14 else AM if days<60 else G
                self._def_days.setText(str(days))
                self._def_days.setStyleSheet(
                    f"color:{dc};font-size:24px;font-weight:bold;"
                    "font-family:'Courier New';background:transparent;")
                self._def_date.setText(defence)
                self._def_bar.set(min(100,max(0,int((1-(days/90.0))*100))),100,dc)
            except: self._def_days.setText("--")
        else: self._def_days.setText("--"); self._def_date.setText("NOT SET")
        lay=self._ch_panel.lay()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not chapters:
            lay.addWidget(lbl("NO CHAPTERS -- CONFIGURE IN APP",TM,9)); return
        for i,ch in enumerate(chapters):
            cw=int(ch.get("currentWords",0) or 0); tw=int(ch.get("targetWords",0) or 1)
            pct=int(ch.get("pct",0) or 0) or round(cw/max(1,tw)*100)
            col=G if pct>=100 else AM
            cell=Panel(); cl=cell.lay()
            hr=QHBoxLayout()
            hr.addWidget(lbl(f"CH{i+1}: {ch.get('name','').upper()}",G,10,bold=True))
            hr.addStretch()
            pct_lbl=QLabel(f"{pct}%"); pct_lbl.setStyleSheet(
                f"color:{col};font-size:11px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            hr.addWidget(pct_lbl)
            cl.addLayout(hr)
            cl.addWidget(lbl(f"{cw:,} / {tw:,} WORDS",TD,9))
            cl.addWidget(SegBar(pct,100,col,12,4)); lay.addWidget(cell)

    # ?? ACTION METHODS ?????????????????????????????????????????
    def _feedback_log(self, msg, color=G):
        self._log_fb.setText(msg)
        self._log_fb.setStyleSheet(f"color:{color};font-size:9px;"
                                   "font-family:'Courier New';background:transparent;")
        QTimer.singleShot(3000,lambda:self._log_fb.setText(""))

    def _log(self, tracker, value, unit=""):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            ts=int(time.time()*1000)
            fs_add(f"users/{uid}/logs",{"tracker":tracker,"value":str(value),
                "unit":unit,"type":tracker,"ts":ts,"timestamp":ts},token)
            fresh=fs_get(f"users/{uid}/daily/{today_key()}",token)
            cur=sf(fresh.get(tracker))
            fs_set(f"users/{uid}/daily/{today_key()}",{tracker:round(cur+float(value),3)},token)
            QTimer.singleShot(0,lambda:self._feedback_log(
                f"{tracker.upper()}: +{value}{unit} LOGGED",G))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _log_sleep(self):
        try: h=float(self._sleep_e.text())
        except: self._feedback_log("! ENTER VALID HOURS",RD); return
        self._log("sleep",h,"h")

    def _log_weight(self):
        try: wt=float(self._weight_e.text())
        except: self._feedback_log("! ENTER VALID WEIGHT",RD); return
        unit=self._weight_unit.currentText()
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            ts=int(time.time()*1000)
            fs_add(f"users/{uid}/logs",{"tracker":"weight","value":str(wt),
                "unit":unit,"type":"weight","ts":ts,"timestamp":ts},token)
            kg=wt if unit=="kg" else round(wt/2.20462,3)
            fs_set(f"users/{uid}/daily/{today_key()}",{"weightKg":kg},token)
            QTimer.singleShot(0,lambda:self._feedback_log(f"WEIGHT: {wt}{unit} LOGGED",AM))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _log_morning(self, level):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            thesis=dict(self._data.get("thesis",{}))
            logs=list(thesis.get("energyLogs") or [])
            today=today_key()
            ex=next((l for l in logs if l.get("date")==today),None)
            if ex: ex["morning"]=level
            else: logs.append({"date":today,"morning":level,"evening":0,"mood":0,"sleepH":None})
            thesis["energyLogs"]=logs
            fs_set(f"users/{uid}/settings/thesis",thesis,token,full=True)
            lbls={1:"ROUGH",2:"TIRED",3:"OK",4:"GOOD",5:"GREAT"}
            QTimer.singleShot(0,lambda:self._feedback_log(
                f"MORNING: {level}/5 -- {lbls.get(level,'')}",G))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()


    def _log_evening(self, level):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            thesis=dict(self._data.get("thesis",{}))
            logs=list(thesis.get("energyLogs") or [])
            today=today_key()
            ex=next((l for l in logs if l.get("date")==today),None)
            if ex: ex["evening"]=level
            else: logs.append({"date":today,"morning":0,"evening":level,"mood":0,"sleepH":None})
            thesis["energyLogs"]=logs
            fs_set(f"users/{uid}/settings/thesis",thesis,token,full=True)
            lbls={1:"ROUGH",2:"TIRED",3:"OK",4:"GOOD",5:"GREAT"}
            QTimer.singleShot(0,lambda:self._feedback_log(
                f"EVENING: {level}/5 -- {lbls.get(level,'')} (FEEDS TOMORROW)",AM))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _log_tracker(self, name, is_tog, cur_val):
        val=-cur_val if (is_tog and cur_val>0) else 1.0
        self._log(name.lower().strip(), val)

    def _log_manual(self):
        name=self._man_name.text().strip()
        try: val=float(self._man_val.text())
        except: self._feedback_log("! ENTER VALID NUMBER",RD); return
        if not name: self._feedback_log("! ENTER TRACKER NAME",RD); return
        self._log(name.lower(),val)

    def _set_task_filter(self, cat):
        self._task_filter=cat
        if self._data: self._render_tasks(self._data)

    def _toggle_task(self, tid, done):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        todos=list(self._data.get("todos",[]))
        for t in todos:
            if t.get("id")==tid:
                t["done"]=done; t["checkedOffDate"]=today_key() if done else ""
        def run():
            # Android saveTodos uses .set() -- full document replace
            fields = {"items": _wrap(todos)}
            _req(f"{FIRESTORE}/users/{uid}/settings/todos",
                 "PATCH", {"fields": fields}, token)
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()
        self._render_tasks({"todos":todos,"goals":self._data.get("goals",{})})

    def _add_task(self):
        text=self._task_entry.text().strip()
        if not text: return
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        wgt=int(self._task_wgt.currentText().replace("W",""))
        cat=self._task_cat.currentText()
        todos=list(self._data.get("todos",[]))
        todos.append({"id":str(uuid.uuid4()),"text":text,"done":False,
            "weight":wgt,"baseWeight":wgt,"category":cat,
            "createdDate":today_key(),"checkedOffDate":"",
            "rolledOver":False,"rolledFrom":"","autoIncr":False,"tags":[],"deadline":"","notes":""})
        def run():
            # Android saveTodos uses .set() -- full document replace
            fields = {"items": _wrap(todos)}
            _req(f"{FIRESTORE}/users/{uid}/settings/todos",
                 "PATCH", {"fields": fields}, token)
            QTimer.singleShot(0,lambda:self._task_entry.clear())
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _save_writing(self):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        words=self._sess_words.value(); qual=self._qual_grp.checkedId() or 3
        if words<=0: self._writing_fb.setText("! ENTER WORD COUNT"); return
        def run():
            thesis=dict(self._data.get("thesis",{}))
            logs=list(thesis.get("writingLogs") or []); today=today_key()
            ex=next((l for l in logs if l.get("date")==today),None)
            if ex: ex["words"]=int(ex.get("words",0) or 0)+words; ex["quality"]=qual
            else: logs.append({"date":today,"words":words,"quality":qual})
            thesis["writingLogs"]=logs
            fs_set(f"users/{uid}/settings/thesis",thesis,token,full=True)
            ts=int(time.time()*1000)
            fs_add(f"users/{uid}/logs",{"tracker":"writing_session","value":str(float(words)),
                "unit":"words","type":"writing_session","ts":ts,"timestamp":ts},token)
            QTimer.singleShot(0,lambda:self._writing_fb.setText(
                f"LOGGED: {words:,} WORDS  Q:{qual}/5"))
            QTimer.singleShot(3000,lambda:self._writing_fb.setText(""))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    # ?? POMODORO ???????????????????????????????????????????????

    def _render_goals(self, data):
        life_goals = data.get("life_goals",[])
        deadlines  = data.get("deadlines",[])

        # Life goals
        lay = self._lg_panel.lay()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not life_goals:
            lay.addWidget(lbl("NO LIFE GOALS SET",TM,9))
        else:
            for g in life_goals:
                pct=int(g.get("progress",0) or 0); done=bool(g.get("completed",False))
                col=G if done else AM
                cell=Panel(); cl=cell.lay()
                hr=QHBoxLayout()
                title=str(g.get("title",""))
                tl=QLabel((title[:28]+"..") if len(title)>28 else title)
                tl.setStyleSheet(f"color:{col};font-size:10px;font-weight:bold;"
                    "font-family:'Courier New';background:transparent;")
                hr.addWidget(tl); hr.addStretch()
                hr.addWidget(lbl(f"{pct}%",col,11,bold=True))
                cl.addLayout(hr)
                cl.addWidget(SegBar(pct,100,col,12,4))
                desc=str(g.get("description",""))
                if desc: cl.addWidget(lbl(desc[:48],TM,8))
                td=g.get("targetDate","")
                if td:
                    try:
                        days=(datetime.strptime(td,"%Y-%m-%d")-datetime.now()).days
                        dc=RD if days<30 else AM if days<90 else GD
                        cl.addWidget(lbl(f"TARGET: {td}  ({days}D)",dc,8))
                    except: pass
                lay.addWidget(cell)

        # Deadlines
        lay2 = self._dl_panel.lay()
        while lay2.count():
            item=lay2.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        dls = sorted(deadlines, key=lambda d: d.get("date",""))
        if not dls:
            lay2.addWidget(lbl("NO DEADLINES SET",TM,9))
        else:
            for d in dls:
                title=str(d.get("title","")); date=str(d.get("date",""))
                try:
                    days=(datetime.strptime(date,"%Y-%m-%d")-datetime.now()).days
                    dc=RD if days<=7 else AM if days<=30 else GD
                    days_txt=f"{days}D" if days>=0 else "OVERDUE"
                except: dc=GD; days_txt=""
                cell=Panel(); rl=QHBoxLayout()
                lf=QVBoxLayout()
                tl=QLabel((title[:24]+"..") if len(title)>24 else title)
                tl.setStyleSheet(f"color:{dc};font-size:10px;font-weight:bold;"
                    "font-family:'Courier New';background:transparent;")
                lf.addWidget(tl); lf.addWidget(lbl(date,TM,8))
                rl.addLayout(lf); rl.addStretch()
                badge=QFrame(); badge.setStyleSheet(f"background:{SM};border:none;")
                bl=QHBoxLayout(badge); bl.setContentsMargins(6,3,6,3)
                bl.addWidget(lbl(days_txt,dc,11,bold=True))
                rl.addWidget(badge); cell.lay().addLayout(rl); lay2.addWidget(cell)

    def _feedback_goals(self, msg, color=G):
        self._goals_fb.setText(msg)
        self._goals_fb.setStyleSheet(f"color:{color};font-size:9px;"
            "font-family:'Courier New';background:transparent;")
        QTimer.singleShot(3000, lambda: self._goals_fb.setText(""))

    def _add_goal(self):
        title=self._lg_title.text().strip()
        if not title: self._feedback_goals("! ENTER A GOAL TITLE",RD); return
        desc=self._lg_desc.text().strip()
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            goals=list(self._data.get("life_goals",[]))
            # Match Android LifeGoal model exactly (including subTasks)
            goals.append({
                "id":          str(uuid.uuid4()),
                "title":       title,
                "description": desc,
                "targetDate":  "",
                "progress":    0,
                "completed":   False,
                "subTasks":    []
            })
            # Android saveLifeGoals uses .set() not .update() -- full doc replace
            fields = {"items": _wrap(goals)}
            _req(f"{FIRESTORE}/users/{uid}/settings/lifegoals",
                 "PATCH", {"fields": fields}, token)
            QTimer.singleShot(0,lambda:self._lg_title.clear())
            QTimer.singleShot(0,lambda:self._feedback_goals(
                f"GOAL ADDED: {title[:28].upper()}",G))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _add_deadline(self):
        title=self._dl_title.text().strip(); date=self._dl_date.text().strip()
        if not title: self._feedback_goals("! ENTER A TITLE",RD); return
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            dls=list(self._data.get("deadlines",[]))
            # Match Android Deadline model
            dls.append({
                "id":       str(uuid.uuid4()),
                "title":    title,
                "date":     date,
                "category": "Thesis"
            })
            # Android saveDeadlines uses .set() -- full doc replace
            fields = {"items": _wrap(dls)}
            _req(f"{FIRESTORE}/users/{uid}/settings/deadlines",
                 "PATCH", {"fields": fields}, token)
            QTimer.singleShot(0,lambda:self._dl_title.clear())
            QTimer.singleShot(0,lambda:self._feedback_goals(
                f"DEADLINE: {title[:28].upper()}",AM))
            QTimer.singleShot(0,self._on_action)
        threading.Thread(target=run,daemon=True).start()

    def _save_note(self):
        text=self._note_text.toPlainText().strip()
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            date=today_key()
            if text:
                # Match Android saveNote exactly: text + updated timestamp
                # Use current time as ISO string since we can't use serverTimestamp via REST
                updated_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                fields = {
                    "text":    {"stringValue": text},
                    "updated": {"timestampValue": updated_str}
                }
                _req(f"{FIRESTORE}/users/{uid}/notes/{date}",
                     "PATCH", {"fields": fields}, token)
            else:
                _req(f"{FIRESTORE}/users/{uid}/notes/{date}","DELETE",token=token)
            QTimer.singleShot(0,lambda:self._note_fb.setText("NOTE SAVED"))
            QTimer.singleShot(0,lambda:self._note_fb.setStyleSheet(
                f"color:{G};font-size:9px;font-family:'Courier New';background:transparent;"))
            QTimer.singleShot(2000,lambda:self._note_fb.setText(""))
        threading.Thread(target=run,daemon=True).start()

    def _load_note(self):
        uid=self._get_uid(); token=self._get_token()
        if not uid or not token: return
        def run():
            doc=fs_get(f"users/{uid}/notes/{today_key()}",token)
            text=str(doc.get("text",""))
            QTimer.singleShot(0,lambda:self._note_text.setPlainText(text))
            QTimer.singleShot(0,lambda:self._note_fb.setText("NOTE LOADED"))
            QTimer.singleShot(2000,lambda:self._note_fb.setText(""))
        threading.Thread(target=run,daemon=True).start()


    # -- JOBS --------------------------------------------------
    def _build_jobs(self):
        w=QWidget(); w.setStyleSheet(f"background:{BK};")
        c=QWidget(); c.setStyleSheet(f"background:{BK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(8,6,8,6); lay.setSpacing(4)

        # Stats row
        lay.addWidget(SecHdr("// JOB SEARCH PIPELINE"))
        self._jobs_stats=Panel(GD)
        sr=QHBoxLayout(); sr.setSpacing(0)
        self._job_stat_widgets={}
        for cat,col in [("APPLIED",G),("INTERVIEW",AM),("OFFER",G),("REJECTED",RD)]:
            cell=QWidget(); cell.setStyleSheet("background:transparent;")
            cl=QVBoxLayout(cell); cl.setContentsMargins(8,6,8,6); cl.setSpacing(2)
            num=QLabel("0"); num.setStyleSheet(
                f"color:{col};font-size:18px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(num)
            cl.addWidget(lbl(cat,TD,8))
            sr.addWidget(cell); sr.addStretch() if cat!="REJECTED" else None
            self._job_stat_widgets[cat.lower()]=num
        self._jobs_stats.lay().addLayout(sr); lay.addWidget(self._jobs_stats)

        # Filter bar
        fb=QWidget(); fb.setStyleSheet("background:transparent;")
        fl=QHBoxLayout(fb); fl.setContentsMargins(0,4,0,4); fl.setSpacing(4)
        self._job_filter="ALL"; self._job_filter_btns={}
        for cat in ["ALL","INDUSTRY","ACADEMIA","STARTUP"]:
            btn=PipBtn(cat,GD); btn.clicked.connect(lambda _,c=cat:self._set_job_filter(c))
            self._job_filter_btns[cat]=btn; fl.addWidget(btn)
        fl.addStretch(); lay.addWidget(fb)

        # Job list
        self._jobs_scroll=QScrollArea(); self._jobs_scroll.setWidgetResizable(True)
        self._jobs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._jobs_scroll.setStyleSheet("QScrollArea{border:none;}")
        self._jobs_list=QWidget(); self._jobs_list.setStyleSheet(f"background:{BK};")
        self._jobs_lay=QVBoxLayout(self._jobs_list)
        self._jobs_lay.setContentsMargins(0,4,0,4); self._jobs_lay.setSpacing(3)
        self._jobs_lay.addStretch(); self._jobs_scroll.setWidget(self._jobs_list)
        lay.addWidget(self._jobs_scroll)

        self._jobs_fb=lbl("",G,9); lay.addWidget(self._jobs_fb)
        w.setLayout(QVBoxLayout()); w.layout().setContentsMargins(0,0,0,0)
        w.layout().addWidget(scrolled(c)); return w

    def _render_jobs(self, data):
        apps=data.get("job_apps",[])
        # Stats
        from collections import Counter
        counts=Counter(str(a.get("status","")).upper() for a in apps)
        for cat,widget in self._job_stat_widgets.items():
            widget.setText(str(counts.get(cat.upper(),0)))

        # Filter
        f=self._job_filter
        filtered=[a for a in apps
                  if f=="ALL" or str(a.get("sector","")).upper()==f]
        # Sort: active first, then by applied date desc
        STATUS_ORDER={"APPLIED":0,"INTERVIEW":1,"OFFER":2,"REJECTED":3,"":4}
        filtered.sort(key=lambda a:(
            STATUS_ORDER.get(str(a.get("status","")).upper(),4),
            -(a.get("appliedDateTs") or 0)
        ))

        while self._jobs_lay.count()>1:
            item=self._jobs_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not filtered:
            self._jobs_lay.insertWidget(0,lbl(
                "NO APPLICATIONS YET" if f=="ALL"
                else f"NO {f} APPLICATIONS",TM,10))
            return

        for i,a in enumerate(filtered):
            row=self._job_card(a)
            self._jobs_lay.insertWidget(i,row)

        # Update filter button colours
        for cat,btn in self._job_filter_btns.items():
            btn.set_color(G if cat==self._job_filter else GD)

    def _job_card(self, a):
        status=str(a.get("status","")).upper()
        company=str(a.get("company",""))
        role=str(a.get("role",""))
        sector=str(a.get("sector","")).upper()
        applied=str(a.get("appliedDate",""))
        interview=str(a.get("interviewDate",""))
        col={
            "APPLIED":G,"INTERVIEW":AM,"OFFER":G,"REJECTED":TD
        }.get(status,GD)

        # Days since applied
        days_str=""
        try:
            from datetime import datetime as _dt
            d=(datetime.now()-_dt.strptime(applied,"%Y-%m-%d")).days
            days_str=f"{d}D"
        except: pass

        card=QWidget(); card.setStyleSheet(f"background:{SF};border:1px solid {SM};")
        cl=QVBoxLayout(card); cl.setContentsMargins(10,7,10,7); cl.setSpacing(3)

        # Header row
        hr=QHBoxLayout(); hr.setSpacing(6)
        co_lbl=QLabel((company[:20]+"..") if len(company)>20 else company)
        co_lbl.setStyleSheet(f"color:{col};font-size:11px;font-weight:bold;"
                             "font-family:'Courier New';background:transparent;")
        hr.addWidget(co_lbl); hr.addStretch()

        # Status badge
        badge=QFrame(); badge.setStyleSheet(f"background:{SM};border:none;")
        bl=QHBoxLayout(badge); bl.setContentsMargins(6,2,6,2)
        bl.addWidget(lbl(status or "PENDING",col,9,bold=True))
        hr.addWidget(badge); cl.addLayout(hr)

        # Role + sector
        cl.addWidget(lbl(role[:34] if role else "ROLE TBD",TD,10))

        # Meta row
        mr=QHBoxLayout(); mr.setSpacing(10)
        if sector: mr.addWidget(lbl(sector,TM,8))
        if applied: mr.addWidget(lbl(f"APPLIED: {applied}",TM,8))
        if days_str: mr.addWidget(lbl(days_str,TM,8))
        mr.addStretch()

        # Interview date if set
        if interview and status=="INTERVIEW":
            try:
                from datetime import datetime as _dt
                d=(datetime.strptime(interview,"%Y-%m-%d")-datetime.now()).days
                dc=RD if d<=3 else AM if d<=7 else G
                mr.addWidget(lbl(f"INTERVIEW: {interview} ({d}D)",dc,8,bold=True))
            except:
                mr.addWidget(lbl(f"INTERVIEW: {interview}",AM,8))

        cl.addLayout(mr)

        # Follow-up nudge
        try:
            from datetime import datetime as _dt
            days_since=(_dt.now()-_dt.strptime(applied,"%Y-%m-%d")).days
            if status=="APPLIED" and days_since>=10:
                cl.addWidget(lbl(f"! {days_since}D SINCE APPLIED -- FOLLOW UP?",AM,8))
        except: pass

        return card

    def _set_job_filter(self, f):
        self._job_filter=f
        if self._data: self._render_jobs(self._data)

    def _pomo_set(self, m):
        self._pomo_mins=m; self._pomo_mins_lbl.setText(str(m)); self._pomo_reset()

    def _pomo_toggle_fn(self):
        if self._pomo_running:
            self._pomo_running=False; self._pomo_timer.stop()
            self._pomo_elapsed=int((time.time()*1000-self._pomo_start)/1000)
            self._pomo_toggle.setText("RESUME TIMER"); self._pomo_toggle.set_color(G)
        else:
            self._pomo_start=int(time.time()*1000)-(self._pomo_elapsed*1000)
            self._pomo_running=True; self._pomo_timer.start(1000)
            lbl_t=self._pomo_label.text() or "FOCUS"
            self._pomo_task_lbl.setText(lbl_t.upper())
            self._pomo_task_lbl.setStyleSheet(
                f"color:{G};font-size:9px;font-family:'Courier New';background:transparent;")
            self._pomo_toggle.setText("PAUSE TIMER"); self._pomo_toggle.set_color(AM)

    def _pomo_reset(self):
        self._pomo_running=False; self._pomo_timer.stop(); self._pomo_elapsed=0
        self._pomo_clock.setText(f"{self._pomo_mins:02d}:00")
        self._pomo_clock.setStyleSheet(
            f"color:{AM};font-size:36px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._pomo_toggle.setText("START TIMER"); self._pomo_toggle.set_color(G)
        self._pomo_bar.set(0,100,G)

    def _pomo_tick(self):
        if not self._pomo_running: return
        limit=self._pomo_mins*60
        elapsed=int((time.time()*1000-self._pomo_start)/1000)
        left=max(0,limit-elapsed); m,s=divmod(left,60)
        self._pomo_clock.setText(f"{m:02d}:{s:02d}")
        self._pomo_clock.setStyleSheet(
            f"color:{G};font-size:36px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        self._pomo_bar.set(min(elapsed,limit),limit,G)
        if left<=0:
            self._pomo_running=False; self._pomo_timer.stop()
            self._pomo_clock.setText("DONE!")
            self._pomo_clock.setStyleSheet(
                f"color:{AM};font-size:36px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            self._pomo_bar.set(1,1,AM)
            lbl_t=self._pomo_label.text() or "FOCUS"
            self._pomo_sessions.append({"label":lbl_t,"mins":self._pomo_mins,
                "time":datetime.now().strftime("%H:%M")})
            self._pomo_elapsed=0; self._pomo_toggle.setText("START TIMER")
            self._pomo_toggle.set_color(G)
            n=len(self._pomo_sessions)
            self._pomo_sess_lbl.setText(f"{n} SESSION{'S' if n!=1 else ''} TODAY")
            self._pomo_sess_lbl.setStyleSheet(
                f"color:{AM};font-size:8px;font-family:'Courier New';background:transparent;")
            self._rebuild_pomo_log()
            uid=self._get_uid(); token=self._get_token()
            if uid and token:
                end_ms=int(time.time()*1000); start_ms=end_ms-self._pomo_mins*60*1000
                threading.Thread(target=fs_add,
                    args=(f"users/{uid}/focusSessions",{"startMs":start_ms,"endMs":end_ms,
                        "durationMins":self._pomo_mins,"label":lbl_t},token),
                    daemon=True).start()

    def _rebuild_pomo_log(self):
        lay=self._pomo_log.lay()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not self._pomo_sessions:
            lay.addWidget(lbl("NO SESSIONS YET",TM,9)); return
        for s in self._pomo_sessions[-6:]:
            row=QWidget(); row.setStyleSheet("background:transparent;")
            rl=QHBoxLayout(row); rl.setContentsMargins(0,1,0,1)
            rl.addWidget(lbl(f"{s['time']} -- {s['label'][:18]}",GD,9))
            rl.addStretch(); rl.addWidget(lbl(f"{s['mins']}M",G,9))
            lay.addWidget(row)

# ????????????????????????????????????????????????????????????????
# MAIN WINDOW -- bar + collapsible panel
# ????????????????????????????????????????????????????????????????
class PipBoyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._expanded   = False
        self._session    = None
        self._token      = None
        self._uid        = None
        self._worker     = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(f"background:{BK};")

        cfg = load_config()
        screen = QApplication.primaryScreen().availableGeometry()
        x = cfg.get("x", screen.width()  - PANEL_W - 16)
        y = cfg.get("y", screen.height() - BAR_H   - 50)
        self.move(x, y)

        self._build()
        self._build_tray()
        self._auto_login()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(0)

        # Compact bar (always visible)
        self._bar = CompactBar(self)
        self._bar.expand_clicked.connect(self._toggle_expanded)
        lay.addWidget(self._bar)

        # Expanded panel (hidden by default)
        self._panel = ExpandedPanel(
            uid_fn=lambda: self._uid,
            token_fn=lambda: self._token,
            on_action=self._trigger_fetch,
            parent=self
        )
        self._panel.setFixedSize(PANEL_W, PANEL_H)
        self._panel.hide()
        lay.addWidget(self._panel)

        self.setFixedWidth(PANEL_W)
        self._update_size()

    def _update_size(self):
        h = BAR_H + (PANEL_H if self._expanded else 0)
        self.setFixedHeight(h)

    def _toggle_expanded(self):
        self._expanded = not self._expanded
        if self._expanded:
            # Render cached data immediately so panel isn't blank
            if self._panel._data:
                self._panel.update_data(self._panel._data)
            self._panel.show()
            # Trigger a fresh fetch in background
            self._trigger_fetch()
        else:
            self._panel.hide()
        self._bar.set_expanded(self._expanded)
        self._update_size()
        # Keep window on screen
        screen = QApplication.primaryScreen().availableGeometry()
        pos = self.pos()
        if pos.y() + self.height() > screen.height():
            self.move(pos.x(), screen.height() - self.height() - 4)
        self._save_pos()

    def _build_tray(self):
        px = QPixmap(16,16); px.fill(QColor(0,0,0,0))
        p = QPainter(px); p.setPen(QPen(QColor(G),1.5))
        p.drawEllipse(1,1,14,14); p.drawLine(8,4,8,12); p.drawLine(4,8,12,8); p.end()
        self._tray = QSystemTrayIcon(QIcon(px), self)
        self._tray.setToolTip("Pip-Boy Health")
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{"
            f"  background:{SF}; color:{G}; border:1px solid {GD};"
            f"  font-family:'Courier New'; font-size:9px; padding:2px;"
            f"}}"
            f"QMenu::item:selected {{"
            f"  background:#0d2e18;"
            f"}}"
            f"QMenu::separator {{"
            f"  background:{SM}; height:1px; margin:2px 4px;"
            f"}}"
        )
        menu.addAction("SHOW/HIDE",self._toggle_expanded)
        menu.addSeparator()
        menu.addAction("QUIT",QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda r:
            self._toggle_expanded() if r==QSystemTrayIcon.ActivationReason.Trigger else None)
        self._tray.show()

    def _save_pos(self):
        cfg = load_config(); cfg["x"]=self.x(); cfg["y"]=self.y()
        save_config(cfg)

    # Drag on bar title area
    def mousePressEvent(self, e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if hasattr(self,"_drag_pos") and e.buttons()==Qt.MouseButton.LeftButton:
            delta=e.globalPosition().toPoint()-self._drag_pos
            self._drag_pos=e.globalPosition().toPoint()
            self.move(self.pos()+delta)

    def mouseReleaseEvent(self, e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._save_pos()

    def closeEvent(self, e):
        e.ignore(); self.hide()

    # ?? Auth ???????????????????????????????????????????????????
    def _auto_login(self):
        session = load_session()
        if session and session.get("id_token") and session.get("uid"):
            # Warn if session has no refresh token (old auth file)
            if not session.get("refresh_token"):
                print("WARNING: saved session has no refresh_token.")
                print("Run: python pipboy_auth.py --reauth")
            # Stamp issued_at as now if missing so age calculation works
            if not session.get("issued_at"):
                session = dict(session)
                session["issued_at"] = int(time.time())
                save_session(session)
            self._session = session
            self._token   = session["id_token"]
            self._uid     = session["uid"]
            self._start_worker()
        else:
            self._bar.set_status("RUN pipboy_auth.py TO SIGN IN", RD)

    def _start_worker(self):
        self._worker = Worker()
        self._worker.set_session(self._session)
        self._worker.got_data.connect(self._on_data)
        self._worker.got_status.connect(self._bar.set_status)
        self._worker.start()
        self._worker.trigger()

    def _trigger_fetch(self):
        if self._worker: self._worker.trigger()

    def _on_data(self, data):
        if "_token" in data:
            self._token = data.pop("_token")
            if self._worker:
                self._worker._token   = self._token
                if self._worker._session:
                    self._worker._session["id_token"] = self._token

        # Apply theme colour from phone app settings
        theme = str(data.get("theme_color") or "#00FF66")
        if hasattr(self, "_last_theme") and self._last_theme != theme:
            self._apply_theme(theme)
        elif not hasattr(self, "_last_theme"):
            self._apply_theme(theme)
        self._last_theme = theme

        self._bar.update_data(data)
        if self._expanded: self._panel.update_data(data)
        else: self._panel._data = data  # cache for when panel opens

    def _apply_theme(self, hex_color):
        """Apply the phone app's chosen theme colour to the desktop."""
        global G, GD
        try:
            # Validate hex
            int(hex_color.lstrip("#"), 16)
            G = hex_color
            # GD = darkened version
            r,gr,b = [int(hex_color.lstrip("#")[i:i+2],16) for i in (0,2,4)]
            GD = "#{:02x}{:02x}{:02x}".format(
                max(0,int(r*0.65)), max(0,int(gr*0.65)), max(0,int(b*0.65)))
        except Exception:
            G = "#00FF66"; GD = "#00AA44"


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Pip-Boy Health")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(f"""
        * {{ font-family: 'Courier New'; }}
        QScrollBar:vertical {{ background:{BK};width:5px;border:none; }}
        QScrollBar::handle:vertical {{ background:{SM};border-radius:2px;min-height:16px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QToolTip {{ background:{SF};color:{G};border:1px solid {GD};font-size:9px;padding:3px 6px; }}
    """)
    w = PipBoyWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
