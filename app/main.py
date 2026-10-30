"""应用入口：组装音色库、编辑区与生成流程。"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import uuid
from pathlib import Path

import flet as ft

from app import config
from app.core.audio_utils import play_file
from app.core.pipeline import GenerationResult, Pipeline
from app.core.voice_store import Profile, VoiceStore
from app.ui import theme
from app.ui.views.editor import EditorView
from app.ui.views.settings import SettingsDialog
from app.ui.views.voices import ImportModelDialog, VoicesPanel


class TtsApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.store = VoiceStore()
        self.pipeline = Pipeline()
        self.cancel_event = threading.Event()
        self.picker = ft.FilePicker(on_result=self._on_file_picked)
        self._configure_page()

        profile = self._initial_profile()
        self.voices_panel = VoicesPanel(
            self.store,
            on_select=self._select_profile,
            selected_id=profile.id,
        )
        self.voices_panel.import_button.action = ft.PickFiles(
            self.picker,
            dialog_title="选择 RVC 模型（.pth）",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pth"],
        )
        self.editor = EditorView(
            on_generate=self.start_generate,
            on_preview=self._preview,
            on_export=lambda: page.run_task(self._export),
            on_settings=self._show_settings,
        )
        self.page.on_keyboard_event = self._on_keyboard
        self.page.services.append(self.picker)
        self.page.add(
            ft.Row(
                spacing=0,
                expand=True,
                controls=[self.voices_panel, self.editor],
            )
        )
        self.page.update()
        self._select_profile(profile)

    def _configure_page(self) -> None:
        page = self.page
        page.bgcolor = theme.BG
        page.padding = 0
        page.theme_mode = ft.ThemeMode.DARK
        page.theme = theme.build_theme()
        page.title = "声涧 · 文字转语音"
        page.window.width = 1080
        page.window.height = 720
        page.window.min_width = 960
        page.window.min_height = 640
        page.window.bgcolor = theme.BG

    def _initial_profile(self) -> Profile:
        for p in self.store.profiles:
            if p.is_rvc and p.model_status()[0]:
                return p
        return self.store.profiles[0]

    def _select_profile(self, profile: Profile) -> None:
        self.voices_panel.set_selected(profile.id)
        self.editor.set_profile(profile)

    # ---------- 生成 ----------

    def start_generate(self) -> None:
        if self.editor.busy:
            return
        text = self.editor.text
        if not text:
            self._toast("请先输入要合成的文字")
            return
        profile = self.editor.profile
        if profile is None:
            self._toast("请选择音色")
            return
        if profile.is_rvc and not profile.model_status()[0]:
            self._toast(f"{profile.name} 尚未就绪，本次将使用底声合成")

        params = self.editor.params(normalize=True, concurrency=3)
        self.cancel_event = threading.Event()
        self.editor.set_busy(True)
        self.page.run_thread(self._work, text, profile, params)

    def _work(self, text: str, profile: Profile, params) -> None:  # noqa: ANN001
        try:
            result = self.pipeline.generate(
                text,
                profile,
                params,
                on_progress=self._progress_from_thread,
                cancel=self.cancel_event,
            )
        except Exception as exc:  # noqa: BLE001 - 需要把错误展示给用户
            self._schedule(self._apply_failure, str(exc))
            return
        self._schedule(self._apply_result, result)

    def _schedule(self, handler, *args) -> None:  # noqa: ANN001
        """页面关闭后 session 会失效，这里吞掉调度异常避免线程崩溃。"""
        try:
            self.page.run_task(handler, *args)
        except Exception:  # noqa: BLE001
            pass

    def _progress_from_thread(self, stage: str, current: int, total: int, detail: str) -> None:
        self._schedule(self._apply_progress, stage, current, total, detail)

    async def _apply_progress(self, stage: str, current: int, total: int, detail: str) -> None:
        self.editor.update_progress(stage, current, total, detail)

    async def _apply_result(self, result: GenerationResult) -> None:
        self.editor.finish(result)
        for warning in result.warnings:
            self._toast(warning)
        self._toast(f"生成完成：{result.audio_path.name}")

    async def _apply_failure(self, message: str) -> None:
        self.editor.fail(f"生成失败：{message[:80]}")
        self._toast(f"生成失败：{message[:120]}")

    # ---------- 试听 / 导出 ----------

    def _preview(self) -> None:
        if not self.editor.result:
            return
        try:
            play_file(self.editor.result.audio_path)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"无法播放：{exc}")

    async def _export(self) -> None:
        result = self.editor.result
        if not result:
            return
        try:
            target = await self.picker.save_file(
                dialog_title="导出音频",
                file_name=result.audio_path.name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["mp3"],
            )
        except Exception as exc:  # noqa: BLE001
            self._toast(f"打开保存对话框失败：{exc}")
            return
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".mp3":
            path = path.with_suffix(".mp3")
        try:
            shutil.copy2(result.audio_path, path)
            self._toast(f"已导出到 {path}")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"导出失败：{exc}")

    # ---------- 音色导入 ----------

    def _on_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        if not e.files[0].path:
            self._toast("当前环境无法获取文件路径，请使用桌面端")
            return
        model_path = Path(e.files[0].path)
        dialog = ImportModelDialog(
            self.page,
            model_path,
            on_save=self._save_imported_model,
        )
        self.page.show_dialog(dialog)

    def _save_imported_model(self, name: str, base_voice: str, model_path: Path) -> None:
        profile = Profile(
            id="rvc-" + uuid.uuid4().hex[:6],
            name=name,
            desc=f"RVC 克隆 · {model_path.stem}",
            base={"engine": "edge", "voice": base_voice},
            convert={
                "type": "rvc",
                "model": "",
                "index": "",
                "pitch": 0,
                "indexRate": 0.75,
                "protect": 0.33,
                "f0Method": "rmvpe",
            },
        )
        # 同目录下的 .index 自动配对
        index_candidates = sorted(model_path.parent.glob("*.index"))
        index_path = index_candidates[0] if index_candidates else None
        self.store.import_rvc_model(profile, model_path, index_path, base_voice)
        self.voices_panel.refresh()
        self._select_profile(profile)
        self._toast(f"已导入音色「{name}」")

    # ---------- 设置 ----------

    def _show_settings(self) -> None:
        dialog = SettingsDialog(
            self.page,
            on_open_output=self._open_output,
            on_clear_cache=self._clear_cache,
        )
        self.page.show_dialog(dialog)

    def _open_output(self) -> None:
        config.ensure_dirs()
        try:
            os.startfile(str(config.OUTPUT_DIR))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self._toast(f"无法打开目录：{exc}")

    def _clear_cache(self) -> None:
        shutil.rmtree(config.CACHE_DIR, ignore_errors=True)
        config.ensure_dirs()
        self._toast("缓存已清理")

    # ---------- 通用 ----------

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        if e.key == "Enter" and (e.ctrl or e.meta):
            self.start_generate()

    def _toast(self, message: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=theme.t(message, 13, theme.TEXT),
                bgcolor=theme.OVERLAY,
                behavior=ft.SnackBarBehavior.FLOATING,
                margin=ft.Margin.only(left=24, right=24, bottom=16),
                duration=3000,
                shape=ft.RoundedRectangleBorder(radius=12),
            )
        )


def main(page: ft.Page) -> None:
    config.ensure_dirs()
    TtsApp(page)


if __name__ == "__main__":
    if "--web" in sys.argv:
        ft.run(main, view=ft.AppView.FLET_APP_WEB, port=8550)
    else:
        ft.run(main)
