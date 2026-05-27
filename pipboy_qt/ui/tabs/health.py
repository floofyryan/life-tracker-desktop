"""ui/tabs/health.py — HEALTH tab"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import (
    SectionHeader, PipPanel, PipIcon, SegBar20,
    GlowLabel, MarqueeLabel, label, h_line, make_row
)
import firebase as fb


class VitalCard(QWidget):
    def __init__(self, key, title, icon_kind, color, parent=None):
        super().__init__(parent)
        self._color = color
        self.setStyleSheet(f"background: {SURF}; border: 1px solid {SURF_MID};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        # Header row: icon + title
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        self._icon = PipIcon(icon_kind, color, 18, self)
        hdr.addWidget(self._icon)
        hdr.addWidget(label(title, TEXT_DIM, 9))
        hdr.addStretch()
        lay.addLayout(hdr)

        # Big value
        self._val_lbl = GlowLabel("--", color, 20, bold=True, parent=self)
        lay.addWidget(self._val_lbl)

        # Seg bar
        self._bar = SegBar20(0, 100, color, self)
        lay.addWidget(self._bar)

    def set_value(self, display_text, value, max_val, warn=False):
        col = RED if warn else self._color
        self._val_lbl.setColor(col)
        self._val_lbl.setText(display_text)
        self._icon.set_color(col)
        self._bar.set_value(value, max_val, col)


class HealthTab(QWidget):
    def __init__(self, data, token, parent=None):
        super().__init__(parent)
        self._data  = data
        self._token = token
        self._build()

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        content.setStyleSheet(f"background: {BLACK};")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        # Condition summary card
        SH = SectionHeader("// CONDITION")
        lay.addWidget(SH)
        cond_panel = PipPanel(border_color=GREEN_DIM)
        cond_row = QHBoxLayout()
        cond_row.setSpacing(12)
        self._cond_score = GlowLabel("--", GREEN, 26, bold=True)
        cond_row.addWidget(self._cond_score)
        right = QVBoxLayout()
        right.setSpacing(4)
        self._cond_label = GlowLabel("INITIALIZING", GREEN, 12, bold=True)
        right.addWidget(self._cond_label)
        self._cond_bar   = SegBar20(0, 100, GREEN)
        right.addWidget(self._cond_bar)
        cond_row.addLayout(right)
        cond_row.addStretch()
        cond_panel.layout().addLayout(cond_row)
        lay.addWidget(cond_panel)

        # Vitals grid 2x2
        lay.addWidget(SectionHeader("// VITALS"))
        grid = QGridLayout()
        grid.setSpacing(6)
        self._vitals = {}
        specs = [
            ("water",  "HYDRATION", "water",  GREEN,  0, 0),
            ("sleep",  "SLEEP",     "sleep",  AMBER,  0, 1),
            ("steps",  "STEPS",     "steps",  GREEN,  1, 0),
            ("active", "ACTIVE",    "active", GREEN,  1, 1),
        ]
        for key, title, icon, color, row, col in specs:
            card = VitalCard(key, title, icon, color)
            grid.addWidget(card, row, col)
            self._vitals[key] = card
        lay.addLayout(grid)

        # Extra vitals row
        extra_row = QHBoxLayout()
        extra_row.setSpacing(6)
        for key, title, icon in [("hr","HEART RATE","foc"),("weight","WEIGHT","weight")]:
            card = VitalCard(key, title, icon, GREEN_DIM)
            extra_row.addWidget(card)
            self._vitals[key] = card
        lay.addLayout(extra_row)

        # Custom trackers
        lay.addWidget(SectionHeader("// CUSTOM TRACKERS"))
        self._tc_panel = PipPanel()
        self._tc_grid  = QGridLayout()
        self._tc_grid.setSpacing(6)
        self._tc_panel.layout().addLayout(self._tc_grid)
        lay.addWidget(self._tc_panel)

        lay.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(scroll)

    def update_data(self, data):
        self._data = data
        d = data.get("daily", {})
        g = data.get("goals", {})

        water  = fb.sf(d.get("water"));  wg  = fb.sf(g.get("waterGoalL"), 3.0)
        sleep  = fb.sf(d.get("sleep"));  slg = fb.sf(g.get("sleepGoalH"), 8.0)
        steps  = fb.sf(d.get("steps"));  stg = fb.sf(g.get("stepGoal"),   7500)
        active = fb.sf(d.get("active")); ag  = fb.sf(g.get("activeGoalMin"), 30)
        hr     = fb.sf(d.get("heartRateAvg") or d.get("heartRate"))
        weight = fb.sf(d.get("weightKg") or d.get("weight"))

        cond = int(fb.sf(d.get("condition") or d.get("overall")))
        lbl  = fb.condition_label(cond)
        col  = GREEN if cond >= 65 else AMBER if cond >= 35 else RED
        self._cond_score.setText(str(cond) if cond else "--")
        self._cond_score.setColor(col)
        self._cond_label.setText(lbl)
        self._cond_label.setColor(col)
        self._cond_bar.set_value(cond, 100, col)

        def step_fmt(v):
            return f"{v/1000:.1f}K" if v >= 1000 else str(int(v))

        self._vitals["water"].set_value(f"{water:.1f}L", water, wg, water < wg*0.25)
        self._vitals["sleep"].set_value(f"{sleep:.1f}H", sleep, slg, sleep < 5)
        self._vitals["steps"].set_value(step_fmt(steps), steps, stg, steps < stg*0.25)
        self._vitals["active"].set_value(f"{int(active)}M", active, ag, active < 10)
        self._vitals["hr"].set_value(f"{int(hr)}BPM" if hr else "--", hr, 200)
        self._vitals["weight"].set_value(f"{weight:.1f}kg" if weight else "--", weight, weight or 1)

        # Custom trackers
        trackers = data.get("trackers", [])
        totals   = fb.tracker_totals(data.get("logs", []))

        # Clear and rebuild grid
        while self._tc_grid.count():
            item = self._tc_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not trackers:
            self._tc_panel.layout().addWidget(
                label("NO CUSTOM TRACKERS -- CONFIGURE IN APP", TEXT_MUTED, 10))
            return

        for i, t in enumerate(trackers):
            name   = str(t.get("name",""))
            key    = name.lower().strip()
            val    = totals.get(key, 0)
            is_tog = bool(t.get("isToggle", False))
            is_int = bool(t.get("isInteger", False))
            unit   = str(t.get("unit",""))
            goal   = fb.sf(t.get("goal"))

            if is_tog:
                display = "ON" if val > 0 else "OFF"
                col     = GREEN if val > 0 else GREEN_DIM
            elif is_int:
                display = str(int(val)); col = GREEN
            else:
                display = f"{val:.1f}"; col = GREEN

            cell = QWidget()
            cell.setStyleSheet(f"background: {SURF}; border: 1px solid {SURF_MID};")
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(3)
            cl.addWidget(label(name.upper(), TEXT_DIM, 9))
            cl.addWidget(GlowLabel(f"{display} {unit}", col, 14, bold=True))
            if goal > 0:
                bar = SegBar20(val, goal, col)
                cl.addWidget(bar)
            self._tc_grid.addWidget(cell, i//3, i%3)
