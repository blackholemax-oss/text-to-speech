"""视觉规范：暗色、低饱和背景 + 荧光薄荷绿强调色。"""

from __future__ import annotations

import flet as ft

BG = "#0E1014"
CARD = "#151920"
OVERLAY = "#1C222B"
LINE = "#262D38"
LINE_SOFT = "#1D242D"
TEXT = "#E8ECF1"
MUTED = "#8B96A8"
DIM = "#5D6879"
BRAND = "#3CE08C"
BRAND_SOFT = "#16291F"
DANGER = "#F0736D"
WARN = "#E8B75C"

FONT = "Microsoft YaHei UI"
R_CARD = 16
R_CTRL = 10


def t(
    value: str,
    size: int = 14,
    color: str = TEXT,
    weight: ft.FontWeight = ft.FontWeight.W_400,
    **kwargs,
) -> ft.Text:
    return ft.Text(value, size=size, color=color, weight=weight, font_family=FONT, **kwargs)


def card(content: ft.Control, padding: int = 16, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border=ft.Border.all(1, LINE),
        border_radius=ft.BorderRadius.all(R_CARD),
        padding=ft.Padding.all(padding),
        **kwargs,
    )


def input_border(idle: str = LINE, focused: str = BRAND, radius: int = R_CTRL) -> dict:
    """Flet 1.0 的输入边框用 ControlState 字典表达。"""
    return {
        ft.ControlState.DEFAULT: ft.OutlineInputBorder(
            side=ft.BorderSide(1, idle),
            border_radius=ft.BorderRadius.all(radius),
        ),
        ft.ControlState.FOCUSED: ft.OutlineInputBorder(
            side=ft.BorderSide(1, focused),
            border_radius=ft.BorderRadius.all(radius),
        ),
    }


def build_theme() -> ft.Theme:
    return ft.Theme(
        font_family=FONT,
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=BRAND,
            on_primary=BG,
            surface=CARD,
            on_surface=TEXT,
            secondary=BRAND,
            on_secondary=BG,
            outline=LINE,
            error=DANGER,
        ),
    )
