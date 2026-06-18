"""Shared visual and layout constants for the desktop UI."""

from __future__ import annotations

import flet as ft

# ---------------------------------------------------------
# Modern Minimalist Palette
# ---------------------------------------------------------
BG = "#0B0F12"          
PANEL = "#13181E"       
TEXT = "#F3F4F6"        
MUTED = "#6B7280"       
ACCENT = "#34D399"      
ACCENT_DIM = "#102A22"  
WARN = "#1e3229"        
BORDER = "#232B35"      
PANEL_ALT = "#1A202C"   
PANEL_SOFT = "#0f1714"  
TEXT_SOFT = "#9CA3AF"   
DIVIDER = "#1C232B"     
SURFACE = "#10161C"
SURFACE_RAISED = "#151D24"

# ---------------------------------------------------------
# Breakpoints and layout (Required by app)
# ---------------------------------------------------------
COMPACT_BREAKPOINT = 1024.0
SIDEBAR_MIN_WIDTH = 220.0
SIDEBAR_MAX_WIDTH = 300.0
SIDEBAR_WIDTH_RATIO = 0.22
SIDEBAR_RAIL_WIDTH = 72.0
SIDEBAR_MENU_BUTTON_WIDTH = 44.0

CARD_COMPACT_MIN = 260.0
CARD_COMPACT_MAX = 460.0
CARD_COMPACT_MARGIN = 48.0
CARD_WIDE_MIN = 320.0
CARD_WIDE_MAX = 520.0
CARD_WIDE_GUTTER = 120.0
CARD_WIDE_RATIO = 0.58
CARD_CANVAS_INSET = 60.0

FILMSTRIP_TILE_COMPACT = 48.0
FILMSTRIP_TILE_DESKTOP = 56.0
FILMSTRIP_TEXT_COMPACT = 20
FILMSTRIP_TEXT_DESKTOP = 24
FILMSTRIP_GAP = 10.0
FILMSTRIP_VISIBLE_COMPACT = 4
FILMSTRIP_VISIBLE_DESKTOP = 5
FILMSTRIP_FADE_COMPACT = 20.0
FILMSTRIP_FADE_DESKTOP = 28.0

# ---------------------------------------------------------
# Web-inspired Layout Variables
# ---------------------------------------------------------
PAGE_PADDING = 24
PANEL_PADDING = 20
CARD_PADDING = 24
CARD_EMPTY_PADDING = 24
SECTION_GAP = 16
SMALL_GAP = 12
TOPBAR_PADDING_H = 14
TOPBAR_PADDING_V = 10

SECTION_TITLE_SIZE = 22
CARD_RADIUS = 12
PANEL_RADIUS = 12
CONTROL_RADIUS = 8
METRIC_PADDING = 14
METRIC_VALUE_SIZE = 28
METRIC_LABEL_SIZE = 11

HOME_CARD_TITLE_SIZE = 42
HOME_HINT_SIZE = 13
KANJI_IDLE_SIZE = 64
KANJI_FOCUS_SIZE = 72
KANJI_EMPTY_SIZE = 42

DURATION_WIDTH_IDLE = 90
DURATION_WIDTH_FOCUS = 88
CALENDAR_HEIGHT = 320
IMPORT_LOG_HEIGHT = 160
TOOLTIP_WAIT_MS = 100

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def border_all(color: str, width: float = 1) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, right=side, bottom=side, left=side)

def border_tb(color: str, width: float = 1) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, bottom=side)

def pad_symmetric(horizontal: float = 0, vertical: float = 0) -> ft.Padding:
    return ft.Padding(left=horizontal, top=vertical, right=horizontal, bottom=vertical)

def pad_only(*, left: float = 0, top: float = 0, right: float = 0, bottom: float = 0) -> ft.Padding:
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)

def align(x: float, y: float) -> ft.Alignment:
    return ft.Alignment(x=x, y=y)

def get_elevation_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(blur_radius=24, color="#00000055", offset=ft.Offset(0, 10))
