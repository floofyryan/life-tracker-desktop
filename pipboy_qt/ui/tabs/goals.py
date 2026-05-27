"""ui/tabs/goals.py"""
import threading, uuid
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLineEdit
from PyQt6.QtCore import Qt, QTimer
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, SegBar20, GlowLabel, MarqueeLabel, label
import firebase as fb

class GoalsTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid=uid; self._token=token; self._life_goals=[]; self._deadlines=[]
        self._build()

    def _build(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        c=QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        lay.addWidget(SectionHeader("// LIFE GOALS"))
        self._lg_panel=PipPanel(); lay.addWidget(self._lg_panel)

        lay.addWidget(SectionHeader("// ADD LIFE GOAL"))
        ap=PipPanel()
        self._lg_title=QLineEdit(); self._lg_title.setPlaceholderText("goal title...")
        self._lg_desc=QLineEdit(); self._lg_desc.setPlaceholderText("description (optional)...")
        add_btn=PipButton("ADD LIFE GOAL",GREEN); add_btn.clicked.connect(self._add_goal)
        ap.layout().addWidget(self._lg_title); ap.layout().addWidget(self._lg_desc)
        ap.layout().addWidget(add_btn); lay.addWidget(ap)

        lay.addWidget(SectionHeader("// UPCOMING DEADLINES"))
        self._dl_panel=PipPanel(); lay.addWidget(self._dl_panel)

        lay.addWidget(SectionHeader("// ADD DEADLINE"))
        dp=PipPanel()
        dr=QHBoxLayout(); dr.setSpacing(8)
        self._dl_title=QLineEdit(); self._dl_title.setPlaceholderText("deadline title...")
        self._dl_date=QLineEdit(fb.today_key()); self._dl_date.setFixedWidth(110)
        add_dl=PipButton("ADD DEADLINE",AMBER); add_dl.clicked.connect(self._add_deadline)
        dr.addWidget(self._dl_title); dr.addWidget(self._dl_date); dr.addWidget(add_dl)
        dp.layout().addLayout(dr); lay.addWidget(dp)

        self._fb_lbl=label("",GREEN,10); lay.addWidget(self._fb_lbl)
        lay.addStretch(); scroll.setWidget(c)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def update_data(self, data):
        self._life_goals=data.get("life_goals",[]); self._deadlines=data.get("deadlines",[])
        self._render_goals(); self._render_deadlines()

    def _render_goals(self):
        lay=self._lg_panel.layout()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not self._life_goals:
            lay.addWidget(label("NO LIFE GOALS SET",TEXT_MUTED,10)); return
        for g in self._life_goals:
            pct=int(g.get("progress",0) or 0); done=bool(g.get("completed",False))
            col=GREEN if done else AMBER
            cell=QWidget(); cell.setStyleSheet(f"background:{SURF};border:1px solid {SURF_MID};")
            cl=QVBoxLayout(cell); cl.setContentsMargins(8,6,8,6); cl.setSpacing(3)
            hr=QHBoxLayout()
            title=str(g.get("title",""))
            if len(title)>24:
                ml=MarqueeLabel(title.upper(),col,10); ml.setFixedHeight(18)
                hr.addWidget(ml)
            else:
                hr.addWidget(GlowLabel(title.upper(),col,11,bold=True))
            hr.addStretch(); hr.addWidget(GlowLabel(f"{pct}%",col,12,bold=True))
            cl.addLayout(hr)
            bar=SegBar20(pct,100,col); cl.addWidget(bar)
            desc=str(g.get("description",""))
            if desc: cl.addWidget(label(desc[:50],TEXT_MUTED,9))
            td=g.get("targetDate","")
            if td:
                try:
                    from datetime import datetime
                    days=(datetime.strptime(td,"%Y-%m-%d")-datetime.now()).days
                    dc=RED if days<30 else AMBER if days<90 else GREEN_DIM
                    cl.addWidget(label(f"TARGET: {td}  ({days}D)",dc,8))
                except: pass
            lay.addWidget(cell)

    def _render_deadlines(self):
        lay=self._dl_panel.layout()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        dls=sorted(self._deadlines,key=lambda d:d.get("date",""))
        if not dls:
            lay.addWidget(label("NO DEADLINES SET",TEXT_MUTED,10)); return
        for d in dls:
            title=str(d.get("title","")); date=str(d.get("date",""))
            try:
                from datetime import datetime
                days=(datetime.strptime(date,"%Y-%m-%d")-datetime.now()).days
                dc=RED if days<=7 else AMBER if days<=30 else GREEN_DIM
                days_txt=f"{days}D" if days>=0 else "OVERDUE"
            except: dc=GREEN_DIM; days_txt=""
            cell=QWidget(); cell.setStyleSheet(f"background:{SURF};border:1px solid {SURF_MID};")
            rl=QHBoxLayout(cell); rl.setContentsMargins(8,6,8,6); rl.setSpacing(8)
            lf=QVBoxLayout()
            if len(title)>26:
                ml=MarqueeLabel(title.upper(),dc,10); ml.setFixedHeight(18); lf.addWidget(ml)
            else:
                lf.addWidget(GlowLabel(title.upper(),dc,11,bold=True))
            lf.addWidget(label(date,TEXT_MUTED,9)); rl.addLayout(lf); rl.addStretch()
            badge=QWidget(); badge.setStyleSheet(f"background:{SURF_MID};")
            bl=QHBoxLayout(badge); bl.setContentsMargins(8,4,8,4)
            bl.addWidget(GlowLabel(days_txt,dc,12,bold=True)); rl.addWidget(badge)
            lay.addWidget(cell)

    def _feedback(self,msg,color=GREEN):
        self._fb_lbl.setText(msg)
        self._fb_lbl.setStyleSheet(f"color:{color};font-size:10px;background:transparent;")
        QTimer.singleShot(3000,lambda:self._fb_lbl.setText(""))

    def _add_goal(self):
        title=self._lg_title.text().strip()
        if not title: self._feedback("! ENTER A GOAL TITLE",RED); return
        desc=self._lg_desc.text().strip()
        def run():
            goals=list(self._life_goals)
            goals.append({"id":str(uuid.uuid4()),"title":title,"description":desc,
                          "targetDate":"","progress":0,"completed":False,"subTasks":[]})
            fb.save_life_goals(self._uid,self._token,goals)
            QTimer.singleShot(0,lambda:self._lg_title.clear())
            QTimer.singleShot(0,lambda:self._feedback(f"GOAL ADDED: {title[:30].upper()}",GREEN))
        threading.Thread(target=run,daemon=True).start()

    def _add_deadline(self):
        title=self._dl_title.text().strip(); date=self._dl_date.text().strip()
        if not title: self._feedback("! ENTER A TITLE",RED); return
        def run():
            dls=list(self._deadlines)
            dls.append({"id":str(uuid.uuid4()),"title":title,"date":date,"category":"Thesis"})
            fb.save_deadlines(self._uid,self._token,dls)
            QTimer.singleShot(0,lambda:self._dl_title.clear())
            QTimer.singleShot(0,lambda:self._feedback(f"DEADLINE ADDED: {title[:30].upper()}",AMBER))
        threading.Thread(target=run,daemon=True).start()
