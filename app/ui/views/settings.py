"""设置弹窗：运行环境、输出目录与缓存。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from app import config
from app.core.audio_utils import ffmpeg_path
from app.ui import theme


def _device_summary() -> str:
    """不导入 torch，避免打开设置时卡顿。"""
    try:
        import subprocess

        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode == 0 and out.stdout.strip():
            return f"{out.stdout.strip()} · CPU 模式"
    except Exception:
        pass
    return "CPU 模式（可选装 CUDA 版 torch 提速）"


def _cache_size() -> str:
    total = 0
    if config.CACHE_DIR.exists():
        for path in config.CACHE_DIR.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    return f"{total / 1024**2:.1f} MB"


class SettingsDialog(ft.AlertDialog):
    def __init__(
        self,
        page: ft.Page,
        on_open_output: Callable[[], None],
        on_clear_cache: Callable[[], None],
    ) -> None:
        self.on_clear_cache = on_clear_cache
        self.cache_label = theme.t(_cache_size(), 12, theme.MUTED)
        try:
            ffmpeg = ffmpeg_path()
            ffmpeg_text = Path(ffmpeg).name
            ffmpeg_color = theme.BRAND
        except Exception:
            ffmpeg_text = "未找到 ffmpeg"
            ffmpeg_color = theme.DANGER

        rows = ft.Column(
            width=460,
            spacing=12,
            tight=True,
            controls=[
                self._row("运行设备", theme.t(_device_summary(), 12, theme.MUTED)),
                self._row("ffmpeg", theme.t(ffmpeg_text, 12, ffmpeg_color)),
                self._row(
                    "输出目录",
                    ft.Row(
                        spacing=8,
                        controls=[
                            theme.t(str(config.OUTPUT_DIR), 12, theme.MUTED),
                            ft.IconButton(
                                icon=ft.Icons.FOLDER_OPEN,
                                icon_size=16,
                                icon_color=theme.BRAND,
                                tooltip="打开输出目录",
                                on_click=lambda e: on_open_output(),
                            ),
                        ],
                    ),
                ),
                self._row(
                    "临时缓存",
                    ft.Row(
                        spacing=8,
                        controls=[
                            self.cache_label,
                            ft.TextButton(
                                content=theme.t("清理", 12, theme.MUTED),
                                on_click=lambda e: self._clear(),
                            ),
                        ],
                    ),
                ),
                ft.Container(
                    padding=ft.Padding.all(12),
                    bgcolor=theme.OVERLAY,
                    border_radius=ft.BorderRadius.all(theme.R_CTRL),
                    content=theme.t(
                        "RVC 音色需要 .pth 模型；首次转换会自动下载 rmvpe 与 HuBERT 预训练模型。",
                        11,
                        theme.MUTED,
                    ),
                ),
            ],
        )
        super().__init__(
            title=theme.t("设置", 16, theme.TEXT, ft.FontWeight.W_600),
            bgcolor=theme.CARD,
            content=rows,
            actions=[
                ft.TextButton(
                    content=theme.t("关闭", 13, theme.MUTED),
                    on_click=lambda e: page.pop_dialog(),
                )
            ],
        )

    @staticmethod
    def _row(label: str, value: ft.Control) -> ft.Row:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[theme.t(label, 12, theme.MUTED), value],
        )

    def _clear(self) -> None:
        self.on_clear_cache()
        self.cache_label.value = _cache_size()
        self.cache_label.update()
