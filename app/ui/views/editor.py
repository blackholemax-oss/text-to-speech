"""主编辑区：文本输入、参数带与底部操作栏。"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.edge_engine import segment_text
from app.core.pipeline import GenerateParams, GenerationResult
from app.core.voice_store import Profile
from app.ui import theme

_STAGE_LABELS = {
    "synthesize": "合成语音",
    "convert_audio": "转码",
    "rvc": "音色转换",
    "merge": "拼接与归一",
}


class EditorView(ft.Container):
    def __init__(
        self,
        on_generate: Callable[[], None],
        on_preview: Callable[[], None],
        on_export: Callable[[], None],
        on_settings: Callable[[], None],
    ) -> None:
        self.on_generate = on_generate
        self.on_preview = on_preview
        self.on_export = on_export
        self.on_settings = on_settings
        self.result: GenerationResult | None = None

        self.profile: Profile | None = None
        self.busy = False

        self.chip_label = theme.t("未选择音色", 12, theme.MUTED)
        self.chip_dot = ft.Container(width=6, height=6, border_radius=ft.BorderRadius.all(3), bgcolor=theme.MUTED)
        self.chip = ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=ft.BorderRadius.all(8),
            border=ft.Border.all(1, theme.LINE),
            bgcolor=theme.OVERLAY,
            content=ft.Row(spacing=6, controls=[self.chip_dot, self.chip_label]),
        )

        self.char_label = theme.t("0 字", 12, theme.MUTED)
        self.text_field = ft.TextField(
            multiline=True,
            expand=True,
            min_lines=8,
            border=theme.input_border(theme.OVERLAY, theme.LINE, 10),
            bgcolor=theme.OVERLAY,
            content_padding=ft.Padding.all(16),
            text_size=15,
            color=theme.TEXT,
            cursor_color=theme.BRAND,
            selection_color="#2E5C46",
            hint_text="把要朗读的文字粘贴到这里。支持长文，系统会按标点自动分段合成。",
            hint_style=ft.TextStyle(color=theme.MUTED, size=14),
            on_change=self._on_text_change,
        )

        self.rate_slider, self.rate_value = self._slider_row(-30, 30, 0, 60, "%")
        self.pitch_slider, self.pitch_value = self._slider_row(-12, 12, 0, 24, " 半音")
        self.index_slider, self.index_value = self._slider_row(0, 100, 75, 20, "%")
        self.protect_slider, self.protect_value = self._slider_row(0, 50, 33, 25, "%")

        self.param_sliders = (self.pitch_slider, self.index_slider, self.protect_slider)
        self.rate_card = self._param_card("语速", self.rate_slider, self.rate_value)
        self.pitch_card = self._param_card("变调", self.pitch_slider, self.pitch_value, "仅 RVC 音色生效")
        self.index_card = self._param_card("相似度", self.index_slider, self.index_value, "仅 RVC 音色生效")
        self.protect_card = self._param_card("保护度", self.protect_slider, self.protect_value, "仅 RVC 音色生效")
        self.rvc_cards = [self.pitch_card, self.index_card, self.protect_card]

        self.progress_label = theme.t("", 12, theme.MUTED)
        self.progress_bar = ft.ProgressBar(
            value=0,
            height=3,
            color=theme.BRAND,
            bgcolor=theme.LINE,
            border_radius=ft.BorderRadius.all(2),
            visible=False,
        )
        self.status_label = theme.t("就绪 · 输出目录 output/", 12, theme.MUTED)

        self.preview_button = ft.OutlinedButton(
            content=theme.t("试听", 13),
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            height=42,
            disabled=True,
            style=ft.ButtonStyle(
                color=theme.MUTED,
                side=ft.BorderSide(1, theme.LINE),
                shape=ft.RoundedRectangleBorder(radius=theme.R_CTRL),
                padding=ft.Padding.symmetric(horizontal=16),
            ),
            on_click=lambda e: self.on_preview(),
        )
        self.export_button = ft.OutlinedButton(
            content=theme.t("导出", 13),
            icon=ft.Icons.SAVE_ALT_ROUNDED,
            height=42,
            disabled=True,
            style=ft.ButtonStyle(
                color=theme.MUTED,
                side=ft.BorderSide(1, theme.LINE),
                shape=ft.RoundedRectangleBorder(radius=theme.R_CTRL),
                padding=ft.Padding.symmetric(horizontal=16),
            ),
            on_click=lambda e: self.on_export(),
        )
        self.generate_button = ft.FilledButton(
            content=theme.t("生成语音", 14, theme.BG, ft.FontWeight.W_600),
            icon=ft.Icons.GRAPHIC_EQ_ROUNDED,
            height=44,
            width=156,
            style=ft.ButtonStyle(
                bgcolor=theme.BRAND,
                color=theme.BG,
                shape=ft.RoundedRectangleBorder(radius=theme.R_CTRL),
            ),
            on_click=lambda e: self.on_generate(),
        )

        header = ft.Container(
            padding=ft.Padding.only(left=24, right=24, top=20, bottom=12),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=3,
                        controls=[
                            theme.t("文字转语音", 20, theme.TEXT, ft.FontWeight.W_600),
                            theme.t("Edge 韵律 · RVC 音色克隆", 12, theme.MUTED),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        controls=[
                            self.chip,
                            ft.IconButton(
                                icon=ft.Icons.TUNE,
                                icon_size=18,
                                icon_color=theme.MUTED,
                                tooltip="设置",
                                on_click=lambda e: self.on_settings(),
                            ),
                        ],
                    ),
                ],
            ),
        )

        editor_card = theme.card(
            ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            theme.t("文本", 12, theme.MUTED),
                            self.char_label,
                        ],
                    ),
                    self.text_field,
                ],
            ),
            padding=16,
            expand=True,
            margin=ft.Margin.only(left=24, right=24, bottom=16),
        )

        params = ft.Container(
            padding=ft.Padding.only(left=24, right=24),
            content=ft.Row(
                spacing=12,
                controls=[
                    self.rate_card,
                    self.pitch_card,
                    self.index_card,
                    self.protect_card,
                ],
            ),
        )

        action_bar = ft.Container(
            bgcolor=theme.CARD,
            border=ft.Border(top=ft.BorderSide(1, theme.LINE)),
            padding=ft.Padding.only(left=24, right=24, top=10, bottom=12),
            content=ft.Column(
                spacing=8,
                controls=[
                    self.progress_bar,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    self.status_label,
                                    theme.t("Ctrl + Enter 快速生成", 11, theme.DIM),
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    self.preview_button,
                                    self.export_button,
                                    self.generate_button,
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

        super().__init__(
            expand=True,
            content=ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    header,
                    editor_card,
                    params,
                    ft.Container(
                        padding=ft.Padding.only(left=24, right=24, top=8, bottom=2),
                        content=self.progress_label,
                    ),
                    action_bar,
                ],
            ),
        )

    def _slider_row(self, lo: int, hi: int, value: int, divisions: int, suffix: str) -> tuple[ft.Slider, ft.Text]:
        label = theme.t(f"{value}{suffix}", 12, theme.MUTED)
        slider = ft.Slider(
            min=lo,
            max=hi,
            value=value,
            divisions=divisions,
            active_color=theme.BRAND,
            inactive_color=theme.LINE,
            thumb_color=theme.BRAND,
            label=f"{value}{suffix}",
            on_change=lambda e, suffix=suffix, label=label: self._on_slider(e, suffix, label),
        )
        return slider, label

    @staticmethod
    def _on_slider(e: ft.Event, suffix: str, label: ft.Text) -> None:
        label.value = f"{int(float(e.control.value))}{suffix}"
        e.control.label = label.value
        label.update()

    def _param_card(
        self, title: str, slider: ft.Slider, value_label: ft.Text, tooltip: str | None = None
    ) -> ft.Container:
        return ft.Container(
            expand=True,
            bgcolor=theme.CARD,
            border=ft.Border.all(1, theme.LINE),
            border_radius=ft.BorderRadius.all(12),
            padding=ft.Padding.only(left=14, right=10, top=8, bottom=2),
            tooltip=tooltip,
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[theme.t(title, 12, theme.MUTED), value_label],
                    ),
                    slider,
                ],
            ),
        )

    def _on_text_change(self, e: ft.Event) -> None:
        text = self.text_field.value or ""
        segments = segment_text(text) if text.strip() else []
        self.char_label.value = f"{len(text)} 字 · {len(segments)} 段"
        self.char_label.update()

    @property
    def text(self) -> str:
        return (self.text_field.value or "").strip()

    def set_profile(self, profile: Profile) -> None:
        self.profile = profile
        ready, reason = profile.model_status()
        dot = theme.BRAND if ready else (theme.WARN if profile.is_rvc else theme.MUTED)
        self.chip_dot.bgcolor = dot
        kind = "RVC 克隆" if profile.is_rvc else "Edge 原生"
        self.chip_label.value = f"{profile.name} · {kind}"

        # 应用该音色的声线设计：语速、变调、相似度、保护度
        base = profile.base or {}
        convert = profile.convert or {}
        self._set_slider(self.rate_slider, self.rate_value, int(base.get("rate", 0)), "%")
        self._set_slider(self.pitch_slider, self.pitch_value, int(convert.get("pitch", 0)), " 半音")
        self._set_slider(
            self.index_slider, self.index_value, int(round(float(convert.get("indexRate", 0.75)) * 100)), "%"
        )
        self._set_slider(
            self.protect_slider, self.protect_value, int(round(float(convert.get("protect", 0.33)) * 100)), "%"
        )

        for slider in self.param_sliders:
            slider.disabled = not profile.is_rvc or not ready
        for card in self.rvc_cards:
            card.opacity = 1.0 if profile.is_rvc and ready else 0.55
        if profile.is_rvc and not ready:
            self.status_label.value = reason
        else:
            self.status_label.value = f"{profile.name} 已就绪 · 输出目录 output/"
        self.chip.update()
        self.status_label.update()
        for slider in self.param_sliders:
            slider.update()
        for card in self.rvc_cards:
            card.update()

    @staticmethod
    def _set_slider(slider: ft.Slider, label: ft.Text, value: int, suffix: str) -> None:
        lo, hi = int(slider.min), int(slider.max)
        value = max(lo, min(hi, value))
        slider.value = value
        slider.label = f"{value}{suffix}"
        label.value = slider.label

    def params(self, normalize: bool = True, concurrency: int = 3) -> GenerateParams:
        return GenerateParams(
            rate=int(self.rate_slider.value or 0),
            pitch_shift=int(self.pitch_slider.value or 0),
            index_rate=float(self.index_slider.value or 0) / 100,
            protect=float(self.protect_slider.value or 0) / 100,
            normalize=normalize,
            concurrency=concurrency,
        )

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.generate_button.disabled = busy
        self.preview_button.disabled = busy or self.result is None
        self.export_button.disabled = busy or self.result is None
        self.generate_button.content = theme.t(
            "生成中…" if busy else "生成语音", 14, theme.BG, ft.FontWeight.W_600
        )
        self.progress_bar.visible = busy
        if busy:
            self.progress_bar.value = 0
            self.progress_label.value = "准备中…"
        else:
            self.progress_label.value = ""
        self.generate_button.update()
        self.preview_button.update()
        self.export_button.update()
        self.progress_bar.update()
        self.progress_label.update()

    def update_progress(self, stage: str, current: int, total: int, detail: str) -> None:
        label = _STAGE_LABELS.get(stage, stage)
        safe_total = max(total, 1)
        if stage == "rvc" and current == 0:
            value = 0.0
        else:
            value = min(current / safe_total, 1)
        self.progress_bar.value = value if stage != "merge" else 0.95
        self.progress_label.value = f"{detail or label} · 分段 {current}/{total}"
        self.status_label.value = f"正在{label}…"
        self.progress_bar.update()
        self.progress_label.update()
        self.status_label.update()

    def finish(self, result: GenerationResult) -> None:
        self.result = result
        minutes, seconds = divmod(int(result.duration), 60)
        self.status_label.value = (
            f"已生成 · 时长 {minutes}:{seconds:02d} · 用时 {result.elapsed:.1f}s"
        )
        self.set_busy(False)
        self.preview_button.disabled = False
        self.export_button.disabled = False
        self.preview_button.update()
        self.export_button.update()
        self.status_label.update()

    def fail(self, message: str) -> None:
        self.set_busy(False)
        self.status_label.value = message
        self.status_label.update()
