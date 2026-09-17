"""Murmur theme - light/dark palettes + a dynamically-built stylesheet.

Two palettes live here: `LIGHT` and `DARK`. The module-level attributes
(`theme.BG`, `theme.TEXT`, etc.) are resolved at access time against the
currently active palette via PEP 562 module __getattr__, so all callers
keep their existing `theme.X` style without code changes when the user
flips themes.
"""
from __future__ import annotations

from PySide6.QtGui import QColor


LIGHT: dict[str, str] = {
    "BG":              "#FAFAF7",
    "SURFACE":         "#FFFFFF",
    "SURFACE_2":       "#F4F3EF",
    "HOVER_BG":        "#EFEEE9",
    "NAV_SEL_BG":      "#ECEAE4",
    "BORDER":          "#ECECE8",
    "BORDER_2":        "#E1E0DB",
    "TEXT":            "#1A1A1C",
    "TEXT_MUTED":      "#6B6B6E",
    "TEXT_DIM":        "#A0A0A2",
    "HERO_BG":         "#15151A",
    "HERO_TEXT":       "#FFFFFF",
    "HERO_CTA_BG":     "#FFFFFF",
    "HERO_CTA_TEXT":   "#15151A",
    "HERO_CTA_HOVER":  "#E8E8E5",
    "PRIMARY_BTN_BG":  "#15151A",
    "PRIMARY_BTN_TEXT": "#FFFFFF",
    "PRIMARY_BTN_HOVER": "#2A2A30",
    "ACCENT":          "#87B9F5",
    "ACCENT_DK":       "#3B7BD9",
    "RECORDING":       "#E26A6A",
    "TRANSCRIBING":    "#5BD39B",
    "SCROLL_HANDLE":   "#E1E0DB",
    "SCROLL_HOVER":    "#C5C4BE",
}


DARK: dict[str, str] = {
    "BG":              "#0B0B0E",
    "SURFACE":         "#131318",
    "SURFACE_2":       "#22222C",
    "HOVER_BG":        "#2C2C38",
    "NAV_SEL_BG":      "#3A3A48",
    "BORDER":          "#2E2E38",
    "BORDER_2":        "#3F3F4A",
    "TEXT":            "#ECEAE6",
    "TEXT_MUTED":      "#B5B3B0",
    "TEXT_DIM":        "#8E8D92",
    "HERO_BG":         "#1F1F28",
    "HERO_TEXT":       "#FFFFFF",
    "HERO_CTA_BG":     "#FFFFFF",
    "HERO_CTA_TEXT":   "#15151A",
    "HERO_CTA_HOVER":  "#E0DFDB",
    "PRIMARY_BTN_BG":  "#ECEAE6",
    "PRIMARY_BTN_TEXT": "#131318",
    "PRIMARY_BTN_HOVER": "#FFFFFF",
    # Monochrome dark theme - accent colours are tonal greys/whites so the
    # whole UI matches the black-and-white silhouette icon. ACCENT is the
    # quiet selection tint; ACCENT_DK is the prominent highlight (POLISHED
    # label, focus borders, checkbox check, progress fill).
    "ACCENT":          "#55556A",
    "ACCENT_DK":       "#ECEAE6",
    "RECORDING":       "#E26A6A",
    "TRANSCRIBING":    "#ECEAE6",
    "SCROLL_HANDLE":   "#3F3F4A",
    "SCROLL_HOVER":    "#55556A",
}


_active: dict[str, str] = LIGHT


SIDEBAR_W   = 220
RIGHTRAIL_W = 300
NAV_ITEM_H  = 40


def set_mode(mode: str) -> None:
    """`mode` is 'light' or 'dark'. Anything else falls back to light."""
    global _active
    _active = DARK if mode == "dark" else LIGHT


def current_mode() -> str:
    return "dark" if _active is DARK else "light"


def palette() -> dict[str, str]:
    return _active


# ---- module-level attribute proxy (so theme.BG etc. stay dynamic) ----------

_COLOR_KEYS = {
    "COLOR_ACCENT":       "ACCENT",
    "COLOR_ACCENT_DK":    "ACCENT_DK",
    "COLOR_TEXT":         "TEXT",
    "COLOR_TEXT_MUTED":   "TEXT_MUTED",
    "COLOR_BORDER":       "BORDER",
}


def __getattr__(name: str):
    if name in _active:
        return _active[name]
    if name in _COLOR_KEYS:
        return QColor(_active[_COLOR_KEYS[name]])
    if name == "STYLESHEET":
        return _build_stylesheet()
    raise AttributeError(f"module 'theme' has no attribute {name!r}")


# ---- stylesheet builder ----------------------------------------------------

def _build_stylesheet() -> str:
    p = _active
    return f"""
QMainWindow, QWidget#Sidebar, QWidget#RightRail {{
    background: {p['BG']};
    color: {p['TEXT']};
}}

QWidget#MainArea {{
    background: {p['SURFACE']};
}}

QWidget#Sidebar {{
    /* No hard border — separation comes from surface contrast. */
}}

QWidget#RightRail {{
    /* No border — sits in the surround. */
}}

/* --- Sidebar --- */

QLabel#Brand {{
    color: {p['TEXT']};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 19px;
    font-weight: 500;
    padding: 0;
}}

QLabel#BrandBadge {{
    color: {p['TEXT']};
    background: transparent;
    border: 1px solid {p['BORDER_2']};
    border-radius: 10px;
    padding: 2px 9px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 10px;
    font-weight: 500;
}}

QPushButton#NavItem {{
    text-align: left;
    padding-left: 10px;
    padding-right: 10px;
    border: none;
    background: transparent;
    color: {p['TEXT']};
    border-radius: 10px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    min-height: {NAV_ITEM_H}px;
}}
QPushButton#NavItem:hover {{
    background: {p['SURFACE_2']};
}}
QPushButton#NavItem:checked {{
    background: {p['NAV_SEL_BG']};
    color: {p['TEXT']};
    font-weight: 500;
}}
QPushButton#NavItem:disabled {{
    color: {p['TEXT_MUTED']};
    background: transparent;
}}

QLabel#ComingSoon {{
    color: {p['TEXT_MUTED']};
    background: {p['SURFACE_2']};
    padding: 2px 7px;
    border-radius: 6px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QFrame#UsageCard {{
    background: {p['SURFACE_2']};
    border: 1px solid {p['BORDER']};
    border-radius: 12px;
}}
QLabel#UsageTitle {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: 600;
}}
QLabel#UsageBody {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 11px;
}}

/* --- Main area --- */

QLabel#Greeting {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 24px;
    font-weight: 400;
}}

QFrame#Hero {{
    background: {p['HERO_BG']};
    border-radius: 16px;
}}
QLabel#HeroEyebrow {{
    color: rgba(255,255,255,140);
    font-family: 'Segoe UI', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
}}
QLabel#HeroTitle {{
    color: {p['HERO_TEXT']};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 32px;
    font-weight: 400;
}}
QLabel#HeroBody {{
    color: rgba(255,255,255,180);
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QPushButton#HeroCta {{
    background: {p['HERO_CTA_BG']};
    color: {p['HERO_CTA_TEXT']};
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#HeroCta:hover {{
    background: {p['HERO_CTA_HOVER']};
}}

QLabel#SectionLabel {{
    color: {p['TEXT_DIM']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
}}

QFrame#TranscriptRow {{
    background: {p['SURFACE_2']};
    border: none;
    border-radius: 12px;
}}
QFrame#TranscriptRow:hover {{
    background: {p['HOVER_BG']};
}}
QLabel#TranscriptTime {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}}
QLabel#TranscriptText {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QLabel#TranscriptPolish {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}

/* --- Right rail cards --- */

QFrame#Card {{
    background: {p['SURFACE_2']};
    border: none;
    border-radius: 14px;
}}
QLabel#StatBig {{
    color: {p['TEXT']};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 32px;
    font-weight: 400;
}}
QLabel#StatLabel {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    padding-left: 2px;
    padding-bottom: 6px;
}}
QLabel#CardTitle {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    font-weight: 600;
}}
QLabel#CardSub {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}}
QLabel#CardSubStrong {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}

QLabel#ProfileDisplay {{
    color: {p['TEXT']};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 28px;
    font-weight: 400;
}}

QLabel#VoiceType {{
    color: {p['TEXT']};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 20px;
    font-style: italic;
    font-weight: 400;
}}

QFrame#ClickableCard {{
    background: {p['SURFACE_2']};
    border: none;
    border-radius: 14px;
}}
QFrame#ClickableCard:hover {{
    background: {p['HOVER_BG']};
}}

QPushButton#TabBtn {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    font-weight: 500;
    padding: 4px 4px 8px 4px;
    margin: 0;
}}
QPushButton#TabBtn:hover {{
    color: {p['TEXT']};
}}
QPushButton#TabBtn:checked {{
    color: {p['TEXT']};
    font-weight: 600;
    border-bottom: 2px solid {p['TEXT']};
}}

QLabel#TransformName {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    font-weight: 600;
}}

QFrame#SnippetRow {{
    background: {p['SURFACE_2']};
    border: none;
    border-radius: 12px;
}}
QFrame#SnippetRow:hover {{
    background: {p['HOVER_BG']};
}}
QLabel#SnippetTrigger {{
    color: {p['TEXT']};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    font-weight: 600;
}}
QLabel#SnippetArrow {{
    color: {p['TEXT_DIM']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}}
QLabel#SnippetExpansion {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}

QPushButton#RowEditBtn {{
    background: transparent;
    border: none;
    color: {p['TEXT_DIM']};
    font-size: 14px;
    border-radius: 14px;
}}
QPushButton#RowEditBtn:hover {{
    color: {p['TEXT']};
    background: {p['HOVER_BG']};
}}

QTextEdit#RowEdit {{
    background: {p['SURFACE']};
    border: 1px solid {p['ACCENT_DK']};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
}}

QFrame#Toast {{
    background: {p['HERO_BG']};
    border: 1px solid {p['BORDER_2']};
    border-radius: 12px;
}}
QLabel#ToastIcon {{
    color: {p['TRANSCRIBING']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}}
QLabel#ToastText {{
    color: {p['HERO_TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    background: transparent;
}}

QFrame#DictChip {{
    background: {p['SURFACE_2']};
    border: 1px solid {p['BORDER']};
    border-radius: 14px;
}}
QFrame#DictChip:hover {{
    background: {p['HOVER_BG']};
}}
QLabel#DictChipText {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: 500;
    background: transparent;
}}
QPushButton#DictChipX {{
    color: {p['TEXT_MUTED']};
    background: transparent;
    border: none;
    font-family: 'Segoe UI', sans-serif;
    font-size: 16px;
    font-weight: 400;
    padding: 0;
    margin: 0;
}}
QPushButton#DictChipX:hover {{
    color: {p['TEXT']};
}}

QFrame#ProgressTrack {{
    background: {p['BORDER']};
    border: none;
    border-radius: 2px;
}}
QFrame#ProgressFill {{
    background: {p['ACCENT_DK']};
    border: none;
    border-radius: 2px;
}}

/* --- Inputs (settings/style pages) --- */

QLineEdit, QComboBox, QSpinBox {{
    background: {p['SURFACE']};
    border: 1px solid {p['BORDER_2']};
    border-radius: 8px;
    padding: 6px 10px;
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    selection-background-color: {p['ACCENT']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {p['ACCENT_DK']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p['TEXT_MUTED']};
    width: 0;
    height: 0;
    margin-right: 8px;
}}

/* Popup list that opens beneath a QComboBox */
QComboBox QAbstractItemView {{
    background: {p['SURFACE']};
    border: 1px solid {p['BORDER_2']};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    color: {p['TEXT']};
    selection-background-color: {p['NAV_SEL_BG']};
    selection-color: {p['TEXT']};
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 6px;
    color: {p['TEXT']};
    background: transparent;
    min-height: 22px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {p['HOVER_BG']};
    color: {p['TEXT']};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {p['NAV_SEL_BG']};
    color: {p['TEXT']};
}}

QCheckBox {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {p['BORDER_2']};
    border-radius: 4px;
    background: {p['SURFACE']};
}}
QCheckBox::indicator:hover {{
    border-color: {p['TEXT_MUTED']};
}}
QCheckBox::indicator:checked {{
    background: {p['ACCENT_DK']};
    border-color: {p['ACCENT_DK']};
}}
QCheckBox::indicator:checked:hover {{
    background: {p['ACCENT']};
    border-color: {p['ACCENT']};
}}

QPushButton#PrimaryBtn {{
    background: {p['PRIMARY_BTN_BG']};
    color: {p['PRIMARY_BTN_TEXT']};
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#PrimaryBtn:hover {{ background: {p['PRIMARY_BTN_HOVER']}; }}
QPushButton#PrimaryBtn:disabled {{
    background: {p['BORDER']};
    color: {p['TEXT_DIM']};
}}

QPushButton#SecondaryBtn {{
    background: transparent;
    color: {p['TEXT']};
    border: 1px solid {p['BORDER_2']};
    border-radius: 8px;
    padding: 8px 14px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QPushButton#SecondaryBtn:hover {{ background: {p['SURFACE_2']}; }}

QLabel#FieldLabel {{
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#FieldHelp {{
    color: {p['TEXT_MUTED']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 11px;
}}

QTextEdit {{
    background: {p['SURFACE']};
    border: 1px solid {p['BORDER_2']};
    border-radius: 10px;
    padding: 10px 12px;
    color: {p['TEXT']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    selection-background-color: {p['ACCENT']};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {p['SCROLL_HANDLE']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['SCROLL_HOVER']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
