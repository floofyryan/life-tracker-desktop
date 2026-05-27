"""ui/tabs/log.py"""
import time, threading
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QLineEdit, QComboBox, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, PipIcon, SegBar20, label, h_line
import firebase as fb

class LogTab(QWidget):
    def __init__(self, uid, token, on_action, parent=None):
        super().__init__(parent)
        self._uid = uid; self._token = token; self._on_action = on_action
        self._trackers = []; self._logs = []; self._thesis = {}
        self._build()

    def set_token(self, token): self._token = token

    def _build(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        c = QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay = QVBoxLayout(c); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        # Water
        lay.addWidget(SectionHeader("// HYDRATION LOG"))
        wp = PipPanel(); wr = QHBoxLayout(); wr.setSpacing(4)
        for amt,lbl_t in [(0.25,"250ml"),(0.33,"330ml"),(0.5,"500ml"),(0.75,"750ml"),(1.0,"1 L")]:
            btn=PipButton(lbl_t,GREEN); btn.clicked.connect(lambda _,a=amt:self._log_water(a))
            wr.addWidget(btn)
        wr.addStretch(); wp.layout().addLayout(wr); lay.addWidget(wp)

        # Sleep
        lay.addWidget(SectionHeader("// SLEEP LOG"))
        sp = PipPanel(); sr = QHBoxLayout(); sr.setSpacing(8)
        sr.addWidget(label("HOURS SLEPT:", TEXT_DIM, 10))
        self._sleep_entry = QLineEdit("7.0"); self._sleep_entry.setFixedWidth(70)
        sr.addWidget(self._sleep_entry)
        btn_s = PipButton("LOG SLEEP", GREEN); btn_s.clicked.connect(self._log_sleep)
        sr.addWidget(btn_s); sr.addStretch(); sp.layout().addLayout(sr); lay.addWidget(sp)

        # Weight
        lay.addWidget(SectionHeader("// WEIGHT LOG"))
        wtp = PipPanel(); wtr = QHBoxLayout(); wtr.setSpacing(8)
        wtr.addWidget(label("WEIGHT:", TEXT_DIM, 10))
        self._weight_entry = QLineEdit(); self._weight_entry.setFixedWidth(80)
        self._weight_entry.setPlaceholderText("e.g. 175")
        wtr.addWidget(self._weight_entry)
        self._weight_unit = QComboBox()
        self._weight_unit.addItems(["lbs","kg"]); self._weight_unit.setFixedWidth(60)
        wtr.addWidget(self._weight_unit)
        btn_w = PipButton("LOG WEIGHT", AMBER); btn_w.clicked.connect(self._log_weight)
        wtr.addWidget(btn_w); wtr.addStretch(); wtp.layout().addLayout(wtr); lay.addWidget(wtp)

        # Morning energy
        lay.addWidget(SectionHeader("// MORNING STATUS CHECK"))
        self._morning_panel = PipPanel(border_color=AMBER)
        self._morning_done_lbl = label("", GREEN, 11)
        self._morning_done_lbl.setWordWrap(True)
        self._morning_panel.layout().addWidget(self._morning_done_lbl)
        self._morning_done_lbl.hide()
        self._morning_prompt = QWidget()
        self._morning_prompt.setStyleSheet("background:transparent;")
        ml = QVBoxLayout(self._morning_prompt); ml.setContentsMargins(0,0,0,0); ml.setSpacing(6)
        ml.addWidget(label("HOW DO YOU FEEL ON WAKING? (AFFECTS PERCEPTION)", GREEN_DIM, 9))
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        for n,lbl_t in [(1,"ROUGH"),(2,"TIRED"),(3,"OK"),(4,"GOOD"),(5,"GREAT")]:
            col=RED if n<=2 else AMBER if n==3 else GREEN
            btn=PipButton(f"{n}\n{lbl_t}",col); btn.setFixedWidth(52)
            btn.clicked.connect(lambda _,v=n:self._log_morning(v))
            btn_row.addWidget(btn)
        btn_row.addStretch(); ml.addLayout(btn_row)
        self._morning_panel.layout().addWidget(self._morning_prompt)
        lay.addWidget(self._morning_panel)

        # Evening check-in (only shown after 7pm)
        lay.addWidget(SectionHeader("// EVENING STATUS CHECK"))
        self._evening_panel = PipPanel(border_color=GREEN_DIM)
        self._evening_done_lbl = label("", GREEN, 11)
        self._evening_done_lbl.setWordWrap(True)
        self._evening_panel.layout().addWidget(self._evening_done_lbl)
        self._evening_done_lbl.hide()
        self._evening_prompt = QWidget()
        self._evening_prompt.setStyleSheet("background:transparent;")
        el = QVBoxLayout(self._evening_prompt)
        el.setContentsMargins(0, 0, 0, 0); el.setSpacing(6)
        el.addWidget(label("HOW WAS YOUR DAY?", GREEN_DIM, 9))
        ebtn_row = QHBoxLayout(); ebtn_row.setSpacing(4)
        for n, lbl_t in [(1, "ROUGH"), (2, "TIRED"), (3, "OK"), (4, "GOOD"), (5, "GREAT")]:
            col = RED if n <= 2 else AMBER if n == 3 else GREEN
            btn = PipButton(f"{n}\n{lbl_t}", col); btn.setFixedWidth(52)
            btn.clicked.connect(lambda _, v=n: self._log_evening(v))
            ebtn_row.addWidget(btn)
        ebtn_row.addStretch(); el.addLayout(ebtn_row)
        self._evening_panel.layout().addWidget(self._evening_prompt)
        lay.addWidget(self._evening_panel)

        # Custom trackers
        lay.addWidget(SectionHeader("// CUSTOM TRACKERS"))
        self._tc_panel = PipPanel()
        self._tc_lbl = label("NO CUSTOM TRACKERS -- CONFIGURE IN APP", TEXT_MUTED, 10)
        self._tc_panel.layout().addWidget(self._tc_lbl)
        lay.addWidget(self._tc_panel)

        # Manual
        lay.addWidget(SectionHeader("// MANUAL ENTRY"))
        mp = PipPanel(); mr = QHBoxLayout(); mr.setSpacing(8)
        self._man_name = QLineEdit(); self._man_name.setPlaceholderText("tracker name")
        self._man_name.setFixedWidth(120)
        self._man_val  = QLineEdit("1"); self._man_val.setFixedWidth(60)
        btn_m = PipButton("LOG", GREEN); btn_m.clicked.connect(self._log_manual)
        mr.addWidget(self._man_name); mr.addWidget(self._man_val)
        mr.addWidget(btn_m); mr.addStretch(); mp.layout().addLayout(mr); lay.addWidget(mp)

        self._fb_lbl = label("", GREEN, 10); lay.addWidget(self._fb_lbl)
        lay.addStretch(); scroll.setWidget(c)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def update_data(self, data):
        self._trackers = data.get("trackers",[])
        self._logs     = data.get("logs",[])
        self._thesis   = data.get("thesis",{})
        self._rebuild_trackers()
        self._update_morning()
        self._update_evening()

    def _update_morning(self):
        today = fb.today_key()
        el    = self._thesis.get("energyLogs") or []
        entry = next((l for l in el if l.get("date")==today), None)
        logged = entry and entry.get("morning") is not None
        lvl   = entry.get("morning",0) if entry else 0
        lbls  = {1:"ROUGH",2:"TIRED",3:"OK",4:"GOOD",5:"GREAT"}
        self._morning_done_lbl.hide(); self._morning_prompt.hide()
        if logged:
            self._morning_done_lbl.setText(
                f"LOGGED: {lvl}/5 -- {lbls.get(lvl,'')}  (AFFECTS PERCEPTION SCORE)")
            self._morning_done_lbl.show()
        else:
            self._morning_prompt.show()

    def _update_evening(self):
        # Only show the evening panel after 7pm
        if datetime.now().hour < 19:
            self._evening_panel.hide()
            return
        self._evening_panel.show()

        today = fb.today_key()
        el    = self._thesis.get("energyLogs") or []
        entry = next((l for l in el if l.get("date") == today), None)
        logged = entry and entry.get("evening") is not None and entry.get("evening", 0) != 0
        lvl   = entry.get("evening", 0) if entry else 0
        lbls  = {1: "ROUGH", 2: "TIRED", 3: "OK", 4: "GOOD", 5: "GREAT"}
        self._evening_done_lbl.hide(); self._evening_prompt.hide()
        if logged:
            col = RED if lvl <= 2 else AMBER if lvl == 3 else GREEN
            self._evening_done_lbl.setStyleSheet(
                f"color:{col};font-size:11px;background:transparent;")
            self._evening_done_lbl.setText(
                f"EVENING LOGGED: {lvl}/5 -- {lbls.get(lvl, '')}")
            self._evening_done_lbl.show()
        else:
            self._evening_prompt.show()

    def _rebuild_trackers(self):
        # Remove old tracker buttons
        lay = self._tc_panel.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        totals = fb.tracker_totals(self._logs)
        if not self._trackers:
            lay.addWidget(label("NO CUSTOM TRACKERS -- CONFIGURE IN APP", TEXT_MUTED, 10))
            return

        row_w = None
        for i, t in enumerate(self._trackers):
            if i % 3 == 0:
                row_w = QWidget(); row_w.setStyleSheet("background:transparent;")
                rlay  = QHBoxLayout(row_w); rlay.setContentsMargins(0,0,0,0); rlay.setSpacing(4)
                lay.addWidget(row_w)
            name   = str(t.get("name",""))
            key    = name.lower().strip()
            val    = totals.get(key,0)
            is_tog = bool(t.get("isToggle",False))
            is_int = bool(t.get("isInteger",False))
            unit   = str(t.get("unit",""))
            if is_tog:  display=("ON" if val>0 else "OFF"); col=GREEN if val>0 else GREEN_DIM
            elif is_int: display=str(int(val)); col=GREEN
            else:        display=f"{val:.1f}"; col=GREEN
            btn = PipButton(f"{name[:8].upper()}\n{display}{unit[:3]}", col)
            btn.setFixedWidth(88)
            btn.clicked.connect(lambda _,n=name,tog=is_tog,v=val:self._log_tracker(n,tog,v))
            row_w.layout().addWidget(btn)
        if row_w: row_w.layout().addStretch()

    def _feedback(self, msg, color=GREEN):
        self._fb_lbl.setText(msg)
        self._fb_lbl.setStyleSheet(f"color:{color};font-size:10px;background:transparent;")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self._fb_lbl.setText(""))

    def _log_water(self, amt):
        def run():
            fb.log_activity(self._uid, self._token, "water", amt, "L")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(f"+{amt}L WATER LOGGED", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_sleep(self):
        try: hours = float(self._sleep_entry.text())
        except: self._feedback("! ENTER VALID HOURS", RED); return
        def run():
            fb.log_activity(self._uid, self._token, "sleep", hours, "h")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(f"{hours}H SLEEP LOGGED", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_weight(self):
        try: wt = float(self._weight_entry.text())
        except: self._feedback("! ENTER VALID WEIGHT", RED); return
        unit = self._weight_unit.currentText()
        def run():
            ts = int(time.time()*1000)
            fb.fs_add(f"users/{self._uid}/logs",
                      {"tracker":"weight","value":str(wt),"unit":unit,
                       "type":"weight","ts":ts,"timestamp":ts}, self._token)
            kg = wt if unit=="kg" else round(wt/2.20462, 3)
            fb.fs_set_field(f"users/{self._uid}/daily/{fb.today_key()}",
                            {"weightKg": kg}, self._token)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(f"WEIGHT LOGGED: {wt}{unit}", AMBER))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_morning(self, level):
        def run():
            thesis = dict(self._thesis)
            logs   = list(thesis.get("energyLogs") or [])
            today  = fb.today_key()
            ex = next((l for l in logs if l.get("date")==today), None)
            if ex: ex["morning"]=level
            else:  logs.append({"date":today,"morning":level,"evening":0,"mood":0,"sleepH":None})
            thesis["energyLogs"]=logs
            fb.save_thesis(self._uid, self._token, thesis)
            lbls={1:"ROUGH",2:"TIRED",3:"OK",4:"GOOD",5:"GREAT"}
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(
                f"MORNING ENERGY: {level}/5 -- {lbls.get(level,'')}", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_evening(self, level):
        def run():
            thesis = dict(self._thesis)
            logs   = list(thesis.get("energyLogs") or [])
            today  = fb.today_key()
            ex = next((l for l in logs if l.get("date") == today), None)
            if ex:
                ex["evening"] = level
            else:
                logs.append({"date": today, "morning": 0, "evening": level, "mood": 0, "sleepH": None})
            thesis["energyLogs"] = logs
            fb.save_thesis(self._uid, self._token, thesis)
            lbls = {1: "ROUGH", 2: "TIRED", 3: "OK", 4: "GOOD", 5: "GREAT"}
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(
                f"EVENING ENERGY: {level}/5 -- {lbls.get(level, '')}", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_tracker(self, name, is_tog, cur_val):
        def run():
            val = -cur_val if (is_tog and cur_val>0) else 1.0
            fb.log_activity(self._uid, self._token, name, val)
            lbl_t = ("OFF" if val<0 else "ON") if is_tog else f"+{val:.0f}"
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(f"{name.upper()}: {lbl_t}", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()

    def _log_manual(self):
        name = self._man_name.text().strip()
        try: val = float(self._man_val.text())
        except: self._feedback("! ENTER VALID NUMBER", RED); return
        if not name: self._feedback("! ENTER TRACKER NAME", RED); return
        def run():
            fb.log_activity(self._uid, self._token, name, val)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._feedback(
                f"{name.upper()}: +{val:.1f} LOGGED", GREEN))
            QTimer.singleShot(0, self._on_action)
        threading.Thread(target=run, daemon=True).start()
