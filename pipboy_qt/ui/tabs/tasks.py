"""ui/tabs/tasks.py"""
import threading, uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QLineEdit, QComboBox, QButtonGroup,
    QRadioButton, QFrame, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, SegBar20, GlowLabel, label
import firebase as fb


class TaskRow(QWidget):
    def __init__(self, task, on_toggle, parent=None):
        super().__init__(parent)
        self._task      = task
        self._on_toggle = on_toggle
        self._build()

    def _build(self):
        t    = self._task
        done = bool(t.get("done", False))
        wgt  = int(t.get("weight", 1) or 1)
        cat  = str(t.get("category","")).upper()
        text = str(t.get("text",""))
        age  = 0
        try:
            from datetime import datetime
            cr = t.get("createdDate","") or ""
            if cr:
                age = (datetime.now()-datetime.strptime(cr,"%Y-%m-%d")).days
        except: pass

        col = TEXT_DIM if done else RED if age>=7 else AMBER if age>=3 else GREEN
        bg  = SURF

        self.setStyleSheet(f"background:{bg}; border: 1px solid {SURF_MID};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        # Checkbox label
        cb = QLabel("[x]" if done else "[ ]")
        cb.setStyleSheet(
            f"color:{col}; font-size:12px; background:transparent; cursor:pointer;")
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        tid = t.get("id","")
        cb.mousePressEvent = lambda e, i=tid, d=done: self._on_toggle(i, not d)
        lay.addWidget(cb)

        # Text + meta
        mid = QVBoxLayout(); mid.setSpacing(2)
        display = text[:30]+".." if len(text)>30 else text
        tl = QLabel(display.upper())
        tl.setStyleSheet(
            f"color:{TEXT_DIM if done else col}; font-size:11px; background:transparent;"
            + ("text-decoration: line-through;" if done else ""))
        mid.addWidget(tl)
        meta = cat + (f"  ! OVERDUE {age}D" if age>=7 else "")
        ml = QLabel(meta)
        ml.setStyleSheet(f"color:{TEXT_MUTED}; font-size:8px; background:transparent;")
        mid.addWidget(ml)
        lay.addLayout(mid)
        lay.addStretch()

        # Weight badge
        wf = QFrame()
        wf.setStyleSheet(f"background:{SURF_MID}; border:none;")
        wfl = QHBoxLayout(wf); wfl.setContentsMargins(6,3,6,3)
        wfl.addWidget(QLabel(f"W{wgt}"))
        wf.findChild(QLabel).setStyleSheet(
            f"color:{GREEN_DIM}; font-size:9px; background:transparent;")
        lay.addWidget(wf)


class TasksTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid    = uid
        self._token  = token
        self._todos  = []
        self._filter = "ALL"
        self._build()

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Filter bar
        fbar = QWidget(); fbar.setStyleSheet(f"background:{BLACK};")
        fl = QHBoxLayout(fbar); fl.setContentsMargins(10,6,10,6); fl.setSpacing(4)
        self._filter_btns = {}
        for cat in ["ALL","THESIS","JOBS","ADMIN","MISC"]:
            btn = PipButton(cat, GREEN_DIM)
            btn.clicked.connect(lambda _,c=cat: self._set_filter(c))
            fl.addWidget(btn)
            self._filter_btns[cat] = btn
        fl.addStretch()
        outer.addWidget(fbar)

        # Carry weight
        cbar = QWidget(); cbar.setStyleSheet(f"background:{BLACK};")
        cl = QHBoxLayout(cbar); cl.setContentsMargins(10,4,10,4); cl.setSpacing(8)
        cl.addWidget(label("CARRY WEIGHT:", GREEN_DIM, 10))
        self._carry_lbl = label("0/20", GREEN_DIM, 11)
        cl.addWidget(self._carry_lbl)
        self._carry_bar = SegBar20(0, 20, GREEN_DIM)
        self._carry_bar.setFixedWidth(180)
        cl.addWidget(self._carry_bar)
        cl.addStretch()
        outer.addWidget(cbar)

        # Scrollable task list
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{border:none;}")
        self._list_widget = QWidget(); self._list_widget.setStyleSheet(f"background:{BLACK};")
        self._list_lay = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(10,4,10,4); self._list_lay.setSpacing(3)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_widget)
        outer.addWidget(self._scroll)

        # Add task bar
        add = QWidget(); add.setStyleSheet(f"background:{SURF}; border-top:1px solid {SURF_MID};")
        al = QHBoxLayout(add); al.setContentsMargins(10,6,10,6); al.setSpacing(6)
        self._task_entry = QLineEdit()
        self._task_entry.setPlaceholderText("new task...")
        self._task_entry.returnPressed.connect(self._add_task)
        al.addWidget(self._task_entry)
        self._task_wgt = QComboBox()
        self._task_wgt.addItems(["W1","W2","W3","W4","W5"]); self._task_wgt.setFixedWidth(54)
        al.addWidget(self._task_wgt)
        self._task_cat = QComboBox()
        self._task_cat.addItems(["THESIS","JOBS","ADMIN","PERSONAL"]); self._task_cat.setFixedWidth(90)
        al.addWidget(self._task_cat)
        add_btn = PipButton("ADD", GREEN); add_btn.clicked.connect(self._add_task)
        al.addWidget(add_btn)
        outer.addWidget(add)

        self._set_filter("ALL")

    def update_data(self, data):
        self._todos = data.get("todos", [])
        self._refresh_list()

    def _refresh_list(self):
        cat = self._filter
        cat_key = "PERSONAL" if cat=="MISC" else cat
        filtered = [t for t in self._todos
                    if cat=="ALL" or str(t.get("category","")).upper()==cat_key]
        filtered.sort(key=lambda t: (t.get("done",False), -(int(t.get("weight",1) or 1))))

        # Clear list
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not filtered:
            self._list_lay.insertWidget(0, label("NO TASKS", TEXT_MUTED, 11))
        else:
            for i, t in enumerate(filtered):
                row = TaskRow(t, self._toggle_task)
                self._list_lay.insertWidget(i, row)

        # Carry weight
        carry = sum(int(t.get("weight",1) or 1) for t in self._todos if not t.get("done"))
        col   = RED if carry>20 else AMBER if carry>15 else GREEN_DIM
        self._carry_lbl.setText(f"{carry}/20")
        self._carry_lbl.setStyleSheet(f"color:{col};font-size:11px;background:transparent;")
        self._carry_bar.set_value(min(carry,20), 20, col)

        # Filter button styles
        for c, btn in self._filter_btns.items():
            if c == cat:
                btn.set_color(GREEN)
            else:
                btn.set_color(GREEN_DIM)

    def _set_filter(self, cat):
        self._filter = cat
        self._refresh_list()

    def _toggle_task(self, tid, done):
        def run():
            todos = list(self._todos)
            for t in todos:
                if t.get("id")==tid:
                    t["done"]=done
                    t["checkedOffDate"]=fb.today_key() if done else ""
            fb.save_todos(self._uid, self._token, todos)
            QTimer.singleShot(0, lambda: self.update_data({"todos": todos}))
        threading.Thread(target=run, daemon=True).start()

    def _add_task(self):
        text = self._task_entry.text().strip()
        if not text: return
        wgt  = int(self._task_wgt.currentText().replace("W",""))
        cat  = self._task_cat.currentText()
        def run():
            todos = list(self._todos)
            todos.append({
                "id": str(uuid.uuid4()), "text": text, "done": False,
                "weight": wgt, "baseWeight": wgt, "category": cat,
                "createdDate": fb.today_key(), "checkedOffDate": "",
                "rolledOver": False, "rolledFrom": "", "autoIncr": False,
                "tags": [], "deadline": "", "notes": ""
            })
            fb.save_todos(self._uid, self._token, todos)
            QTimer.singleShot(0, lambda: self._task_entry.clear())
            QTimer.singleShot(0, lambda: self.update_data({"todos": todos}))
        threading.Thread(target=run, daemon=True).start()
