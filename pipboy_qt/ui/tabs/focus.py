"""ui/tabs/focus.py"""
import time, threading
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QScrollArea, QLineEdit, QLabel)
from PyQt6.QtCore import Qt, QTimer
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, SegBar20, GlowLabel, label
import firebase as fb


class FocusTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid     = uid
        self._token   = token
        self._mins    = 25
        self._running = False
        self._elapsed = 0
        self._start_ms= 0
        self._sessions= []
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build()

    def set_token(self, token): self._token = token

    def _build(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        c=QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        # Timer display
        lay.addWidget(SectionHeader("// FOCUS TIMER"))
        tp=PipPanel(border_color=AMBER)
        self._clock=GlowLabel("25:00",AMBER,42,bold=True)
        self._clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.layout().addWidget(self._clock)
        self._task_lbl=label("FOCUS TIMER",GREEN_DIM,10)
        self._task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.layout().addWidget(self._task_lbl)
        self._prog_bar=SegBar20(0,100,GREEN); tp.layout().addWidget(self._prog_bar)
        self._sess_count=label("0 SESSIONS COMPLETED TODAY",TEXT_MUTED,9)
        self._sess_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tp.layout().addWidget(self._sess_count)
        lay.addWidget(tp)

        # Working on
        lay.addWidget(SectionHeader("// WORKING ON"))
        wp=PipPanel()
        self._label_entry=QLineEdit("THESIS WRITING")
        wp.layout().addWidget(self._label_entry); lay.addWidget(wp)

        # Duration
        lay.addWidget(SectionHeader("// DURATION"))
        dp=PipPanel(); dr=QHBoxLayout(); dr.setSpacing(4)
        for m in [15,25,45,60]:
            btn=PipButton(f"{m}M",AMBER); btn.clicked.connect(lambda _,x=m:self._set_mins(x))
            dr.addWidget(btn)
        dr.addSpacing(8)
        minus=PipButton("-",GREEN_DIM); minus.clicked.connect(lambda:self._set_mins(max(1,self._mins-5)))
        dr.addWidget(minus)
        self._mins_lbl=GlowLabel("25",GREEN,14,bold=True); dr.addWidget(self._mins_lbl)
        plus=PipButton("+",GREEN_DIM); plus.clicked.connect(lambda:self._set_mins(self._mins+5))
        dr.addWidget(plus); dr.addStretch()
        dp.layout().addLayout(dr); lay.addWidget(dp)

        # Controls
        lay.addWidget(SectionHeader("// CONTROLS"))
        cp=PipPanel(); cr=QHBoxLayout(); cr.setSpacing(6)
        self._toggle_btn=PipButton("START TIMER",GREEN)
        self._toggle_btn.clicked.connect(self._toggle)
        cr.addWidget(self._toggle_btn)
        reset_btn=PipButton("RESET",RED); reset_btn.clicked.connect(self._reset)
        cr.addWidget(reset_btn); cr.addStretch()
        cp.layout().addLayout(cr); lay.addWidget(cp)

        # Session log
        lay.addWidget(SectionHeader("// SESSION LOG TODAY"))
        self._log_panel=PipPanel()
        self._log_panel.layout().addWidget(label("NO SESSIONS YET",TEXT_MUTED,10))
        lay.addWidget(self._log_panel); lay.addStretch()
        scroll.setWidget(c)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def _set_mins(self, m):
        self._mins=m; self._mins_lbl.setText(str(m)); self._reset()

    def _toggle(self):
        if self._running:
            self._running=False; self._timer.stop()
            self._elapsed=int((time.time()*1000-self._start_ms)/1000)
            self._toggle_btn.setText("RESUME TIMER"); self._toggle_btn.set_color(GREEN)
        else:
            self._start_ms=int(time.time()*1000)-(self._elapsed*1000)
            self._running=True; self._timer.start(1000)
            lbl=self._label_entry.text() or "FOCUS"
            self._task_lbl.setText(lbl.upper())
            self._task_lbl.setStyleSheet(f"color:{GREEN};font-size:10px;background:transparent;text-align:center;")
            self._toggle_btn.setText("PAUSE TIMER"); self._toggle_btn.set_color(AMBER)

    def _reset(self):
        self._running=False; self._timer.stop(); self._elapsed=0
        self._clock.setText(f"{self._mins:02d}:00"); self._clock.setColor(AMBER)
        self._toggle_btn.setText("START TIMER"); self._toggle_btn.set_color(GREEN)
        self._prog_bar.set_value(0,100,GREEN)

    def _tick(self):
        if not self._running: return
        limit=self._mins*60
        elapsed=int((time.time()*1000-self._start_ms)/1000)
        left=max(0,limit-elapsed)
        m,s=divmod(left,60)
        self._clock.setText(f"{m:02d}:{s:02d}")
        self._clock.setColor(GREEN)
        self._prog_bar.set_value(min(elapsed,limit),limit,GREEN)
        if left<=0:
            self._running=False; self._timer.stop()
            self._clock.setText("DONE!"); self._clock.setColor(AMBER)
            self._prog_bar.set_value(1,1,AMBER)
            self._toggle_btn.setText("START TIMER"); self._toggle_btn.set_color(GREEN)
            lbl=self._label_entry.text() or "FOCUS"
            self._sessions.append({"label":lbl,"mins":self._mins,
                                   "time":__import__("datetime").datetime.now().strftime("%H:%M")})
            self._elapsed=0
            n=len(self._sessions)
            self._sess_count.setText(f"{n} SESSION{'S' if n!=1 else ''} COMPLETED TODAY")
            self._sess_count.setStyleSheet(f"color:{AMBER};font-size:9px;background:transparent;")
            self._rebuild_log()
            # Save to Firebase
            end_ms=int(time.time()*1000); start_ms=end_ms-self._mins*60*1000
            threading.Thread(target=fb.save_focus_session,
                             args=(self._uid,self._token,start_ms,end_ms,self._mins,lbl),
                             daemon=True).start()

    def _rebuild_log(self):
        lay=self._log_panel.layout()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for s in self._sessions[-6:]:
            row=QWidget(); row.setStyleSheet("background:transparent;")
            rl=QHBoxLayout(row); rl.setContentsMargins(0,2,0,2)
            rl.addWidget(label(f"{s['time']} -- {s['label'][:20]}",GREEN_DIM,10))
            rl.addStretch(); rl.addWidget(label(f"{s['mins']}M",GREEN,10))
            lay.addWidget(row)
