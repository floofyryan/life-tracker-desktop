"""
widgets.py
----------
Reusable Pip-Boy UI components for PyQt6.
Matches the Android app's visual language exactly.
"""

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QSizePolicy, QScrollArea
)
from PyQt6.QtCore  import Qt, QSize, QRect, QPoint, QTimer
from PyQt6.QtGui   import (
    QPainter, QColor, QPen, QFont, QFontMetrics,
    QLinearGradient, QPainterPath
)
from ui.style import (
    BLACK, SURF, SURF_MID, GREEN, GREEN_DIM, AMBER, RED,
    TEXT_DIM, TEXT_MUTED,
    pip_panel_style, pip_button_style, section_header_style,
    score_label_style, vital_value_style
)


# ── Section header  // LIKE THIS ──────────────────────────────
class SectionHeader(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setText(self, text):
        self._text = text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Text
        p.setPen(QColor(TEXT_DIM))
        f = QFont("Courier New", 10)
        p.setFont(f)
        p.drawText(QRect(4, 4, self.width()-8, 18), Qt.AlignmentFlag.AlignLeft, self._text)
        # Separator line
        p.setPen(QColor(SURF_MID))
        p.drawLine(0, 26, self.width(), 26)


# ── PipPanel — bordered surface card ──────────────────────────
class PipPanel(QFrame):
    def __init__(self, parent=None, border_color=None):
        super().__init__(parent)
        self._border = border_color or SURF_MID
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SURF};
                border: 1px solid {self._border};
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(6)

    def layout(self):
        return self._layout

    def set_border_color(self, color):
        self._border = color
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SURF};
                border: 1px solid {color};
            }}
        """)


# ── PipButton — matches Android PipButton exactly ─────────────
class PipButton(QPushButton):
    def __init__(self, text, color=None, parent=None):
        super().__init__(text.upper(), parent)
        self._color = color or GREEN
        self._apply_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _apply_style(self):
        c = self._color
        def blend(base, tint, a):
            def h(s): return tuple(int(s.lstrip("#")[i:i+2],16) for i in (0,2,4))
            b = h(base); t = h(tint)
            r = tuple(int(b[i]*(1-a)+t[i]*a) for i in range(3))
            return "#{:02x}{:02x}{:02x}".format(*r)
        bg = blend(BLACK, c, 0.07)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {c};
                border: 1px solid {c};
                font-family: "Courier New";
                font-size: 11px;
                font-weight: bold;
                padding: 7px 14px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {blend(SURF, c, 0.15)};
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
        """)

    def set_color(self, color):
        self._color = color
        self._apply_style()


# ── SegBar20 — 20-segment progress bar ────────────────────────
class SegBar20(QWidget):
    def __init__(self, value=0, max_val=100, color=None, parent=None):
        super().__init__(parent)
        self._value   = value
        self._max_val = max_val
        self._color   = color or GREEN
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value, max_val=None, color=None):
        self._value   = value
        if max_val is not None: self._max_val = max_val
        if color   is not None: self._color   = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width(); h = self.height()
        seg_w  = (w - 21) / 20   # 20 segments, 1px gap each
        pct    = min(1.0, float(self._value) / max(1.0, float(self._max_val)))
        filled = int(pct * 20)
        for i in range(20):
            x = int(i * (seg_w + 1))
            sw = max(1, int(seg_w))
            if i < filled:
                p.fillRect(x, 0, sw, h, QColor(self._color))
            else:
                p.fillRect(x, 0, sw, h, QColor(SURF_MID))
            # Segment border
            p.setPen(QColor(BLACK))
            p.drawRect(x, 0, sw, h-1)


# ── MarqueeLabel — scrolling text for long strings ─────────────
class MarqueeLabel(QWidget):
    def __init__(self, text="", color=None, font_size=11, parent=None):
        super().__init__(parent)
        self._text    = text
        self._color   = color or GREEN
        self._font_sz = font_size
        self._offset  = 0
        self._txt_w   = 0
        self.setFixedHeight(font_size + 8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(30)

    def setText(self, text):
        self._text   = text
        self._offset = 0
        self.update()

    def setColor(self, color):
        self._color = color
        self.update()

    def _scroll(self):
        f = QFont("Courier New", self._font_sz)
        fm = QFontMetrics(f)
        self._txt_w = fm.horizontalAdvance(self._text)
        if self._txt_w > self.width():
            self._offset -= 2
            if self._offset < -(self._txt_w + 20):
                self._offset = self.width()
        else:
            self._offset = 0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setClipRect(0, 0, self.width(), self.height())
        f = QFont("Courier New", self._font_sz)
        p.setFont(f)
        p.setPen(QColor(self._color))
        x = self._offset if self._txt_w > self.width() else 0
        p.drawText(int(x), self.height()-4, self._text)

    def closeEvent(self, e):
        self._timer.stop()


# ── GlowLabel — label with phosphor glow effect ───────────────
class GlowLabel(QLabel):
    """A QLabel that draws a subtle glow behind the text."""
    def __init__(self, text="", color=None, font_size=11, bold=False, parent=None):
        super().__init__(text, parent)
        self._color   = QColor(color or GREEN)
        self._font_sz = font_size
        self._bold    = bold
        f = QFont("Courier New", font_size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
        self.setFont(f)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def setColor(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = QFont("Courier New", self._font_sz,
                  QFont.Weight.Bold if self._bold else QFont.Weight.Normal)
        p.setFont(f)
        # Glow layer (slightly transparent, offset slightly)
        glow = QColor(self._color)
        glow.setAlpha(60)
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            p.setPen(QPen(glow))
            p.drawText(self.rect().adjusted(dx,dy,dx,dy), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        # Main text
        p.setPen(QPen(self._color))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())


# ── PipIcon — canvas-drawn icons matching Android app ─────────
class PipIcon(QWidget):
    def __init__(self, kind="foc", color=None, size=20, parent=None):
        super().__init__(parent)
        self._kind  = kind
        self._color = color or GREEN
        self._size  = size
        self.setFixedSize(size, size)

    def set_color(self, color):
        self._color = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._draw(p)

    def _draw(self, p):
        s  = self._size
        h  = s // 2
        c  = QColor(self._color)
        lw = max(1, s // 12)

        p.setPen(QPen(c, lw))
        p.setBrush(c)

        k = self._kind

        if k == "water":
            path = QPainterPath()
            path.moveTo(h, 2)
            path.cubicTo(h+8,h-2, h+10,h+4, h, s-2)
            path.cubicTo(h-10,h+4, h-8,h-2, h, 2)
            p.fillPath(path, c)
            p.setBrush(QColor(SURF))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPoint(h, h+3), 3, 2)

        elif k == "sleep":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(3, 2, s-6, s-4)
            p.setBrush(QColor(SURF))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(6, 1, s-4, s-2)
            p.setPen(QPen(c, lw))
            p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            p.drawText(s-7, 8, "*")

        elif k in ("steps", "active"):
            pts = [(h,2),(h+5,10),(h+2,10),(h+2,s-2),(h-2,s-2),(h-2,10),(h-5,10)]
            path = QPainterPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]: path.lineTo(*pt)
            path.closeSubpath()
            p.fillPath(path, c)

        elif k == "str":
            pts = [(h,2),(s-2,h),(h,s-2),(2,h)]
            path = QPainterPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]: path.lineTo(*pt)
            path.closeSubpath()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.drawLine(h, 4, h, s-4)
            p.drawLine(4, h, s-4, h)

        elif k == "end":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(3, 3, s-6, s-6)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(7, 7, s-14, s-14)

        elif k == "per":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(2, h-5, s-4, 10, 0, 180*16)
            p.drawArc(2, h-5, s-4, 10, 180*16, 180*16)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(h-2, h-2, 4, 4)

        elif k == "agi":
            for y in [5, h, s-5]:
                p.drawLine(3, y, s-6, y)

        elif k == "foc":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(2, 2, s-4, s-4)
            p.drawEllipse(6, 6, s-12, s-12)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(h-2, h-2, 4, 4)

        elif k == "tsk":
            p.setFont(QFont("Courier New", 7))
            for i, y in enumerate([4, h, s-5]):
                p.drawText(4, y+4, "x" if i==0 else "-")
                p.drawLine(10, y, s-2, y)

        elif k == "weight":
            p.fillRect(2, h-3, 4, 6, c)
            p.fillRect(6, h-1, s-12, 2, c)
            p.fillRect(s-6, h-3, 4, 6, c)

        elif k == "timer":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(2, 2, s-4, s-4)
            p.drawLine(h, h, h, 5)
            p.drawLine(h, h, h+4, h+3)

        elif k == "thesis":
            path = QPainterPath()
            path.moveTo(2,3); path.lineTo(h,1); path.lineTo(h,s-3); path.lineTo(2,s-1); path.closeSubpath()
            path2 = QPainterPath()
            path2.moveTo(h,1); path2.lineTo(s-2,3); path2.lineTo(s-2,s-1); path2.lineTo(h,s-3); path2.closeSubpath()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path); p.drawPath(path2)
            p.drawLine(h, 1, h, s-3)

        elif k == "plus":
            p.drawLine(h, 3, h, s-3)
            p.drawLine(3, h, s-3, h)

        elif k == "condition":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(h-5, 1, 10, 11)
            p.drawRect(h-4, 12, 8, s-14)
            p.drawLine(h-4, s-4, h-8, s-2)
            p.drawLine(h+4, s-4, h+8, s-2)


# ── Helpers ────────────────────────────────────────────────────
def make_row(*widgets, spacing=8):
    """Quick HBox row."""
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0,0,0,0)
    lay.setSpacing(spacing)
    for widget in widgets:
        if widget == "stretch":
            lay.addStretch()
        elif isinstance(widget, int):
            lay.addSpacing(widget)
        else:
            lay.addWidget(widget)
    return w

def make_col(*widgets, spacing=6):
    """Quick VBox column."""
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0,0,0,0)
    lay.setSpacing(spacing)
    for widget in widgets:
        if widget == "stretch":
            lay.addStretch()
        elif isinstance(widget, int):
            lay.addSpacing(widget)
        else:
            lay.addWidget(widget)
    return w

def h_line():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {SURF_MID}; background: {SURF_MID}; max-height: 1px;")
    return line

def label(text, color=None, size=11, bold=False, muted=False):
    l = QLabel(text)
    c = color or (TEXT_DIM if muted else GREEN)
    w = "bold" if bold else "normal"
    l.setStyleSheet(f"color: {c}; font-size: {size}px; font-weight: {w}; background: transparent;")
    return l

def scroll_wrap(widget):
    """Wrap a widget in a QScrollArea."""
    sa = QScrollArea()
    sa.setWidget(widget)
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    return sa
