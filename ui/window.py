"""Murmur desktop window - sidebar nav + stacked content + optional right rail.

Visual reference: Wispr Flow's Home page. We keep the same shape but the
content is Murmur's (free, offline-first, Groq polish optional).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal as _Signal
# Re-export for backward use; primary import name remains `Signal` below.
Signal = _Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .toast import Toast
from .pages.dictionary_page import DictionaryPage
from .pages.home import HomePage
from .pages.insights import InsightsPage
from .pages.scratchpad import ScratchpadPage
from .pages.settings_page import SettingsPage
from .pages.snippets_page import SnippetsPage
from .pages.style_page import StylePage
from .pages.transforms_page import TransformsPage


# Segoe Fluent Icons (Win 11) - fall back to Segoe MDL2 Assets (Win 10+).
_ICON_HOME       = ""
_ICON_INSIGHTS   = ""
_ICON_DICTIONARY = ""
_ICON_SNIPPETS   = ""
_ICON_STYLE      = ""
_ICON_TRANSFORMS = ""
_ICON_SCRATCHPAD = ""
_ICON_SETTINGS   = ""
_ICON_HELP       = ""


def _glyph_icon(glyph: str, *, size: int = 18, color: str = theme.TEXT) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    font = QFont("Segoe Fluent Icons", int(size * 0.62))
    if not QFontInfo(font).family().lower().startswith("segoe fluent"):
        font = QFont("Segoe MDL2 Assets", int(size * 0.62))
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(pix.rect(), Qt.AlignCenter, glyph)
    p.end()
    return QIcon(pix)


def _draw_murmur_mark(
    p: QPainter,
    *,
    size: float,
    stroke_color: QColor,
    dot_color: QColor,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> None:
    """Murmur's signature mark - a single soft sine cycle radiating to the
    right of a small focal dot.

    Reading:
      - dot  = the speaking source (you)
      - wave = the murmur travelling outward - one gentle cycle, not the
               loud full-amplitude equaliser bars Wispr uses

    Drawing tuned to stay sharp at small icon sizes: chunky stroke
    (~12% of size), generous dot radius, smooth path."""
    import math
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainterPath, QPen

    s = size
    dot_r = s * 0.12
    dot_cx = offset_x + s * 0.22
    dot_cy = offset_y + s * 0.50

    p.setPen(Qt.NoPen)
    p.setBrush(dot_color)
    p.drawEllipse(QPointF(dot_cx, dot_cy), dot_r, dot_r)

    stroke = max(2.0, s * 0.12)
    pen = QPen(stroke_color, stroke)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    left_x = dot_cx + dot_r + stroke * 0.5
    right_x = offset_x + s - stroke * 0.5
    mid_y = dot_cy
    amplitude = s * 0.22

    path = QPainterPath()
    samples = 96
    for i in range(samples + 1):
        t = i / samples
        x = left_x + t * (right_x - left_x)
        # One full cycle: up then down, ending at midline.
        y = mid_y - amplitude * math.sin(t * 2 * math.pi)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    p.drawPath(path)


def make_app_icon() -> QIcon:
    """Murmur app icon - loaded from the multi-size Murmur.ico baked by
    scripts/export_icon.py (LANCZOS-downsampled from the 1254px source)."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(here, "Murmur.ico")
    if os.path.exists(ico_path):
        return QIcon(ico_path)
    # Fallback to the source PNG if the .ico hasn't been built yet.
    return QIcon(os.path.join(here, "assets", "WhiteIcon.png"))


_BRAND_SILHOUETTE: QPixmap | None = None


def _brand_pixmap(
    size: int = 26,
    *,
    stroke: QColor | None = None,
    dot: QColor | None = None,
) -> QPixmap:
    """Sidebar brand glyph - the head silhouette baked from WhiteIcon.png
    (transparent background so it floats on either light or dark surface).

    The legacy stroke/dot kwargs are accepted but ignored - the silhouette
    carries its own tonality from the source art and tinting it would lose
    the line-art shading."""
    global _BRAND_SILHOUETTE
    if _BRAND_SILHOUETTE is None:
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sil_path = os.path.join(here, "assets", "HeadSilhouette.png")
        _BRAND_SILHOUETTE = QPixmap(sil_path)
    if _BRAND_SILHOUETTE.isNull():
        # Asset missing - fall back to a transparent square so layouts
        # don't collapse.
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        return pix
    return _BRAND_SILHOUETTE.scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


@dataclass(frozen=True)
class _NavSpec:
    key: str
    label: str
    glyph: str
    enabled: bool = True
    coming_soon: bool = False


_PRIMARY_NAV: list[_NavSpec] = [
    _NavSpec("home",       "Home",       _ICON_HOME),
    _NavSpec("insights",   "Insights",   _ICON_INSIGHTS),
    _NavSpec("dictionary", "Dictionary", _ICON_DICTIONARY),
    _NavSpec("snippets",   "Snippets",   _ICON_SNIPPETS),
    _NavSpec("style",      "Style",      _ICON_STYLE),
    _NavSpec("transforms", "Transforms", _ICON_TRANSFORMS),
    _NavSpec("scratchpad", "Scratchpad", _ICON_SCRATCHPAD),
]

_BOTTOM_NAV: list[_NavSpec] = [
    _NavSpec("settings", "Settings", _ICON_SETTINGS),
    _NavSpec("help",     "Help",     _ICON_HELP),
]


# Pages that should display the right rail (stats + voice profile).
_RAIL_PAGES = {"home", "insights"}


class _ClickableCard(QFrame):
    """QFrame that emits `clicked` on left-mouse-press. The whole card
    surface is the click target."""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("ClickableCard")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _make_nav_button(spec: _NavSpec) -> QPushButton:
    btn = QPushButton(f"  {spec.label}")
    btn.setObjectName("NavItem")
    btn.setCheckable(spec.enabled)
    btn.setEnabled(spec.enabled)
    btn.setIcon(_glyph_icon(spec.glyph, color=theme.TEXT_DIM if not spec.enabled else theme.TEXT))
    btn.setIconSize(QSize(16, 16))
    btn.setCursor(Qt.PointingHandCursor if spec.enabled else Qt.ArrowCursor)

    if spec.coming_soon:
        # Small "SOON" tag, right-aligned, no background - minimalist.
        layout = QHBoxLayout(btn)
        layout.setContentsMargins(34, 0, 12, 0)
        layout.addStretch(1)
        tag = QLabel("SOON")
        tag.setObjectName("ComingSoon")
        tag.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(tag)
    return btn


class _Sidebar(QWidget):
    """Left column - brand, primary nav, usage card, bottom nav."""

    navigated = Signal(str)  # key

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(theme.SIDEBAR_W)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 22, 14, 18)
        outer.setSpacing(2)

        # Brand row - small bar-chart glyph + serif wordmark + outlined badge.
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.setContentsMargins(4, 0, 0, 0)
        glyph = QLabel()
        glyph.setPixmap(_brand_pixmap(26))
        glyph.setFixedSize(26, 26)
        self._brand_glyph_label = glyph  # kept so apply_theme can refresh it
        brand = QLabel("Murmur")
        brand.setObjectName("Brand")
        badge = QLabel("Free")
        badge.setObjectName("BrandBadge")
        brand_row.addWidget(glyph)
        brand_row.addWidget(brand)
        brand_row.addSpacing(2)
        brand_row.addWidget(badge)
        brand_row.addStretch(1)
        outer.addLayout(brand_row)
        outer.addSpacing(28)

        # Primary nav buttons
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for spec in _PRIMARY_NAV:
            btn = _make_nav_button(spec)
            outer.addWidget(btn)
            if spec.enabled:
                self._group.addButton(btn)
                btn.clicked.connect(lambda _checked=False, k=spec.key: self.navigated.emit(k))
            self._buttons[spec.key] = btn

        outer.addStretch(1)

        # Usage card (status + tip)
        card = QFrame()
        card.setObjectName("UsageCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 12, 14, 12)
        card_l.setSpacing(4)
        title = QLabel("Unlimited dictation")
        title.setObjectName("UsageTitle")
        body = QLabel("Runs on your machine — no quotas, no account.")
        body.setObjectName("UsageBody")
        body.setWordWrap(True)
        card_l.addWidget(title)
        card_l.addWidget(body)
        outer.addWidget(card)
        outer.addSpacing(6)

        # Bottom nav
        for spec in _BOTTOM_NAV:
            btn = _make_nav_button(spec)
            outer.addWidget(btn)
            if spec.enabled:
                self._group.addButton(btn)
                btn.clicked.connect(lambda _checked=False, k=spec.key: self.navigated.emit(k))
            self._buttons[spec.key] = btn

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn and btn.isEnabled():
            btn.setChecked(True)

    def _refresh_brand_glyph(self) -> None:
        """Rebuild the brand pixmap so it picks up the active palette."""
        if hasattr(self, "_brand_glyph_label"):
            self._brand_glyph_label.setPixmap(_brand_pixmap(26))


class _RightRail(QWidget):
    """Right column - stats + voice profile. Built once, refreshed on demand."""

    voice_profile_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("RightRail")
        self.setFixedWidth(theme.RIGHTRAIL_W)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 76, 26, 22)
        outer.setSpacing(16)

        # ---- Stats card ----
        stats_card = QFrame()
        stats_card.setObjectName("Card")
        sl = QVBoxLayout(stats_card)
        sl.setContentsMargins(22, 22, 22, 22)
        sl.setSpacing(14)

        def stat_row(big: QLabel, lbl: QLabel) -> QWidget:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)
            h.addWidget(big, 0, Qt.AlignBottom)
            h.addWidget(lbl, 0, Qt.AlignBottom)
            h.addStretch(1)
            return w

        self._stat_words = QLabel("0")
        self._stat_words.setObjectName("StatBig")
        words_lbl = QLabel("total words")
        words_lbl.setObjectName("StatLabel")
        sl.addWidget(stat_row(self._stat_words, words_lbl))

        self._stat_wpm = QLabel("0")
        self._stat_wpm.setObjectName("StatBig")
        wpm_lbl = QLabel("wpm")
        wpm_lbl.setObjectName("StatLabel")
        sl.addWidget(stat_row(self._stat_wpm, wpm_lbl))

        self._stat_streak = QLabel("0")
        self._stat_streak.setObjectName("StatBig")
        streak_lbl = QLabel("day streak")
        streak_lbl.setObjectName("StatLabel")
        sl.addWidget(stat_row(self._stat_streak, streak_lbl))

        outer.addWidget(stats_card)

        # ---- Voice Profile card (clickable teaser only - full data on detail page) ----
        vp_card = _ClickableCard()
        vp_card.clicked.connect(self.voice_profile_clicked.emit)
        vp_l = QVBoxLayout(vp_card)
        vp_l.setContentsMargins(22, 22, 22, 22)
        vp_l.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        vp_title = QLabel("Voice Profile")
        vp_title.setObjectName("CardTitle")
        title_row.addWidget(vp_title)
        title_row.addStretch(1)
        chev = QLabel("›")
        chev.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 18px; "
                           f"font-weight: 400;")
        title_row.addWidget(chev, 0, Qt.AlignTop)
        vp_l.addLayout(title_row)
        vp_l.addSpacing(6)

        # Bottom row: type + description on the left, wave glyph on the right.
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)
        self._vp_type = QLabel("—")
        self._vp_type.setObjectName("VoiceType")
        self._vp_type.setWordWrap(True)
        text_col.addWidget(self._vp_type)

        self._vp_desc = QLabel("—")
        self._vp_desc.setObjectName("CardSub")
        self._vp_desc.setWordWrap(True)
        text_col.addWidget(self._vp_desc)
        text_col.addStretch(1)
        body_row.addLayout(text_col, 1)

        # Subtle wave glyph on the right - Murmur's mark, muted grey.
        glyph = QLabel()
        glyph.setFixedSize(56, 56)
        glyph.setAttribute(Qt.WA_TransparentForMouseEvents)
        body_row.addWidget(glyph, 0, Qt.AlignVCenter)
        self._vp_glyph_label = glyph
        self._refresh_vp_glyph()

        vp_l.addLayout(body_row)

        outer.addWidget(vp_card)
        outer.addStretch(1)

    def _refresh_vp_glyph(self) -> None:
        """Re-render the right-rail glyph using the current theme palette."""
        if not hasattr(self, "_vp_glyph_label"):
            return
        self._vp_glyph_label.setPixmap(_brand_pixmap(
            56,
            stroke=QColor(theme.TEXT_DIM),
            dot=QColor(theme.ACCENT),
        ))

    def apply_theme(self) -> None:
        """Called by MurmurWindow after the palette flips."""
        self._refresh_vp_glyph()

    def refresh(self) -> None:
        import history
        s = history.stats()
        p = history.profile()
        self._stat_words.setText(_format_count(s.total_words))
        self._stat_wpm.setText(str(int(round(s.avg_wpm))))
        self._stat_streak.setText(str(s.day_streak))

        vt_name, vt_desc = history.voice_type(s, p)
        self._vp_type.setText(vt_name)
        self._vp_desc.setText(vt_desc)


def _format_count(n: int) -> str:
    if n >= 100_000:
        return f"{n / 1000:.0f}K"
    if n >= 10_000:
        return f"{n / 1000:.1f}K"
    return str(n)


class _HelpPage(QWidget):
    def __init__(self, hotkey_label: str):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(40, 40, 40, 40)
        l.setSpacing(14)

        title = QLabel("How to use Murmur")
        title.setObjectName("Greeting")
        l.addWidget(title)

        bullets = [
            f"• Hold {hotkey_label} anywhere in Windows — speak — release to transcribe.",
            "• Or click the small bar at the bottom-center of your screen to start, ✓ to finish, ✗ to cancel.",
            "• Your text is pasted at the cursor in any app (Gmail, VS Code, Slack, Discord, browsers).",
            "• Speech recognition runs on this machine by default, and nothing is sent anywhere.",
            "• Settings has two Groq switches, both off until you turn them on: cloud transcription uploads your recorded audio, AI polish uploads the transcribed text.",
            "• Closing this window keeps Murmur running in the tray. Quit from the tray's right-click menu.",
        ]
        for line in bullets:
            lab = QLabel(line)
            lab.setObjectName("HeroBody")
            lab.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px;")
            lab.setWordWrap(True)
            l.addWidget(lab)

        l.addStretch(1)


class MurmurWindow(QMainWindow):
    """Top-level desktop window. Hides to tray on close (controller decides)."""

    page_changed = Signal(str)
    close_requested = Signal()       # X clicked - controller hides us
    settings_changed = Signal()      # settings page saved
    transcript_corrected = Signal(int, str, str)  # row_id, original, corrected

    def __init__(
        self,
        cfg,
        save_settings: Callable[[object], None],
        hotkey_label: str,
    ):
        super().__init__()
        self.setWindowTitle("Murmur")
        self.setWindowIcon(make_app_icon())
        self.setMinimumSize(1100, 680)
        self.resize(1240, 760)
        self.setStyleSheet(theme.STYLESHEET)
        self._has_been_shown = False

        central = QWidget()
        central.setObjectName("Root")
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self._sidebar = _Sidebar()
        self._sidebar.navigated.connect(self._go)
        h.addWidget(self._sidebar)

        # Main content area
        main_wrap = QWidget()
        main_wrap.setObjectName("MainArea")
        mw_l = QHBoxLayout(main_wrap)
        mw_l.setContentsMargins(0, 0, 0, 0)
        mw_l.setSpacing(0)

        self._stack = QStackedWidget()
        mw_l.addWidget(self._stack, 1)

        self._rail = _RightRail()
        self._rail.voice_profile_clicked.connect(self._open_voice_tab)
        mw_l.addWidget(self._rail)

        h.addWidget(main_wrap, 1)
        self.setCentralWidget(central)

        # Build pages
        self._home = HomePage(hotkey_label=hotkey_label)
        # Forward correction edits up to the main controller via a window-level signal.
        self._home.transcript_corrected.connect(self.transcript_corrected.emit)
        self._insights = InsightsPage()
        self._dictionary = DictionaryPage(cfg=cfg, save=lambda s: self._on_save(s, save_settings))
        self._snippets = SnippetsPage(cfg=cfg, save=lambda s: self._on_save(s, save_settings))
        self._transforms = TransformsPage(cfg=cfg, save=lambda s: self._on_save(s, save_settings))
        self._scratch = ScratchpadPage()
        self._style = StylePage(cfg=cfg, save=lambda s: self._on_save(s, save_settings))
        self._settings = SettingsPage(cfg=cfg, save=lambda s: self._on_save(s, save_settings))
        self._help = _HelpPage(hotkey_label=hotkey_label)

        self._pages: dict[str, QWidget] = {
            "home":       self._home,
            "insights":   self._insights,
            "dictionary": self._dictionary,
            "snippets":   self._snippets,
            "transforms": self._transforms,
            "scratchpad": self._scratch,
            "style":      self._style,
            "settings":   self._settings,
            "help":       self._help,
        }
        for w in self._pages.values():
            self._stack.addWidget(w)

        self._go("home")

        # Shared toast widget - floats above everything, used for "Learned X".
        self._toast = Toast(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the toast centred at the top across resizes.
        if hasattr(self, "_toast") and self._toast.isVisible():
            self._toast._position()

    def show_toast(self, text: str) -> None:
        if hasattr(self, "_toast"):
            self._toast.show_message(text)

    # ---- navigation -------------------------------------------------------

    def _go(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._sidebar.select(key)
        self._rail.setVisible(key in _RAIL_PAGES)
        if key == "home":
            self._home.refresh()
        if key == "insights":
            self._insights.refresh()
        if key in _RAIL_PAGES:
            self._rail.refresh()
        self.page_changed.emit(key)

    def _open_voice_tab(self) -> None:
        self._go("insights")
        self._insights.show_tab("voice")

    def apply_theme(self) -> None:
        """Called after `theme.set_mode(...)` to refresh painted glyphs.

        The QApplication stylesheet is updated by the controller; here we
        just rebuild any pixmaps that captured palette colours at draw
        time so they pick up the new palette."""
        self.setStyleSheet(theme.STYLESHEET)
        self._sidebar._refresh_brand_glyph()
        self._rail.apply_theme()
        self.update()

    def go(self, key: str) -> None:
        self._go(key)

    # ---- external API for the controller ---------------------------------

    def notify_new_dictation(self) -> None:
        """Called after a dictation gets written to history."""
        if self._stack.currentWidget() is self._home:
            self._home.refresh()
        if self._stack.currentWidget() is self._insights:
            self._insights.refresh()
        if self._rail.isVisible():
            self._rail.refresh()

    def show_and_raise(self) -> None:
        # First-ever show: center on the primary screen so it can't land off-screen.
        if not self._has_been_shown:
            self._has_been_shown = True
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                w = min(self.width(), geo.width())
                h = min(self.height(), geo.height())
                self.resize(w, h)
                self.move(
                    geo.x() + max(0, (geo.width() - w) // 2),
                    geo.y() + max(0, (geo.height() - h) // 2),
                )
        # Unminimize if needed.
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        # Windows blocks SetForegroundWindow when called from another window's
        # focus context (tray menu). Use the AttachThreadInput dance to bypass.
        self._force_foreground_windows()

    def _force_foreground_windows(self) -> None:
        import sys
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32

            SW_RESTORE = 9
            SW_SHOW = 5
            hwnd = int(self.winId())
            if not hwnd:
                return

            fg = u32.GetForegroundWindow()
            cur_thread = k32.GetCurrentThreadId()
            fg_thread = u32.GetWindowThreadProcessId(fg, 0) if fg else 0

            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = bool(u32.AttachThreadInput(fg_thread, cur_thread, True))

            u32.ShowWindow(hwnd, SW_RESTORE)
            u32.ShowWindow(hwnd, SW_SHOW)
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            u32.SetFocus(hwnd)

            if attached:
                u32.AttachThreadInput(fg_thread, cur_thread, False)
        except Exception as exc:
            print(f"[window] force-foreground failed: {exc}")

    # ---- closing -> hide-to-tray -----------------------------------------

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        self.close_requested.emit()

    # ---- settings save callback ------------------------------------------

    def _on_save(self, new_cfg, save_settings: Callable[[object], None]) -> None:
        save_settings(new_cfg)
        self.settings_changed.emit()
