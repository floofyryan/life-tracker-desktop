"""
style.py
--------
All Qt Style Sheets and colour constants for the Pip-Boy app.
Matches the exact palette from Android's PipBoy object in MainActivity.kt.
"""

# ── Palette (exact from Android source) ───────────────────────
BLACK      = "#071109"
SURF       = "#0A1A0A"
SURF_MID   = "#1A4A1A"
GREEN      = "#00FF66"
GREEN_DIM  = "#00AA44"
AMBER      = "#FFB000"
RED        = "#FF3333"
TEXT_DIM   = "#00CC55"
TEXT_MUTED = "#004422"

# ── Global stylesheet applied to QApplication ─────────────────
APP_STYLE = f"""
/* ── Base ─────────────────────────────────────────────── */
* {{
    font-family: "Courier New", monospace;
    color: {GREEN};
    background-color: {BLACK};
    border: none;
    outline: none;
}}

QWidget {{
    background-color: {BLACK};
    color: {GREEN};
}}

/* ── Scroll area ──────────────────────────────────────── */
QScrollArea {{
    background-color: {BLACK};
    border: none;
}}

QScrollBar:vertical {{
    background: {BLACK};
    width: 6px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {SURF_MID};
    border-radius: 3px;
    min-height: 20px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

/* ── Tab bar ──────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BLACK};
}}

QTabBar {{
    background: {SURF};
    border-bottom: 1px solid {SURF_MID};
}}

QTabBar::tab {{
    background: {SURF};
    color: {GREEN_DIM};
    font-family: "Courier New";
    font-size: 10px;
    font-weight: bold;
    padding: 8px 14px;
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

/* ── Labels ───────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {GREEN};
    font-family: "Courier New";
}}

/* ── Line edit / Text entry ───────────────────────────── */
QLineEdit {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {SURF_MID};
    font-family: "Courier New";
    font-size: 11px;
    padding: 5px 8px;
    selection-background-color: {GREEN};
    selection-color: {BLACK};
}}

QLineEdit:focus {{
    border: 1px solid {GREEN};
}}

QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Text edit (notes) ────────────────────────────────── */
QTextEdit {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {SURF_MID};
    font-family: "Courier New";
    font-size: 11px;
    padding: 6px;
    selection-background-color: {GREEN};
    selection-color: {BLACK};
}}

QTextEdit:focus {{
    border: 1px solid {GREEN};
}}

/* ── Combo box ────────────────────────────────────────── */
QComboBox {{
    background: {SURF};
    color: {GREEN_DIM};
    border: 1px solid {SURF_MID};
    font-family: "Courier New";
    font-size: 10px;
    padding: 4px 8px;
}}

QComboBox:hover {{
    border: 1px solid {GREEN};
    color: {GREEN};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {GREEN_DIM};
    width: 0;
    height: 0;
}}

QComboBox QAbstractItemView {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {GREEN};
    selection-background-color: rgba(0,255,102,0.15);
    selection-color: {GREEN};
    outline: none;
}}

/* ── Spin box ─────────────────────────────────────────── */
QSpinBox {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {SURF_MID};
    font-family: "Courier New";
    font-size: 11px;
    padding: 4px 8px;
}}

QSpinBox:focus {{
    border: 1px solid {GREEN};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {SURF_MID};
    border: none;
    width: 16px;
}}

/* ── Slider ───────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {SURF_MID};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {GREEN};
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -4px 0;
}}

QSlider::sub-page:horizontal {{
    background: {GREEN};
    border-radius: 2px;
}}

/* ── Check box ────────────────────────────────────────── */
QCheckBox {{
    color: {GREEN_DIM};
    spacing: 8px;
    font-family: "Courier New";
    font-size: 10px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {SURF_MID};
    background: {SURF};
}}

QCheckBox::indicator:checked {{
    background: rgba(0,255,102,0.2);
    border: 1px solid {GREEN};
}}

QCheckBox::indicator:hover {{
    border: 1px solid {GREEN};
}}

/* ── Message box ──────────────────────────────────────── */
QMessageBox {{
    background: {SURF};
}}

QMessageBox QPushButton {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {GREEN};
    padding: 6px 16px;
    font-family: "Courier New";
    font-size: 10px;
    font-weight: bold;
}}

QMessageBox QPushButton:hover {{
    background: rgba(0,255,102,0.1);
}}

/* ── Tool tip ─────────────────────────────────────────── */
QToolTip {{
    background: {SURF};
    color: {GREEN};
    border: 1px solid {GREEN_DIM};
    font-family: "Courier New";
    font-size: 9px;
    padding: 4px 8px;
}}
"""

# ── Component-level styles (applied per-widget) ────────────────
def pip_panel_style(border_color=None):
    bc = border_color or SURF_MID
    return f"""
        background-color: {SURF};
        border: 1px solid {bc};
    """

def pip_button_style(color=None, width=None):
    c  = color or GREEN
    bg = _blend(BLACK, c, 0.07)
    w  = f"min-width: {width}px;" if width else ""
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {c};
            border: 1px solid {c};
            font-family: "Courier New";
            font-size: 11px;
            font-weight: bold;
            padding: 7px 14px;
            letter-spacing: 1px;
            {w}
        }}
        QPushButton:hover {{
            background-color: rgba(0,255,102,0.12);
        }}
        QPushButton:pressed {{
            background-color: {c};
            color: {BLACK};
        }}
        QPushButton:disabled {{
            color: {TEXT_MUTED};
            border-color: {SURF_MID};
            background: {SURF};
        }}
    """.replace("rgba(0,255,102,0.12)", f"rgba({_hex_to_rgb(c)},0.12)")

def section_header_style():
    return f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 1px;"

def score_label_style(color=None):
    c = color or GREEN
    return f"color: {c}; font-size: 26px; font-weight: bold;"

def vital_value_style(color=None):
    c = color or GREEN
    return f"color: {c}; font-size: 20px; font-weight: bold;"

def _blend(hex_base, hex_tint, alpha):
    def h(s): return tuple(int(s.lstrip("#")[i:i+2],16) for i in (0,2,4))
    b = h(hex_base); t = h(hex_tint)
    r = tuple(int(b[i]*(1-alpha)+t[i]*alpha) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*r)

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i+2],16)) for i in (0,2,4))
