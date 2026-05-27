"""
main_window.py
--------------
Compact bar (56px, always-on-top) + collapsible panel design.
Bar shows context-sensitive stats; panel shows full tab set.
"""

import sys, threading, time
from datetime import datetime as _dt

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QSystemTrayIcon,
    QMenu, QApplication, QSizePolicy, QFrame, QStackedWidget
)
from PyQt6.QtCore  import Qt, QTimer, QThread, pyqtSignal, QPoint, QObject, QRect
from PyQt6.QtGui   import QIcon, QPixmap, QPainter, QColor, QPen, QFont, QCursor

import firebase as fb
from ui.style  import (BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED,
                        TEXT_DIM, TEXT_MUTED)
from ui.widgets import SectionHeader, PipButton, PipIcon, label, h_line

# Tab imports
from ui.tabs.health    import HealthTab
from ui.tabs.condition import ConditionTab
from ui.tabs.log       import LogTab
from ui.tabs.tasks     import TasksTab
from ui.tabs.writing   import WritingTab
from ui.tabs.goals     import GoalsTab
from ui.tabs.notes     import NotesTab
from ui.tabs.focus     import FocusTab
from ui.tabs.jobs      import JobsTab

# ── Window geometry constants ──────────────────────────────────
_W     = 340    # fixed window width
_BAR_H = 56     # compact bar height
_PAN_H = 560    # expanded panel height
_TOT_H = _BAR_H + _PAN_H


# ── Login worker thread ────────────────────────────────────────
class LoginWorker(QThread):
    """Runs Google device flow in a QThread so signals work correctly."""
    success = pyqtSignal(dict)
    error   = pyqtSignal(str)
    status  = pyqtSignal(str)

    def run(self):
        from pipboy_auth import (
            CLIENT_ID, CLIENT_SECRET,
            device_login, firebase_sign_in,
            save_token
        )
        try:
            self.status.emit("OPENING BROWSER...")
            access = device_login(CLIENT_ID, CLIENT_SECRET)
            self.status.emit("AUTHENTICATING WITH FIREBASE...")
            auth = firebase_sign_in(access)
            auth["issued_at"] = int(time.time())
            save_token(auth)
            self.success.emit(auth)
        except Exception as e:
            self.error.emit(str(e))


# ── Data worker thread ─────────────────────────────────────────
class DataWorker(QThread):
    """Fetches all Firebase data in a background thread."""
    data_ready   = pyqtSignal(dict)
    status_ready = pyqtSignal(str, str)   # message, color

    def __init__(self, uid, get_token_fn):
        super().__init__()
        self._uid       = uid
        self._get_token = get_token_fn
        self._running   = True

    def run(self):
        while self._running:
            self._fetch()
            for _ in range(60):
                if not self._running: return
                time.sleep(0.5)

    def fetch_now(self):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        token = self._get_token()
        if not token: return

        self.status_ready.emit("SYNCING...", AMBER)

        session = fb.load_session()
        session, token = fb.maybe_refresh_token(session)

        data = fb.fetch_all(self._uid, token)

        if data.get("_auth_error"):
            rtok = (session or {}).get("refresh_token", "")
            if rtok:
                new_id, new_ref = fb.refresh_id_token(rtok)
                if new_id:
                    session["id_token"]      = new_id
                    session["refresh_token"] = new_ref or rtok
                    session["issued_at"]     = int(time.time())
                    fb.save_session(session)
                    token = new_id
                    data  = fb.fetch_all(self._uid, token)
            if data.get("_auth_error"):
                self.status_ready.emit(
                    "SESSION EXPIRED -- RUN pipboy_auth.py --reauth", RED)
                return

        data["_token"] = token
        self.data_ready.emit(data)
        ts = _dt.now().strftime("%H:%M:%S")
        self.status_ready.emit(f"VAULT-TEC SYNC {ts}", GREEN_DIM)

    def stop(self):
        self._running = False


# ── Tray icon helper ───────────────────────────────────────────
def _make_tray_icon():
    px = QPixmap(32, 32)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(BLACK))
    p.setPen(QPen(QColor(GREEN), 2))
    p.drawEllipse(1, 1, 30, 30)
    p.setPen(QPen(QColor(GREEN_DIM), 1))
    p.drawEllipse(5, 5, 22, 22)
    p.setPen(QPen(QColor(GREEN), 2))
    p.drawLine(16, 8, 16, 24)
    p.drawLine(8, 16, 24, 16)
    p.end()
    return QIcon(px)


# ── Login screen ───────────────────────────────────────────────
class LoginScreen(QWidget):
    sign_in_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(16)

        title = QLabel("PIP-BOY 3000")
        title.setStyleSheet(
            f"color: {GREEN}; font-size: 28px; font-weight: bold;"
            f" letter-spacing: 4px; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("VAULT-TEC HEALTH COMPANION")
        sub.setStyleSheet(
            f"color: {GREEN_DIM}; font-size: 11px; letter-spacing: 2px; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)

        lay.addSpacing(20)

        boot = QLabel(
            "ROBCO INDUSTRIES UNIFIED OPERATING SYSTEM\n"
            "AUTHENTICATION REQUIRED TO ACCESS\n"
            "PERSONAL HEALTH DATABASE")
        boot.setStyleSheet(
            f"color: {GREEN_DIM}; font-size: 10px; background: transparent;")
        boot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(boot)

        lay.addSpacing(20)

        self._btn = PipButton("SIGN IN WITH GOOGLE", GREEN)
        self._btn.setFixedWidth(260)
        self._btn.clicked.connect(self.sign_in_clicked)
        lay.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {AMBER}; font-size: 10px; background: transparent;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status)

    def set_status(self, text, color=AMBER):
        self._status.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent;")
        self._status.setText(text)

    def set_busy(self, busy):
        self._btn.setEnabled(not busy)
        self._btn.setText("AUTHENTICATING..." if busy else "SIGN IN WITH GOOGLE")


# ── Compact Bar ────────────────────────────────────────────────
class CompactBar(QWidget):
    """Always-visible 56px bar drawn with QPainter. Context-sensitive stats."""
    expand_clicked = pyqtSignal()

    # Current display state
    _cond_score  = 0
    _cond_col    = GREEN_DIM
    _status_text = "INITIALIZING..."
    _status_col  = AMBER
    _stats       = []     # list of 3 dicts: {label, value, pct, color}
    _right_text  = ""
    _right_value = ""
    _right_col   = GREEN_DIM
    _expanded    = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_W, _BAR_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drag_pos = None

    def set_expanded(self, v):
        self._expanded = v
        self.update()

    def update_data(self, data):
        d = data.get("daily", {})
        g = data.get("goals", {})

        # Condition score
        self._cond_score = int(fb.sf(d.get("condition") or d.get("overall")))
        self._cond_col = (GREEN if self._cond_score >= 65
                          else AMBER if self._cond_score >= 35 else RED)

        # Context stats
        hour   = _dt.now().hour
        water  = float(d.get("water")  or 0);  wg  = float(g.get("waterGoalL")   or 3.0)
        sleep  = float(d.get("sleep")  or 0);  slg = float(g.get("sleepGoalH")   or 8.0)
        steps  = float(d.get("steps")  or 0);  stg = float(g.get("stepGoal")     or 7500)
        active = float(d.get("active") or 0);  ag  = float(g.get("activeGoalMin") or 30)
        thesis = data.get("thesis", {})
        todos  = data.get("todos", [])

        def fmt(v):
            return f"{v/1000:.1f}K" if v >= 1000 else str(int(v))

        today_key = fb.today_key()
        today_words = next(
            (int(l.get("words", 0) or 0)
             for l in (thesis.get("writingLogs") or [])
             if l.get("date") == today_key),
            0
        )
        pending_tasks = sum(1 for t in todos if not t.get("done"))

        all_stats = {
            "H2O": (f"{water:.1f}L", water / max(0.01, wg),
                    GREEN if water / max(0.01, wg) >= 0.25 else RED),
            "ZZZ": (f"{sleep:.1f}H", sleep / max(0.01, slg),
                    GREEN if sleep / max(0.01, slg) >= 0.625 else RED),
            "STP": (fmt(steps), steps / max(1, stg),
                    GREEN if steps / max(1, stg) >= 0.25 else RED),
            "ACT": (f"{int(active)}M", active / max(1, ag),
                    GREEN if active / max(1, ag) >= 0.33 else RED),
            "WRD": (f"{today_words}", min(1.0, today_words / 500), AMBER),
            "TSK": (f"{pending_tasks}", max(0, 1.0 - pending_tasks / 10),
                    AMBER if pending_tasks > 0 else GREEN),
        }

        if 4 <= hour < 12:
            order = ["ZZZ", "H2O", "STP"]
        elif 12 <= hour < 19:
            order = ["H2O", "STP", "ACT"]
        else:
            order = ["H2O", "WRD", "TSK"]

        # Override: critical stats (below 25% of goal) always get shown first
        critical = [k for k in ["H2O", "ZZZ", "STP", "ACT"]
                    if all_stats[k][2] == RED and k not in order[:1]]
        for k in critical:
            if k not in order:
                order.pop()
                order.insert(0, k)

        self._stats = [
            {"label": k, "value": all_stats[k][0],
             "pct": all_stats[k][1], "color": all_stats[k][2]}
            for k in order[:3]
        ]

        # Right section
        defence = str(thesis.get("defenceDate") or "").strip()
        self._right_text  = ""
        self._right_value = ""
        self._right_col   = GREEN_DIM
        if defence:
            try:
                from datetime import datetime
                days = (datetime.strptime(defence, "%Y-%m-%d") - datetime.now()).days
                if days <= 60:
                    self._right_text  = "DEF"
                    self._right_value = str(days)
                    self._right_col   = (RED if days < 14
                                         else AMBER if days < 30 else GREEN)
            except Exception:
                pass

        if not self._right_value:
            cond = self._cond_score
            labels = [(95, "OPTM"), (80, "FULL"), (65, "IRRD"),
                      (50, "STMP"), (35, "CRIT"), (20, "DMGD"), (0, "MDIC")]
            self._right_text  = next((l for t, l in labels if cond >= t), "----")
            self._right_value = ""
            self._right_col   = (GREEN if cond >= 65
                                  else AMBER if cond >= 35 else RED)

        self.update()

    def set_status(self, text, color):
        self._status_text = text
        self._status_col  = color
        self.update()

    # ── Drawing ────────────────────────────────────────────────
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor(BLACK))

        # Phosphor border (multi-layer glow)
        for alpha, thickness in [(30, 3), (60, 2), (120, 1)]:
            bc = QColor(GREEN_DIM)
            bc.setAlpha(alpha)
            pen = QPen(bc, thickness)
            p.setPen(pen)
            p.drawRect(0, 0, w - 1, h - 1)

        # ── Left: condition score ──────────────────────────────
        lx = 8
        score_str = str(self._cond_score) if self._cond_score else "--"
        p.setPen(QColor(self._cond_col))
        f_big = QFont("Courier New", 18, QFont.Weight.Bold)
        p.setFont(f_big)
        p.drawText(QRect(lx, 4, 50, 28), Qt.AlignmentFlag.AlignLeft, score_str)

        f_tiny = QFont("Courier New", 7)
        p.setFont(f_tiny)
        p.setPen(QColor(TEXT_MUTED))
        p.drawText(QRect(lx, 30, 50, 12), Qt.AlignmentFlag.AlignLeft, "COND")

        # Divider after left section
        div_x1 = 62
        p.setPen(QPen(QColor(SURF_MID), 1))
        p.drawLine(div_x1, 6, div_x1, h - 10)

        # ── Middle: 3 stat columns ─────────────────────────────
        mid_start = div_x1 + 4
        mid_end   = w - 72   # leave room for right section + button
        mid_w     = mid_end - mid_start
        col_w     = mid_w // 3

        for i, stat in enumerate(self._stats[:3]):
            cx = mid_start + i * col_w
            col = stat["color"]

            # Label
            p.setPen(QColor(TEXT_MUTED))
            f_lbl = QFont("Courier New", 7)
            p.setFont(f_lbl)
            p.drawText(QRect(cx, 5, col_w - 2, 10),
                       Qt.AlignmentFlag.AlignLeft, stat["label"])

            # Value
            p.setPen(QColor(col))
            f_val = QFont("Courier New", 10, QFont.Weight.Bold)
            p.setFont(f_val)
            p.drawText(QRect(cx, 14, col_w - 2, 16),
                       Qt.AlignmentFlag.AlignLeft, stat["value"])

            # Mini 6-segment bar
            pct = max(0.0, min(1.0, stat["pct"]))
            filled = int(pct * 6)
            seg_w = (col_w - 4) // 6
            for s in range(6):
                sx = cx + s * (seg_w + 1)
                if s < filled:
                    bc = QColor(col)
                    bc.setAlpha(200)
                else:
                    bc = QColor(SURF_MID)
                p.fillRect(sx, 35, max(1, seg_w), 5, bc)

        # Divider before right section
        div_x2 = mid_end + 2
        p.setPen(QPen(QColor(SURF_MID), 1))
        p.drawLine(div_x2, 6, div_x2, h - 10)

        # ── Right section ──────────────────────────────────────
        rx = div_x2 + 4
        rw = 38
        if self._right_value:
            # Large number (e.g. defence days)
            p.setPen(QColor(self._right_col))
            p.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
            p.drawText(QRect(rx, 6, rw, 20),
                       Qt.AlignmentFlag.AlignLeft, self._right_value)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Courier New", 7))
            p.drawText(QRect(rx, 26, rw, 10),
                       Qt.AlignmentFlag.AlignLeft, self._right_text)
        else:
            # Condition label text
            p.setPen(QColor(self._right_col))
            p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            p.drawText(QRect(rx, 10, rw, 20),
                       Qt.AlignmentFlag.AlignLeft, self._right_text)

        # ── Expand button ──────────────────────────────────────
        bx = w - 20
        p.setPen(QColor(GREEN_DIM))
        p.setFont(QFont("Courier New", 10))
        arrow = "▲" if self._expanded else "▼"
        p.drawText(QRect(bx, 16, 16, 16),
                   Qt.AlignmentFlag.AlignCenter, arrow)

        # ── Bottom status strip ────────────────────────────────
        sc = QColor(self._status_col)
        sc.setAlpha(180)
        p.setPen(sc)
        p.setFont(QFont("Courier New", 7))
        p.drawText(QRect(4, h - 11, w - 8, 10),
                   Qt.AlignmentFlag.AlignLeft, self._status_text[:60])

        # ── Scanline overlay ───────────────────────────────────
        scan_col = QColor(0, 0, 0, 22)
        y = 0
        while y < h:
            p.fillRect(0, y, w, 1, scan_col)
            y += 3

    # ── Mouse events ───────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
            self._drag_start_win = self.window().pos()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_pos
            self.window().move(self._drag_start_win + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            cfg = fb.load_config()
            pos = self.window().pos()
            cfg["x"] = pos.x(); cfg["y"] = pos.y()
            fb.save_config(cfg)
            # If mouse barely moved, treat as click → toggle
            if self._drag_pos:
                delta = e.globalPosition().toPoint() - self._drag_pos
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    self.expand_clicked.emit()
            self._drag_pos = None


# ── Main window ────────────────────────────────────────────────
class PipBoyWindow(QWidget):
    """Frameless always-on-top window: compact bar + collapsible panel."""

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self._session    = None
        self._token      = None
        self._uid        = None
        self._worker     = None
        self._data       = {}
        self._expanded   = False
        self._last_theme = None

        # Size + position
        cfg    = fb.load_config()
        screen = QApplication.primaryScreen().availableGeometry()
        x = cfg.get("x", screen.width()  - _W  - 16)
        y = cfg.get("y", screen.height() - _BAR_H - 50)
        self.setGeometry(x, y, _W, _BAR_H)

        self._build()
        self._build_tray()
        self._try_auto_login()

    # ── Build UI ───────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Compact bar
        self._bar = CompactBar(self)
        self._bar.expand_clicked.connect(self._toggle_expanded)
        root.addWidget(self._bar)

        # Collapsible panel
        self._panel = QWidget(self)
        self._panel.setFixedSize(_W, _PAN_H)
        self._panel.setStyleSheet(
            f"background: {BLACK}; border: 1px solid {GREEN_DIM};")
        self._panel.hide()
        root.addWidget(self._panel)

        panel_lay = QVBoxLayout(self._panel)
        panel_lay.setContentsMargins(1, 1, 1, 1)
        panel_lay.setSpacing(0)

        # Stacked widget: login OR tabs
        self._stack = QStackedWidget()
        panel_lay.addWidget(self._stack)

        # Login screen
        self._login_screen = LoginScreen()
        self._login_screen.sign_in_clicked.connect(self._start_login)
        self._stack.addWidget(self._login_screen)  # index 0

        # Tab widget (hidden until signed in)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {BLACK};
            }}
            QTabBar {{
                background: {SURF};
            }}
            QTabBar::tab {{
                background: {SURF};
                color: {GREEN_DIM};
                font-family: "Courier New";
                font-size: 9px;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid transparent;
                letter-spacing: 1px;
            }}
            QTabBar::tab:selected {{
                color: {GREEN};
                background: {BLACK};
                border-bottom: 2px solid {GREEN};
            }}
            QTabBar::tab:hover:!selected {{
                color: {GREEN};
                background: rgba(0,255,102,0.05);
            }}
        """)
        self._stack.addWidget(self._tabs)   # index 1

    def _build_tabs(self):
        """Called once after sign-in. Creates all tab widgets."""
        self._tab_health    = HealthTab(self._data, self._token)
        self._tab_condition = ConditionTab(self._data, self._token)
        self._tab_log       = LogTab(self._uid, self._token, self._on_log_action)
        self._tab_tasks     = TasksTab(self._uid, self._token)
        self._tab_writing   = WritingTab(self._uid, self._token)
        self._tab_goals     = GoalsTab(self._uid, self._token)
        self._tab_jobs      = JobsTab(self._uid, self._token)
        self._tab_notes     = NotesTab(self._uid, self._token)
        self._tab_focus     = FocusTab(self._uid, self._token)

        for tab, name in [
            (self._tab_health,    "HLTH"),
            (self._tab_condition, "SPEC"),
            (self._tab_log,       "LOG"),
            (self._tab_tasks,     "TASK"),
            (self._tab_writing,   "WRTE"),
            (self._tab_goals,     "GOAL"),
            (self._tab_jobs,      "JOBS"),
            (self._tab_notes,     "NOTE"),
            (self._tab_focus,     "FOCU"),
        ]:
            self._tabs.addTab(tab, name)

    def _build_tray(self):
        icon = _make_tray_icon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Pip-Boy Health — Vault-Tec")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {SURF};
                color: {GREEN};
                border: 1px solid {GREEN_DIM};
                font-family: "Courier New";
                font-size: 10px;
                padding: 4px;
            }}
            QMenu::item:selected {{
                background: rgba(0,255,102,0.12);
            }}
            QMenu::separator {{
                background: {SURF_MID};
                height: 1px;
                margin: 4px 0;
            }}
        """)
        menu.addAction("Pip-Boy Health").setEnabled(False)
        menu.addSeparator()
        show_act = menu.addAction("SHOW / HIDE")
        show_act.triggered.connect(self._tray_toggle)
        menu.addSeparator()
        menu.addAction("QUIT", QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    # ── Toggle expanded panel ──────────────────────────────────
    def _toggle_expanded(self):
        self._expanded = not self._expanded
        self._bar.set_expanded(self._expanded)

        if self._expanded:
            self._panel.show()
            self.setFixedSize(_W, _TOT_H)
            # Keep window on screen
            screen = QApplication.primaryScreen().availableGeometry()
            pos    = self.pos()
            new_y  = min(pos.y(), screen.bottom() - _TOT_H)
            if new_y != pos.y():
                self.move(pos.x(), new_y)
        else:
            self._panel.hide()
            self.setFixedSize(_W, _BAR_H)

        # Save position
        cfg = fb.load_config()
        pos = self.pos()
        cfg["x"] = pos.x(); cfg["y"] = pos.y()
        fb.save_config(cfg)

    # ── Auth ───────────────────────────────────────────────────
    def _try_auto_login(self):
        session = fb.load_session()
        if session and session.get("id_token") and session.get("uid"):
            self._session = session
            self._token   = session["id_token"]
            self._uid     = session["uid"]
            self._on_signed_in(session.get("email", ""))
        else:
            # Show login screen — auto-expand panel
            self._stack.setCurrentIndex(0)
            if not self._expanded:
                self._toggle_expanded()

    def _start_login(self):
        self._login_screen.set_busy(True)
        self._login_screen.set_status("OPENING BROWSER...", AMBER)

        self._login_worker = LoginWorker()
        self._login_worker.success.connect(self._on_login_success)
        self._login_worker.error.connect(self._on_login_error)
        self._login_worker.status.connect(
            lambda msg: self._login_screen.set_status(msg, AMBER))
        self._login_worker.start()

    def _on_login_success(self, auth):
        self._session = auth
        self._token   = auth["id_token"]
        self._uid     = auth["uid"]
        self._on_signed_in(auth.get("email", ""))

    def _on_login_error(self, msg):
        self._login_screen.set_busy(False)
        self._login_screen.set_status(f"ERROR: {msg}", RED)
        self._login_worker = None

    def _on_signed_in(self, email):
        self._build_tabs()
        self._stack.setCurrentIndex(1)   # show tabs
        self._bar.set_status(f"SIGNED IN: {(email or 'USER')[:20]}", GREEN_DIM)
        self._start_worker()

    def _start_worker(self):
        self._worker = DataWorker(self._uid, lambda: self._token)
        self._worker.data_ready.connect(self._on_data)
        self._worker.status_ready.connect(self._bar.set_status)
        self._worker.start()
        self._worker.fetch_now()

    # ── Data ───────────────────────────────────────────────────
    def _on_data(self, data):
        if "_token" in data:
            self._token = data.pop("_token")

        self._data = data

        # Theme color
        theme = str(data.get("theme_color") or "#00FF66")
        if self._last_theme != theme:
            self._apply_theme(theme)
            self._last_theme = theme

        # Update compact bar
        self._bar.update_data(data)

        # Push data to tabs if they exist
        if not hasattr(self, "_tab_health"):
            return

        for tab in [
            self._tab_health, self._tab_condition,
            self._tab_tasks,  self._tab_writing,
            self._tab_goals,  self._tab_notes,
            self._tab_jobs,
        ]:
            tab.update_data(data)

        self._tab_log.set_token(self._token)
        self._tab_focus.set_token(self._token)

        # Push data to log tab too
        self._tab_log.update_data(data)

    def _apply_theme(self, hex_color):
        """Apply the phone app's chosen theme colour to style module globals."""
        import ui.style as _style
        try:
            int(hex_color.lstrip("#"), 16)
            g  = hex_color
            r, gr, b = [int(hex_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
            gd = "#{:02x}{:02x}{:02x}".format(
                max(0, int(r * 0.65)),
                max(0, int(gr * 0.65)),
                max(0, int(b * 0.65))
            )
            _style.GREEN     = g
            _style.GREEN_DIM = gd
        except Exception:
            pass

    def _on_log_action(self):
        if self._worker:
            self._worker.fetch_now()

    # ── Tray helpers ───────────────────────────────────────────
    def _tray_toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._tray_toggle()

    # ── Close → hide to tray ───────────────────────────────────
    def closeEvent(self, e):
        e.ignore()
        self.hide()
