"""生成流水线：文本 → Edge 分段合成 → RVC 音色转换 → 拼接 → mp3。"""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app import config
from app.core.audio_utils import (
    AudioError,
    concat_wavs,
    duration_of,
    mp3_to_wav,
    wav_to_mp3,
)
from app.core.edge_engine import EdgeParams, segment_text, synth_all
from app.core.rvc_converter import RVCConverter, RVCParams, RVCError
from app.core.voice_store import Profile


@dataclass
class GenerateParams:
    rate: int = 0
    volume: int = 0
    pitch: int = 0
    index_rate: float = 0.75
    protect: float = 0.33
    f0_method: str = "rmvpe"
    pitch_shift: int = 0
    normalize: bool = True
    concurrency: int = 3


@dataclass
class GenerationResult:
    audio_path: Path
    duration: float
    segment_count: int
    elapsed: float
    converted: bool
    warnings: list[str] = field(default_factory=list)


ProgressFn = Callable[[str, int, int, str], None]


class GenerateCancelled(RuntimeError):
    pass


class Pipeline:
    def __init__(self, converter: RVCConverter | None = None) -> None:
        self.converter = converter or RVCConverter()

    def _check_cancel(self, cancel: threading.Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise GenerateCancelled("已取消生成")

    def generate(
        self,
        text: str,
        profile: Profile,
        params: GenerateParams | None = None,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
        save_to: Path | None = None,
    ) -> GenerationResult:
        params = params or GenerateParams()
        start = time.time()
        text = apply_voice_style(text, profile)
        segments = segment_text(text)
        if not segments:
            raise ValueError("请输入要合成的文本")

        def report(stage: str, current: int, total: int, detail: str = "") -> None:
            if on_progress:
                on_progress(stage, current, total, detail)

        config.ensure_dirs()
        stamp = datetime.now().strftime("%m%d-%H%M%S")
        work_dir = config.CACHE_DIR / f"job-{stamp}-{int(time.time() * 1000) % 1000:03d}"
        work_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        converted = False

        try:
            report("synthesize", 0, len(segments), "Edge TTS 合成中")
            edge_params = EdgeParams(
                voice=profile.base.get("voice", "zh-CN-XiaoxiaoNeural"),
                rate=params.rate,
                volume=params.volume,
                pitch=params.pitch,
            )
            mp3_paths = asyncio.run(
                synth_all(
                    segments,
                    edge_params,
                    work_dir,
                    on_segment=lambda done, total: report(
                        "synthesize", done, total, "Edge TTS 合成中"
                    ),
                    concurrency=params.concurrency,
                )
            )
            self._check_cancel(cancel)

            report("convert_audio", 0, len(mp3_paths), "转码准备 RVC")
            wavs: list[Path] = []
            for i, mp3 in enumerate(mp3_paths, 1):
                wav = work_dir / f"src_{i:03d}.wav"
                mp3_to_wav(mp3, wav)
                wavs.append(wav)
                report("convert_audio", i, len(mp3_paths), "转码准备 RVC")

            # RVC 音色转换
            if profile.is_rvc:
                ready, reason = profile.model_status()
                if ready:
                    cfg = profile.convert or {}
                    rvc_params = RVCParams(
                        pitch=params.pitch_shift,
                        index_rate=params.index_rate,
                        protect=params.protect,
                        f0_method=params.f0_method,
                    )
                    self.converter.load(
                        Path(cfg["model"]),
                        Path(cfg["index"]) if cfg.get("index") else None,
                        rvc_params,
                        tag=profile.id,
                    )
                    converted_wavs: list[Path] = []
                    total = len(wavs)
                    report(
                        "rvc",
                        0,
                        total,
                        f"RVC 转换中 · 0/{total}（{self.converter.device}）",
                    )

                    # RVC 批量转换只加载一次模型；用轮询输出文件的方式汇报进度
                    stop_monitor = threading.Event()
                    outputs = [p.with_name(f"{p.stem}_edited{p.suffix}") for p in wavs]

                    def monitor() -> None:
                        last = 0
                        while not stop_monitor.wait(0.8):
                            done_count = sum(1 for p in outputs if p.exists())
                            if done_count != last:
                                last = done_count
                                report(
                                    "rvc",
                                    done_count,
                                    total,
                                    f"RVC 转换中 · {done_count}/{total}（{self.converter.device}）",
                                )

                    watcher = threading.Thread(target=monitor, daemon=True)
                    watcher.start()
                    try:
                        converted_wavs = self.converter.convert_many(wavs)
                    finally:
                        stop_monitor.set()
                    wavs = converted_wavs
                    converted = True
                    report("rvc", total, total, f"音色转换完成 · {total}/{total}")
                else:
                    warnings.append(f"{profile.name}：{reason}，本次已跳过音色转换")
            else:
                report("rvc", 0, 1, "跳过音色转换")

            self._check_cancel(cancel)
            report("merge", 0, 1, "拼接与响度归一")
            merged = concat_wavs(wavs, work_dir / "merged.wav")
            title = _safe_name(f"{profile.name}-{stamp}")
            target_dir = save_to or config.OUTPUT_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            out_mp3 = target_dir / f"{title}.mp3"
            wav_to_mp3(merged, out_mp3, normalize=params.normalize)
            report("merge", 1, 1, "完成")

            return GenerationResult(
                audio_path=out_mp3,
                duration=duration_of(out_mp3),
                segment_count=len(segments),
                elapsed=time.time() - start,
                converted=converted,
                warnings=warnings,
            )
        except (AudioError, RVCError) as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def apply_voice_style(text: str, profile: Profile) -> str:
    """按音色设定做轻量文本风格化：短句加“哼”，句末用省略号拖尾。"""
    style = (profile.base or {}).get("style") or {}
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    opening = style.get("opening")
    short_len = int(style.get("short_len", 0))
    if opening and short_len and len(cleaned) <= short_len:
        cleaned = f"{opening}{cleaned}"

    trail = style.get("trail")
    if trail:
        cleaned = cleaned.replace("。", trail)
        if not cleaned.endswith(("。", "！", "？", "!", "?", "…", "~")):
            cleaned += trail
    return cleaned


def _safe_name(name: str) -> str:
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip() or "output"
