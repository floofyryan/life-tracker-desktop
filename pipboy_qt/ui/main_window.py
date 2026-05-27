"""
main_window.py
--------------
The root QMainWindow. Frameless, always-on-top, draggable,
system tray icon, tab container. Owns the data refresh loop.
"""

import sys, threading, time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QSystemTrayIcon,
    QMenu, QApplication, QSizePolicy, QFrame
)
from PyQt6.QtCore  import Qt, QTimer, QThread, pyqtSignal, QPoint, QObject
from PyQt6.QtGui   import QIcon, QPixmap, QPainter, QColor, QPen, QFont, QCursor

import firebase as fb
from ui.style  import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM
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


# ── Login worker thread ────────────────────────────────────────
class LoginWorker(QThread):
    """Runs Google device flow in a QThread so signals work correctly."""
    success = pyqtSignal(dict)   # emits auth dict
    error   = pyqtSignal(str)    # emits error message
    status  = pyqtSignal(str)    # emits status text for the UI

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
        self._get_token = get_token_fn   # callable returning current token
        self._running   = True

    def run(self):
        while self._running:
            self._fetch()
            # Sleep 30s in small chunks so we can stop quickly
            for _ in range(60):
                if not self._running: return
                time.sleep(0.5)

    def fetch_now(self):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        token = self._get_token()
        if not token: return

        self.status_ready.emit("SYNCING...", AMBER)

        # Check + refresh token synchronously
        session = fb.load_session()
        session, token = fb.maybe_refresh_token(session)

        data = fb.fetch_all(self._uid, token)

        if data.get("_auth_error"):
            # Try one inline refresh then retry
            rtok = (session or {}).get("refresh_token","")
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
        ts = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        self.status_ready.emit(f"VAULT-TEC SYNC {ts}", GREEN_DIM)

    def stop(self):
        self._running = False


# ── Pip-Boy icon ───────────────────────────────────────────────
def _make_tray_icon():
    """Draw a 32x32 Pip-Boy icon for the system tray."""
    px = QPixmap(32, 32)
    px.fill(QColor(0,0,0,0))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Background circle
    p.setBrush(QColor(BLACK))
    p.setPen(QPen(QColor(GREEN), 2))
    p.drawEllipse(1, 1, 30, 30)
    # Inner ring
    p.setPen(QPen(QColor(GREEN_DIM), 1))
    p.drawEllipse(5, 5, 22, 22)
    # Health cross
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


# ── Title bar ──────────────────────────────────────────────────
class TitleBar(QWidget):
    close_clicked  = pyqtSignal()
    minimise_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet(f"background: {SURF}; border-bottom: 1px solid {SURF_MID};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(8)

        icon = PipIcon("condition", GREEN, 20, self)
        lay.addWidget(icon)

        title = QLabel("PIP-BOY 3000")
        title.setStyleSheet(
            f"color: {GREEN}; font-size: 11px; font-weight: bold;"
            f" letter-spacing: 2px; background: transparent;")
        lay.addWidget(title)

        sep = QLabel("//")
        sep.setStyleSheet(f"color: {SURF_MID}; font-size: 11px; background: transparent;")
        lay.addWidget(sep)

        self._user_lbl = QLabel("NOT SIGNED IN")
        self._user_lbl.setStyleSheet(
            f"color: {GREEN_DIM}; font-size: 9px; background: transparent;")
        lay.addWidget(self._user_lbl)

        lay.addStretch()

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {AMBER}; font-size: 8px; background: transparent;")
        lay.addWidget(self._dot)

        self._status_lbl = QLabel("INITIALIZING...")
        self._status_lbl.setStyleSheet(
            f"color: {GREEN_DIM}; font-size: 9px; background: transparent;")
        lay.addWidget(self._status_lbl)

        lay.addSpacing(12)

        min_btn = QPushButton("—")
        min_btn.setFixedSize(24, 24)
        min_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {GREEN_DIM};
                           border: none; font-size: 12px; }}
            QPushButton:hover {{ color: {GREEN}; background: rgba(0,255,102,0.1); }}
        """)
        min_btn.clicked.connect(self.minimise_clicked)
        lay.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {RED};
                           border: none; font-size: 12px; }}
            QPushButton:hover {{ background: rgba(255,51,51,0.15); }}
        """)
        close_btn.clicked.connect(self.close_clicked)
        lay.addWidget(close_btn)

        # Drag support
        self._drag_pos = None

    def set_user(self, email):
        self._user_lbl.setText(email or "SIGNED IN")

    def set_status(self, text, color):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; background: transparent;")
        dot_col = GREEN if color == GREEN_DIM else color
        self._dot.setStyleSheet(
            f"color: {dot_col}; font-size: 8px; background: transparent;")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = e.globalPosition().toPoint()
            self.window().move(self.window().pos() + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Save position on release
            cfg = fb.load_config()
            pos = self.window().pos()
            cfg["x"] = pos.x(); cfg["y"] = pos.y()
            fb.save_config(cfg)
            self._drag_pos = None


# ── Main window ────────────────────────────────────────────────
class PipBoyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Frameless + always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool   # keeps off taskbar alt-tab list
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Size + position
        cfg = fb.load_config()
        w, h = 320, 600
        screen = QApplication.primaryScreen().availableGeometry()
        x = cfg.get("x", screen.width()  - w - 16)
        y = cfg.get("y", screen.height() - h - 50)
        self.setGeometry(x, y, w, h)
        self.setMinimumSize(280, 400)

        self._session = None
        self._token   = None
        self._uid     = None
        self._worker  = None
        self._data    = {}

        self._build_ui()
        self._build_tray()
        self._try_auto_login()

    # ── UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        # Outer frame with 1px green border
        outer = QWidget()
        outer.setStyleSheet(f"""
            QWidget {{
                background-color: {BLACK};
                border: 1px solid {GREEN_DIM};
            }}
        """)
        self.setCentralWidget(outer)

        root_lay = QVBoxLayout(outer)
        root_lay.setContentsMargins(1, 1, 1, 1)
        root_lay.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar(self)
        self._title_bar.close_clicked.connect(self._on_close)
        self._title_bar.minimise_clicked.connect(self.showMinimized)
        root_lay.addWidget(self._title_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {GREEN_DIM}; max-height: 1px; border: none;")
        root_lay.addWidget(sep)

        # Stack: login screen OR tabs
        self._stack = QWidget()
        stack_lay   = QVBoxLayout(self._stack)
        stack_lay.setContentsMargins(0, 0, 0, 0)
        stack_lay.setSpacing(0)
        root_lay.addWidget(self._stack)

        # Login screen
        self._login_screen = LoginScreen()
        self._login_screen.sign_in_clicked.connect(self._start_login)
        stack_lay.addWidget(self._login_screen)

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
                font-size: 10px;
                font-weight: bold;
                padding: 8px 10px;
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
        stack_lay.addWidget(self._tabs)
        self._tabs.hide()

    def _build_tabs(self):
        """Called once after sign-in. Creates all tab widgets."""
        self._tab_health    = HealthTab(self._data, self._token)
        self._tab_condition = ConditionTab(self._data, self._token)
        self._tab_log       = LogTab(self._uid, self._token, self._on_log_action)
        self._tab_tasks     = TasksTab(self._uid, self._token)
        self._tab_writing   = WritingTab(self._uid, self._token)
        self._tab_goals     = GoalsTab(self._uid, self._token)
        self._tab_notes     = NotesTab(self._uid, self._token)
        self._tab_focus     = FocusTab(self._uid, self._token)

        for tab, name in [
            (self._tab_health,    "HEALTH"),
            (self._tab_condition, "SPECIAL"),
            (self._tab_log,       "LOG"),
            (self._tab_tasks,     "TASKS"),
            (self._tab_writing,   "WRITING"),
            (self._tab_goals,     "GOALS"),
            (self._tab_notes,     "NOTES"),
            (self._tab_focus,     "FOCUS"),
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
        for tab_name in ["Health","Special","Log","Tasks","Writing","Goals","Notes","Focus"]:
            idx = ["Health","Special","Log","Tasks","Writing","Goals","Notes","Focus"].index(tab_name)
            menu.addAction(tab_name.upper(), lambda i=idx: self._show_tab(i))
        menu.addSeparator()
        menu.addAction("QUIT", QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _show_tab(self, idx):
        self.show()
        self.raise_()
        self.activateWindow()
        if self._tabs.isVisible():
            self._tabs.setCurrentIndex(idx)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()

    # ── Auth ───────────────────────────────────────────────────
    def _try_auto_login(self):
        """Check for saved session and sign in automatically."""
        session = fb.load_session()
        if session and session.get("id_token") and session.get("uid"):
            self._session = session
            self._token   = session["id_token"]
            self._uid     = session["uid"]
            email         = session.get("email","")
            self._on_signed_in(email)
        else:
            self._login_screen.show()
            self._tabs.hide()

    def _start_login(self):
        """Launch Google device flow in a QThread so signals reach the main thread."""
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
        self._on_signed_in(auth.get("email",""))

    def _on_login_error(self, msg):
        self._login_screen.set_busy(False)
        self._login_screen.set_status(f"ERROR: {msg}", RED)
        self._login_worker = None

    def _on_signed_in(self, email):
        self._login_screen.hide()
        self._build_tabs()
        self._tabs.show()
        self._title_bar.set_user(email)
        self._start_worker()

    def _start_worker(self):
        self._worker = DataWorker(self._uid, lambda: self._token)
        self._worker.data_ready.connect(self._on_data)
        self._worker.status_ready.connect(self._title_bar.set_status)
        self._worker.start()
        # Immediate first fetch
        self._worker.fetch_now()

    # ── Data ───────────────────────────────────────────────────
    def _on_data(self, data):
        """Called on main thread when fresh data arrives."""
        # Update token if it was refreshed
        if "_token" in data:
            self._token = data.pop("_token")

        self._data = data

        # Push data to all tabs
        for tab in [
            self._tab_health, self._tab_condition,
            self._tab_tasks,  self._tab_writing,
            self._tab_goals,  self._tab_notes,
        ]:
            tab.update_data(data)

        # Update log and focus tabs with fresh token
        self._tab_log.set_token(self._token)
        self._tab_focus.set_token(self._token)

    def _on_log_action(self):
        """Called after a log action — trigger immediate refresh."""
        if self._worker:
            self._worker.fetch_now()

    # ── Close / minimise ───────────────────────────────────────
    def _on_close(self):
        cfg = fb.load_config()
        pos = self.pos()
        cfg["x"] = pos.x(); cfg["y"] = pos.y()
        fb.save_config(cfg)
        if self._worker:
            self._worker.stop()
        self._tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        e.ignore()
        self.hide()   # Hide to tray instead of closing
