"""Design system for the Wall-E Companion desktop app.

Single source of truth for colors, fonts, spacing and the Qt stylesheet.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette — "mission control" dark theme with Wall-E amber + oscilloscope cyan
# ---------------------------------------------------------------------------
BG = "#05080d"
BG_DEEP = "#03060a"
SURFACE = "#0a1119"
SURFACE_2 = "#0e1824"
SURFACE_3 = "#131f2d"
BORDER = "#1a2a3a"
BORDER_SOFT = "#122030"

TEXT = "#e8f1f8"
TEXT_MUTED = "#7e93a6"
TEXT_DIM = "#54697c"

AMBER = "#ffb23f"
AMBER_DIM = "#8a5c14"
CYAN = "#38d6ff"
CYAN_DIM = "#12566b"
GREEN = "#3ddc97"
RED = "#ff5a5f"
PURPLE = "#b18cff"
YELLOW = "#ffd166"

MOOD_COLORS = {
    "idle": "#38d6ff",
    "curious": "#b18cff",
    "happy": "#3ddc97",
    "sad": "#6c8cff",
    "alert": "#ff5a5f",
    "thinking": "#ffd166",
    "sleeping": "#54697c",
}

MODE_COLORS = {
    "booting": "#7e93a6",
    "idle": "#38d6ff",
    "curious": "#b18cff",
    "interacting": "#3ddc97",
    "speaking": "#ffb23f",
    "listening": "#38d6ff",
    "thinking": "#ffd166",
    "sleeping": "#54697c",
    "low_battery": "#ff5a5f",
    "emergency_stop": "#ff5a5f",
    "error": "#ff5a5f",
}

SERVO_COLORS = {
    "head_pan": "#38d6ff",
    "head_tilt": "#38d6ff",
    "eye_L": "#ffb23f",
    "eye_R": "#ffb23f",
    "body_lean": "#b18cff",
    "arm_L": "#3ddc97",
    "arm_R": "#3ddc97",
}

FONT_UI = "Segoe UI"
FONT_DISPLAY = "Bahnschrift"
FONT_MONO = "Cascadia Mono"


def mood_color(mood: str) -> str:
    return MOOD_COLORS.get(str(mood).lower(), AMBER)


def mode_color(mode: str) -> str:
    return MODE_COLORS.get(str(mode).lower(), CYAN)


APP_QSS = f"""
* {{
    outline: 0;
}}
QWidget {{
    color: {TEXT};
    font-family: "{FONT_UI}";
    font-size: 13px;
}}
QMainWindow, #Root {{
    background: {BG};
}}
QToolTip {{
    background: {SURFACE_3};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 8px;
    border-radius: 6px;
}}

/* ---------- Structural panels ---------- */
#Sidebar {{
    background: {BG_DEEP};
    border-right: 1px solid {BORDER_SOFT};
}}
#TopBar {{
    background: {BG_DEEP};
    border-bottom: 1px solid {BORDER_SOFT};
}}
#StatusBar {{
    background: {BG_DEEP};
    border-top: 1px solid {BORDER_SOFT};
}}
#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}
#Card:hover {{
    border-color: {BORDER};
}}
#CardFlat {{
    background: {SURFACE};
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
}}
#Tile {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {SURFACE_2}, stop:1 {SURFACE});
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}
#Divider {{
    background: {BORDER_SOFT};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ---------- Typography ---------- */
#BrandMark {{
    color: {AMBER};
    font-family: "{FONT_DISPLAY}";
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 3px;
}}
#BrandSub {{
    color: {TEXT_DIM};
    font-family: "{FONT_MONO}";
    font-size: 10px;
    letter-spacing: 2px;
}}
#PageTitle {{
    color: {TEXT};
    font-family: "{FONT_DISPLAY}";
    font-size: 25px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
#PageSubtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
#SectionLabel {{
    color: {TEXT_MUTED};
    font-family: "{FONT_MONO}";
    font-size: 10px;
    letter-spacing: 2px;
    font-weight: 600;
}}
#CardTitle {{
    color: {TEXT};
    font-size: 14px;
    font-weight: 600;
}}
#Hint {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
#Mono {{
    font-family: "{FONT_MONO}";
    font-size: 12px;
    color: {TEXT_MUTED};
}}
#HeroValue {{
    color: {TEXT};
    font-family: "{FONT_DISPLAY}";
    font-size: 26px;
    font-weight: 600;
}}
#HeroUnit {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
#MetricValue {{
    color: {TEXT};
    font-family: "{FONT_DISPLAY}";
    font-size: 20px;
    font-weight: 600;
}}

/* ---------- Sidebar navigation ---------- */
QPushButton#NavItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    color: {TEXT_MUTED};
    font-size: 13px;
    font-weight: 500;
    text-align: left;
    padding: 10px 14px;
}}
QPushButton#NavItem:hover {{
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton#NavItem:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 178, 63, 0.16), stop:1 rgba(255, 178, 63, 0.02));
    border: 1px solid rgba(255, 178, 63, 0.30);
    color: {AMBER};
    font-weight: 600;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {SURFACE_3};
    border-color: #2b4257;
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background: {SURFACE};
    border-color: {BORDER_SOFT};
}}
QPushButton:focus {{
    border-color: {CYAN};
}}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffc266, stop:1 #f0a02c);
    border: 1px solid #ffca7a;
    color: #1a1206;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: #ffcb7d;
}}
QPushButton#Primary:disabled {{
    background: {SURFACE_2};
    color: {TEXT_DIM};
    border-color: {BORDER};
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER};
}}
QPushButton#Ghost:hover {{
    background: {SURFACE_2};
}}
QPushButton#Danger {{
    background: rgba(255, 90, 95, 0.12);
    border: 1px solid rgba(255, 90, 95, 0.55);
    color: {RED};
    font-weight: 700;
}}
QPushButton#Danger:hover {{
    background: rgba(255, 90, 95, 0.22);
}}
QPushButton#DangerSolid {{
    background: #d63b41;
    border: 1px solid #ff6b70;
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#DangerSolid:hover {{
    background: #ef4b51;
}}
QPushButton#Chip {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 6px 14px;
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QPushButton#Chip:hover {{
    color: {TEXT};
    border-color: #2b4257;
}}
QPushButton#Chip:checked {{
    background: rgba(56, 214, 255, 0.14);
    border-color: {CYAN};
    color: {CYAN};
    font-weight: 600;
}}

/* ---------- Inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    selection-background-color: {CYAN_DIM};
    selection-color: {TEXT};
    padding: 8px 10px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {CYAN};
}}
QComboBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    color: {TEXT};
}}
QComboBox:hover {{
    border-color: #2b4257;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {SURFACE_3};
    color: {TEXT};
    padding: 4px;
}}
QSpinBox, QDoubleSpinBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 8px;
    color: {TEXT};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {CYAN};
}}
QCheckBox {{
    color: {TEXT};
    spacing: 9px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {BORDER};
    border-radius: 5px;
    background: {SURFACE_2};
}}
QCheckBox::indicator:hover {{
    border-color: {CYAN_DIM};
}}
QCheckBox::indicator:checked {{
    background: {AMBER};
    border-color: {AMBER};
    image: none;
}}

/* ---------- Sliders ---------- */
QSlider::groove:horizontal {{
    height: 5px;
    background: {SURFACE_3};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {AMBER_DIM}, stop:1 {AMBER});
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #ffffff;
    border: 2px solid {AMBER};
}}
QSlider::handle:horizontal:hover {{
    background: {AMBER};
    border-color: #ffe0b0;
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {SURFACE_3};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2aa97a, stop:1 {GREEN});
    border-radius: 4px;
}}

/* ---------- Scrollbars ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #1f3244;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #2b4257;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: #1f3244;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    padding: 9px 18px;
    margin-right: 4px;
    font-size: 12px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QTabBar::tab:selected {{
    color: {AMBER};
    border-bottom: 2px solid {AMBER};
}}
"""
