"""左侧音色库面板与模型导入弹窗。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from app.core.edge_engine import CURATED_VOICES
from app.core.voice_store import Profile, VoiceStore
from app.ui import theme


def _status_icon(profile: Profile) -> ft.Icon:
    ready, _ = profile.model_status()
    if not profile.is_rvc:
        return ft.Icon(ft.Icons.MIC_NONE, size=15, color=theme.MUTED)
    if ready:
        return ft.Icon(ft.Icons.GRAPHIC_EQ, size=15, color=theme.BRAND)
    return ft.Icon(ft.Icons.ERROR_OUTLINE, size=15, color=theme.WARN)


class VoicesPanel(ft.Container):
    def __init__(
        self,
        store: VoiceStore,
        on_select: Callable[[Profile], None],
        selected_id: str,
    ) -> None:
        self.store = store
        self.on_select = on_select
        self.selected_id = selected_id
        self.search_field = ft.TextField(
            hint_text="搜索",
            prefix_icon=ft.Icons.SEARCH,
            value="",
            bgcolor=theme.OVERLAY,
            border=theme.input_border(theme.OVERLAY, theme.BRAND),
            text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            cursor_color=theme.BRAND,
            on_change=self._on_search,
        )
        self.list_view = ft.ListView(expand=True, spacing=6, padding=ft.Padding.only(top=2))
        self.count_label = theme.t(f"{len(store.profiles)} 个", 12, theme.MUTED)
        self.import_button = ft.OutlinedButton(
            content=theme.t("导入 RVC 模型", 13),
            icon=ft.Icons.UPLOAD_FILE,
            height=40,
            style=ft.ButtonStyle(
                color=theme.MUTED,
                side=ft.BorderSide(1, theme.LINE),
                shape=ft.RoundedRectangleBorder(radius=theme.R_CTRL),
            ),
        )

        super().__init__(
            width=268,
            bgcolor=theme.CARD,
            border=ft.Border(right=ft.BorderSide(1, theme.LINE)),
            padding=ft.Padding.only(left=16, top=20, right=16, bottom=16),
            content=ft.Column(
                spacing=14,
                expand=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            theme.t("音色库", 16, theme.TEXT, ft.FontWeight.W_600),
                            self.count_label,
                        ],
                    ),
                    self.search_field,
                    self.list_view,
                    self.import_button,
                ],
            ),
        )
        self._rebuild()

    def _on_search(self, e: ft.Event) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        keyword = (self.search_field.value or "").strip().lower()
        self.list_view.controls = [
            self._item(p)
            for p in self.store.profiles
            if not keyword or keyword in p.name.lower() or keyword in p.desc.lower()
        ]
        self.count_label.value = f"{len(self.store.profiles)} 个"
        try:
            self.update()
        except RuntimeError:
            pass

    def _item(self, profile: Profile) -> ft.Container:
        selected = profile.id == self.selected_id
        ready, reason = profile.model_status()
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=ft.BorderRadius.all(theme.R_CTRL),
            bgcolor=theme.BRAND_SOFT if selected else None,
            border=ft.Border.all(1, theme.BRAND if selected else theme.LINE_SOFT),
            ink=True,
            on_click=lambda e: self.on_select(profile),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        bgcolor=theme.OVERLAY,
                        border_radius=ft.BorderRadius.all(17),
                        alignment=ft.Alignment.CENTER,
                        content=theme.t(
                            profile.initial,
                            14,
                            theme.BRAND if selected else theme.MUTED,
                            ft.FontWeight.W_600,
                        ),
                    ),
                    ft.Column(
                        spacing=1,
                        expand=True,
                        controls=[
                            theme.t(profile.name, 14, theme.TEXT, ft.FontWeight.W_500),
                            theme.t(
                                reason if profile.is_rvc else profile.desc,
                                11,
                                theme.WARN if profile.is_rvc and not ready else theme.MUTED,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                    ),
                    _status_icon(profile),
                ],
            ),
        )

    def set_selected(self, profile_id: str) -> None:
        self.selected_id = profile_id
        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()


class ImportModelDialog(ft.AlertDialog):
    """选定 .pth 之后的补充信息弹窗，同目录下的 .index 会自动配对。"""

    def __init__(
        self,
        page: ft.Page,
        model_path: Path,
        on_save: Callable[[str, str, Path], None],
    ) -> None:
        self.model_path = model_path
        self.on_save = on_save

        self.name_field = ft.TextField(
            label="音色名称",
            value=model_path.stem,
            bgcolor=theme.OVERLAY,
            border=theme.input_border(),
            text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=12),
        )
        self.base_dropdown = ft.Dropdown(
            label="底声（决定韵律）",
            value="zh-CN-YunxiNeural",
            bgcolor=theme.OVERLAY,
            border=theme.input_border(),
            text_size=13,
            options=[
                ft.DropdownOption(key=vid, text=f"{name} · {desc}")
                for vid, name, desc in CURATED_VOICES[:8]
            ],
        )
        self.save_button = ft.FilledButton(
            content=theme.t("导入并保存", 13, theme.BG, ft.FontWeight.W_600),
            bgcolor=theme.BRAND,
            on_click=lambda e: self._submit(),
        )
        self._page = page

        super().__init__(
            title=theme.t("导入 RVC 模型", 16, theme.TEXT, ft.FontWeight.W_600),
            bgcolor=theme.CARD,
            content=ft.Column(
                width=420,
                spacing=14,
                tight=True,
                controls=[
                    theme.t(f"模型：{model_path.name}", 12, theme.MUTED),
                    self.name_field,
                    self.base_dropdown,
                    theme.t("同目录下的 .index 特征文件会自动一起导入", 11, theme.DIM),
                ],
            ),
            actions=[
                ft.TextButton(
                    content=theme.t("取消", 13, theme.MUTED),
                    on_click=lambda e: page.pop_dialog(),
                ),
                self.save_button,
            ],
        )

    def _submit(self) -> None:
        name = (self.name_field.value or "").strip() or self.model_path.stem
        if not name:
            return
        self.on_save(name, self.base_dropdown.value or "zh-CN-YunxiNeural", self.model_path)
        self._page.pop_dialog()
