"""ui/tabs/jobs.py — JOBS pipeline tab."""
import threading
from collections import Counter
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QFrame
)
from PyQt6.QtCore import Qt

from ui.style   import (BLACK, SURF, SURF_MID, GREEN, GREEN_DIM,
                         AMBER, RED, TEXT_DIM, TEXT_MUTED)
from ui.widgets import SectionHeader, PipPanel, PipButton, label


class JobsTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid   = uid
        self._token = token
        self._apps  = []
        self._filter = "ALL"
        self._build()

    def set_token(self, token):
        self._token = token

    def update_data(self, data):
        self._apps = data.get("job_apps", []) or []
        self._render()

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")

        c = QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        # Pipeline stats
        lay.addWidget(SectionHeader("// JOB SEARCH PIPELINE"))
        self._stats_panel = PipPanel(border_color=GREEN_DIM)
        sr = QHBoxLayout(); sr.setSpacing(0)
        self._stat_widgets = {}
        for cat, col in [("APPLIED", GREEN), ("INTERVIEW", AMBER),
                          ("OFFER", GREEN), ("REJECTED", RED)]:
            cell = QWidget(); cell.setStyleSheet("background:transparent;")
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(8, 6, 8, 6); cl.setSpacing(2)
            num = QLabel("0")
            num.setStyleSheet(
                f"color:{col};font-size:18px;font-weight:bold;"
                "font-family:'Courier New';background:transparent;")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(num)
            cl.addWidget(label(cat, TEXT_DIM, 8))
            sr.addWidget(cell)
            if cat != "REJECTED":
                sr.addStretch()
            self._stat_widgets[cat.lower()] = num
        self._stats_panel.layout().addLayout(sr)
        lay.addWidget(self._stats_panel)

        # Filter bar
        fb_w = QWidget(); fb_w.setStyleSheet("background:transparent;")
        fl = QHBoxLayout(fb_w)
        fl.setContentsMargins(0, 4, 0, 4); fl.setSpacing(4)
        self._filter_btns = {}
        for cat in ["ALL", "INDUSTRY", "ACADEMIA", "STARTUP"]:
            btn = PipButton(cat, GREEN_DIM)
            btn.clicked.connect(lambda _, c=cat: self._set_filter(c))
            self._filter_btns[cat] = btn
            fl.addWidget(btn)
        fl.addStretch()
        lay.addWidget(fb_w)

        # Job list
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet("QScrollArea{border:none;}")
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background:{BLACK};")
        self._list_lay = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(3)
        self._list_lay.addStretch()
        self._list_scroll.setWidget(self._list_widget)
        lay.addWidget(self._list_scroll)

        scroll.setWidget(c)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Render ─────────────────────────────────────────────────
    def _render(self):
        apps = self._apps

        # Update pipeline counts
        counts = Counter(str(a.get("status", "")).upper() for a in apps)
        for cat, widget in self._stat_widgets.items():
            widget.setText(str(counts.get(cat.upper(), 0)))

        # Filter
        f = self._filter
        filtered = [a for a in apps
                    if f == "ALL" or str(a.get("sector", "")).upper() == f]

        # Sort: active first, then by applied date desc
        STATUS_ORDER = {"APPLIED": 0, "INTERVIEW": 1, "OFFER": 2,
                        "REJECTED": 3, "": 4}
        filtered.sort(key=lambda a: (
            STATUS_ORDER.get(str(a.get("status", "")).upper(), 4),
            -(a.get("appliedDateTs") or 0)
        ))

        # Clear existing cards (keep the trailing stretch)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not filtered:
            msg = ("NO APPLICATIONS YET" if f == "ALL"
                   else f"NO {f} APPLICATIONS")
            self._list_lay.insertWidget(0, label(msg, TEXT_MUTED, 10))
            return

        for i, a in enumerate(filtered):
            self._list_lay.insertWidget(i, self._make_card(a))

        # Highlight active filter button
        for cat, btn in self._filter_btns.items():
            btn.set_color(GREEN if cat == self._filter else GREEN_DIM)

    def _make_card(self, a):
        status   = str(a.get("status", "")).upper()
        company  = str(a.get("company", ""))
        role     = str(a.get("role", ""))
        sector   = str(a.get("sector", "")).upper()
        applied  = str(a.get("appliedDate", ""))
        interview = str(a.get("interviewDate", ""))

        col = {"APPLIED": GREEN, "INTERVIEW": AMBER,
               "OFFER": GREEN, "REJECTED": TEXT_DIM}.get(status, GREEN_DIM)

        # Days since applied
        days_str = ""
        try:
            d = (datetime.now() - datetime.strptime(applied, "%Y-%m-%d")).days
            days_str = f"{d}D"
        except Exception:
            pass

        card = QWidget()
        card.setStyleSheet(
            f"background:{SURF};border:1px solid {SURF_MID};")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 7, 10, 7); cl.setSpacing(3)

        # Header row
        hr = QHBoxLayout(); hr.setSpacing(6)
        co_lbl = QLabel((company[:20] + "..") if len(company) > 20 else company)
        co_lbl.setStyleSheet(
            f"color:{col};font-size:11px;font-weight:bold;"
            "font-family:'Courier New';background:transparent;")
        hr.addWidget(co_lbl); hr.addStretch()

        badge = QFrame()
        badge.setStyleSheet(f"background:{SURF_MID};border:none;")
        bl = QHBoxLayout(badge); bl.setContentsMargins(6, 2, 6, 2)
        bl.addWidget(label(status or "PENDING", col, 9, bold=True))
        hr.addWidget(badge)
        cl.addLayout(hr)

        # Role
        cl.addWidget(label(role[:34] if role else "ROLE TBD", TEXT_DIM, 10))

        # Meta row
        mr = QHBoxLayout(); mr.setSpacing(10)
        if sector:   mr.addWidget(label(sector, TEXT_MUTED, 8))
        if applied:  mr.addWidget(label(f"APPLIED: {applied}", TEXT_MUTED, 8))
        if days_str: mr.addWidget(label(days_str, TEXT_MUTED, 8))
        mr.addStretch()

        # Interview date
        if interview and status == "INTERVIEW":
            try:
                d = (datetime.strptime(interview, "%Y-%m-%d") - datetime.now()).days
                dc = RED if d <= 3 else AMBER if d <= 7 else GREEN
                mr.addWidget(label(f"INTERVIEW: {interview} ({d}D)", dc, 8, bold=True))
            except Exception:
                mr.addWidget(label(f"INTERVIEW: {interview}", AMBER, 8))

        cl.addLayout(mr)

        # Follow-up nudge
        try:
            days_since = (datetime.now() - datetime.strptime(applied, "%Y-%m-%d")).days
            if status == "APPLIED" and days_since >= 10:
                cl.addWidget(
                    label(f"! {days_since}D SINCE APPLIED -- FOLLOW UP?", AMBER, 8))
        except Exception:
            pass

        return card

    def _set_filter(self, f):
        self._filter = f
        self._render()
