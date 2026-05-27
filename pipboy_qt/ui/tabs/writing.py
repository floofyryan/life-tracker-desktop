"""ui/tabs/writing.py"""
import math, threading
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                               QSpinBox, QButtonGroup, QRadioButton)
from PyQt6.QtCore import Qt, QTimer
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, SegBar20, GlowLabel, label
import firebase as fb

class WritingTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid=uid; self._token=token; self._thesis={}; self._todos=[]
        self._build()

    def _build(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        c=QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        # Academic rank
        lay.addWidget(SectionHeader("// ACADEMIC RANK"))
        rp=PipPanel()
        rr=QHBoxLayout(); rr.setSpacing(12)
        lf=QWidget(); lf.setStyleSheet(f"background:{SURF_MID};")
        ll=QVBoxLayout(lf); ll.setContentsMargins(8,6,8,6)
        self._rank_lv=GlowLabel("LV1",GREEN,18,bold=True); ll.addWidget(self._rank_lv)
        rr.addWidget(lf)
        rc=QVBoxLayout(); rc.setSpacing(3)
        self._rank_title=GlowLabel("FRESHMAN RESEARCHER",GREEN,11,bold=True)
        self._rank_xp=label("XP: 0 / 100",GREEN_DIM,10)
        self._rank_bar=SegBar20(0,100,GREEN)
        rc.addWidget(self._rank_title); rc.addWidget(self._rank_xp); rc.addWidget(self._rank_bar)
        rr.addLayout(rc); rr.addStretch(); rp.layout().addLayout(rr); lay.addWidget(rp)

        # Defence countdown
        lay.addWidget(SectionHeader("// DEFENCE COUNTDOWN"))
        dp=PipPanel()
        dr=QHBoxLayout(); dr.setSpacing(12)
        self._def_days=GlowLabel("--",GREEN,28,bold=True)
        dr.addWidget(self._def_days)
        dc=QVBoxLayout(); dc.setSpacing(2)
        dc.addWidget(label("DAYS REMAINING",GREEN_DIM,10))
        self._def_date=label("",TEXT_MUTED,9); dc.addWidget(self._def_date)
        dr.addLayout(dc); dr.addStretch(); dp.layout().addLayout(dr)
        self._def_bar=SegBar20(0,100,RED); dp.layout().addWidget(self._def_bar)
        lay.addWidget(dp)

        # Chapters
        lay.addWidget(SectionHeader("// CHAPTER PROGRESS"))
        self._ch_panel=PipPanel(); lay.addWidget(self._ch_panel)

        # Log session
        lay.addWidget(SectionHeader("// LOG WRITING SESSION"))
        sp=PipPanel()
        wr=QHBoxLayout(); wr.setSpacing(8)
        wr.addWidget(label("WORDS WRITTEN:",TEXT_DIM,10))
        self._sess_words=QSpinBox(); self._sess_words.setRange(0,50000)
        self._sess_words.setValue(500); self._sess_words.setSingleStep(100)
        self._sess_words.setFixedWidth(90)
        wr.addWidget(self._sess_words); wr.addStretch(); sp.layout().addLayout(wr)
        qr=QHBoxLayout(); qr.setSpacing(6); qr.addWidget(label("QUALITY:",TEXT_DIM,10))
        self._qual_grp=QButtonGroup(sp)
        for n,l in [(1,"ROUGH"),(2,"SLOW"),(3,"OK"),(4,"GOOD"),(5,"GREAT")]:
            col=RED if n<=2 else AMBER if n==3 else GREEN
            rb=QRadioButton(f"{n} {l}"); rb.setStyleSheet(
                f"color:{col};font-size:9px;background:transparent;")
            self._qual_grp.addButton(rb,n); qr.addWidget(rb)
            if n==3: rb.setChecked(True)
        qr.addStretch(); sp.layout().addLayout(qr)
        save_btn=PipButton("SAVE WRITING SESSION",GREEN)
        save_btn.clicked.connect(self._save_session); sp.layout().addWidget(save_btn)
        self._sess_fb=label("",GREEN,10); sp.layout().addWidget(self._sess_fb)
        lay.addWidget(sp)

        # Overview
        lay.addWidget(SectionHeader("// THESIS OVERVIEW"))
        self._ov_panel=PipPanel(); lay.addWidget(self._ov_panel)
        lay.addStretch(); scroll.setWidget(c)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def update_data(self, data):
        self._thesis=data.get("thesis",{}); self._todos=data.get("todos",[])
        self._render()

    def _render(self):
        thesis=self._thesis; todos=self._todos; today=fb.today_key()
        chapters=thesis.get("chapters") or []

        # XP / level
        writing_xp=sum(int(l.get("words",0) or 0) for l in (thesis.get("writingLogs") or []))
        task_xp=sum(int(t.get("weight",1) or 1)*100 for t in todos
                    if t.get("done") and str(t.get("category","")).upper() in ("THESIS","THESIS_ADMIN"))
        total_xp=writing_xp+task_xp
        level,xp_cur,xp_next,rank=fb.academic_rank(total_xp)
        self._rank_lv.setText(f"LV{level}")
        self._rank_title.setText(rank)
        self._rank_xp.setText(f"XP: {total_xp-xp_cur:,} / {xp_next-xp_cur:,}")
        self._rank_bar.set_value(total_xp-xp_cur,max(1,xp_next-xp_cur),GREEN)

        # Defence
        defence=str(thesis.get("defenceDate") or "").strip()
        if defence:
            try:
                from datetime import datetime
                days=(datetime.strptime(defence,"%Y-%m-%d")-datetime.now()).days
                dc=RED if days<14 else AMBER if days<60 else GREEN
                self._def_days.setText(str(days)); self._def_days.setColor(dc)
                self._def_date.setText(defence)
                pct=min(1.0,max(0.0,1.0-(days/90.0)))
                self._def_bar.set_value(int(pct*100),100,dc)
            except: self._def_days.setText("--")
        else:
            self._def_days.setText("--"); self._def_date.setText("NOT SET -- CONFIGURE IN APP")

        # Chapters
        lay=self._ch_panel.layout()
        while lay.count():
            item=lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not chapters:
            lay.addWidget(label("NO CHAPTERS -- CONFIGURE IN APP",TEXT_MUTED,10))
        else:
            for i,ch in enumerate(chapters):
                cur_w=int(ch.get("currentWords",0) or 0)
                tgt_w=int(ch.get("targetWords",0) or 1)
                pct=int(ch.get("pct",0) or 0) or round(cur_w/max(1,tgt_w)*100)
                col=GREEN if pct>=100 else AMBER
                cell=QWidget(); cell.setStyleSheet(f"background:{SURF};border:1px solid {SURF_MID};")
                cl=QVBoxLayout(cell); cl.setContentsMargins(8,6,8,6); cl.setSpacing(3)
                hr=QHBoxLayout()
                hr.addWidget(label(f"CH{i+1}: {ch.get('name','').upper()}",GREEN,11))
                hr.addStretch()
                hr.addWidget(GlowLabel(f"{pct}%",col,12,bold=True))
                cl.addLayout(hr)
                cl.addWidget(label(f"{cur_w:,} WORDS / {tgt_w:,} TARGET",TEXT_DIM,9))
                bar=SegBar20(pct,100,col); cl.addWidget(bar)
                lay.addWidget(cell)

        # Overview
        lay2=self._ov_panel.layout()
        while lay2.count():
            item=lay2.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        total_w=sum(int(c.get("currentWords",0) or 0) for c in chapters)
        target_w=sum(int(c.get("targetWords",0) or 0) for c in chapters)
        today_w=next((int(l.get("words",0) or 0) for l in (thesis.get("writingLogs") or [])
                      if l.get("date")==today),0)
        pct_ov=round(total_w/max(1,target_w)*100) if target_w else 0
        ov_col=GREEN if pct_ov>=100 else AMBER if pct_ov>=50 else RED
        for lbl_t,val_t,col in [
            ("TOTAL WORDS",f"{total_w:,}",GREEN),
            ("TARGET WORDS",f"{target_w:,}",GREEN),
            ("OVERALL",f"{pct_ov}%",ov_col),
            ("WORDS TODAY",f"{today_w:,}" if today_w else "--",GREEN),
            ("TOTAL XP",f"{total_xp:,}",AMBER),
        ]:
            row=QWidget(); row.setStyleSheet("background:transparent;")
            rl=QHBoxLayout(row); rl.setContentsMargins(0,2,0,2)
            rl.addWidget(label(f"{lbl_t}:",TEXT_DIM,10)); rl.addStretch()
            rl.addWidget(label(val_t,col,10)); lay2.addWidget(row)

    def _save_session(self):
        words=self._sess_words.value()
        qual=self._qual_grp.checkedId() or 3
        if words<=0: self._sess_fb.setText("! ENTER WORD COUNT"); return
        def run():
            thesis=dict(self._thesis)
            logs=list(thesis.get("writingLogs") or [])
            today=fb.today_key()
            ex=next((l for l in logs if l.get("date")==today),None)
            if ex: ex["words"]=int(ex.get("words",0) or 0)+words; ex["quality"]=qual
            else: logs.append({"date":today,"words":words,"quality":qual})
            thesis["writingLogs"]=logs
            fb.save_thesis(self._uid,self._token,thesis)
            import time as _t
            ts=int(_t.time()*1000)
            fb.fs_add(f"users/{self._uid}/logs",
                      {"tracker":"writing_session","value":str(float(words)),
                       "unit":"words","type":"writing_session","ts":ts,"timestamp":ts},
                      self._token)
            QTimer.singleShot(0,lambda:self._sess_fb.setText(
                f"SESSION LOGGED: {words:,} WORDS  QUALITY: {qual}/5"))
            QTimer.singleShot(3000,lambda:self._sess_fb.setText(""))
        threading.Thread(target=run,daemon=True).start()
