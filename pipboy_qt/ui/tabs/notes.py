"""ui/tabs/notes.py"""
import threading
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QTextEdit
from PyQt6.QtCore import Qt, QTimer
from ui.style   import BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED, TEXT_DIM, TEXT_MUTED
from ui.widgets import SectionHeader, PipPanel, PipButton, label
import firebase as fb

class NotesTab(QWidget):
    def __init__(self, uid, token, parent=None):
        super().__init__(parent)
        self._uid=uid; self._token=token; self._build()

    def _build(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        c=QWidget(); c.setStyleSheet(f"background:{BLACK};")
        lay=QVBoxLayout(c); lay.setContentsMargins(10,8,10,8); lay.setSpacing(4)

        lay.addWidget(SectionHeader("// VAULT-TEC DAILY NOTES"))
        np=PipPanel()
        dr=QHBoxLayout(); dr.setSpacing(8)
        dr.addWidget(label("DATE:",TEXT_DIM,10))
        self._date_lbl = label(fb.today_key(),GREEN,11)
        dr.addWidget(self._date_lbl); dr.addStretch()
        np.layout().addLayout(dr)
        self._note_text=QTextEdit()
        self._note_text.setMinimumHeight(160)
        self._note_text.setStyleSheet(f"""
            QTextEdit {{
                background:{SURF}; color:{GREEN};
                border:1px solid {SURF_MID};
                font-family:"Courier New"; font-size:11px;
                padding:6px;
            }}
            QTextEdit:focus {{ border:1px solid {GREEN}; }}
        """)
        np.layout().addWidget(self._note_text)
        br=QHBoxLayout(); br.setSpacing(6)
        save_btn=PipButton("SAVE NOTE",GREEN); save_btn.clicked.connect(self._save_note)
        load_btn=PipButton("LOAD NOTE",GREEN_DIM); load_btn.clicked.connect(self._load_note)
        br.addWidget(save_btn); br.addWidget(load_btn); br.addStretch()
        np.layout().addLayout(br)
        self._note_fb=label("",GREEN,10); np.layout().addWidget(self._note_fb)
        lay.addWidget(np); lay.addStretch(); scroll.setWidget(c)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

    def update_data(self, data):
        self._date_lbl.setText(fb.today_key())

    def _feedback(self,msg,color=GREEN):
        self._note_fb.setText(msg)
        self._note_fb.setStyleSheet(f"color:{color};font-size:10px;background:transparent;")
        QTimer.singleShot(2000,lambda:self._note_fb.setText(""))

    def _save_note(self):
        text=self._note_text.toPlainText()
        def run():
            fb.save_note(self._uid,self._token,fb.today_key(),text)
            QTimer.singleShot(0,lambda:self._feedback("NOTE SAVED",GREEN))
        threading.Thread(target=run,daemon=True).start()

    def _load_note(self):
        def run():
            text=fb.load_note(self._uid,self._token,fb.today_key())
            QTimer.singleShot(0,lambda:self._note_text.setPlainText(text))
            QTimer.singleShot(0,lambda:self._feedback("NOTE LOADED",GREEN_DIM))
        threading.Thread(target=run,daemon=True).start()
