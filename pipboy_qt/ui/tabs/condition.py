"""ui/tabs/condition.py"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QLabel
from PyQt6.QtCore import Qt
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipIcon, SegBar20, GlowLabel, MarqueeLabel, label
import firebase as fb

PILLARS = [
    ("strength",   "STR", "STRENGTH",   "STEPS + ACTIVE",    "Log steps or exercise"),
    ("endurance",  "END", "ENDURANCE",  "HYDRATION + WEIGHT", "Drink water, log weight"),
    ("perception", "PER", "PERCEPTION", "SLEEP + QUALITY",   "Log sleep or energy"),
    ("agility",    "AGI", "AGILITY",    "ACTIVE MINUTES",    "Get 30+ active minutes"),
    ("focus",      "FOC", "FOCUS",      "THESIS + WRITING",  "Log a writing session"),
    ("tasks",      "TSK", "TASKS",      "CARRY WEIGHT",      "Complete or drop tasks"),
]
PILLAR_ICONS = {"strength":"str","endurance":"end","perception":"per",
                "agility":"agi","focus":"foc","tasks":"tsk"}

class ConditionTab(QWidget):
    def __init__(self, data, token, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        content = QWidget(); content.setStyleSheet(f"background:{BLACK};")
        lay = QVBoxLayout(content); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        lay.addWidget(SectionHeader("// OVERALL CONDITION"))
        top = PipPanel(border_color=GREEN_DIM)
        row = QHBoxLayout(); row.setSpacing(12)
        self._score = GlowLabel("--", GREEN, 26, bold=True)
        row.addWidget(self._score)
        rr = QVBoxLayout(); rr.setSpacing(4)
        self._lbl    = GlowLabel("INITIALIZING", GREEN, 12, bold=True)
        self._streak = label("", AMBER, 10)
        self._bar    = SegBar20(0, 100, GREEN)
        rr.addWidget(self._lbl); rr.addWidget(self._streak); rr.addWidget(self._bar)
        row.addLayout(rr); row.addStretch()
        top.layout().addLayout(row); lay.addWidget(top)

        lay.addWidget(SectionHeader("// S.P.E.C.I.A.L."))
        grid = QGridLayout(); grid.setSpacing(6)
        self._pillars = {}
        for i,(key,abbr,name,sub,action) in enumerate(PILLARS):
            cell = QWidget()
            cell.setStyleSheet(f"background:{SURF};border:1px solid {SURF_MID};")
            cl = QVBoxLayout(cell); cl.setContentsMargins(8,6,8,6); cl.setSpacing(3)
            hdr = QHBoxLayout(); hdr.setSpacing(4)
            hdr.addWidget(PipIcon(PILLAR_ICONS[key], GREEN_DIM, 16))
            hdr.addWidget(label(abbr, TEXT_DIM, 9))
            hdr.addStretch()
            sv = GlowLabel("--", GREEN, 14, bold=True)
            hdr.addWidget(sv)
            cl.addLayout(hdr)
            bar = SegBar20(0, 100, GREEN)
            cl.addWidget(bar)
            cl.addWidget(label(sub, TEXT_MUTED, 8))
            al = MarqueeLabel("", AMBER, 9)
            cl.addWidget(al)
            grid.addWidget(cell, i//2, i%2)
            self._pillars[key] = (sv, bar, al)
        lay.addLayout(grid)

        lay.addWidget(SectionHeader("// VAULT-TEC ADVISORY"))
        adv = PipPanel()
        self._advisory = label("AWAITING BIOMETRIC DATA...", GREEN_DIM, 10)
        self._advisory.setWordWrap(True)
        adv.layout().addWidget(self._advisory)
        lay.addWidget(adv); lay.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def update_data(self, data):
        d = data.get("daily",{})
        overall = int(fb.sf(d.get("condition") or d.get("overall")))
        col = GREEN if overall>=65 else AMBER if overall>=35 else RED
        self._score.setText(str(overall) if overall else "--"); self._score.setColor(col)
        self._lbl.setText(fb.condition_label(overall)); self._lbl.setColor(col)
        self._bar.set_value(overall, 100, col)
        streak = d.get("streakBonus")
        self._streak.setText(f"LUCK BONUS: +{streak}%" if streak else "")
        weak=[]
        for key,abbr,name,sub,action in PILLARS:
            score=int(fb.sf(d.get(key))); pc=GREEN if score>=80 else AMBER if score>=50 else RED
            sv,bar,al=self._pillars[key]
            sv.setText(str(score) if score else "--"); sv.setColor(pc)
            bar.set_value(score,100,pc)
            al.setText(f"-> {action}" if score<70 else ""); al.setColor(AMBER)
            if score<50: weak.append(abbr)
        self._advisory.setText(
            f"! DEFICIENCIES: {', '.join(weak)}. CORRECTIVE ACTION REQUIRED." if weak
            else "ALL SYSTEMS NOMINAL. VAULT-TEC COMMENDS YOUR OPERATIONAL EFFICIENCY.")
        self._advisory.setStyleSheet(
            f"color:{RED if weak else GREEN_DIM};background:transparent;font-size:10px;")
