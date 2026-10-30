"""Edge TTS：负责自然韵律的底声道合成。"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

SENTENCE_END = "。！？；…!?;\n"
CLAUSE_END = "，、：,:"

# 常用中文音色（避免启动时联网拉取全量列表，只保留当前真实可用的音色）
CURATED_VOICES: list[tuple[str, str, str]] = [
    ("zh-CN-XiaoxiaoNeural", "晓晓", "女声 · 温暖自然"),
    ("zh-CN-XiaoyiNeural", "晓伊", "女声 · 甜糯高亮"),
    ("zh-CN-YunxiNeural", "云希", "男声 · 清朗少年"),
    ("zh-CN-YunjianNeural", "云健", "男声 · 浑厚有力"),
    ("zh-CN-YunxiaNeural", "云夏", "男声 · 少年感"),
    ("zh-CN-YunyangNeural", "云扬", "男声 · 新闻播报"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北", "女声 · 东北口音"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮", "女声 · 陕西方言"),
    ("zh-TW-HsiaoChenNeural", "曉臻", "台湾女声"),
    ("zh-TW-HsiaoYuNeural", "曉雨", "台湾女声"),
    ("zh-TW-YunJheNeural", "雲哲", "台湾男声"),
    ("zh-HK-HiuMaanNeural", "曉曼", "粤语女声"),
    ("zh-HK-HiuGaaiNeural", "曉佳", "粤语女声"),
    ("zh-HK-WanLungNeural", "雲龍", "粤语男声"),
]


class TTSError(RuntimeError):
    """语音合成失败。"""


def segment_text(text: str, max_chars: int = 90, min_chars: int = 12) -> list[str]:
    """按中文标点切句，再把短句合并到 80~100 字，长句按逗号二次切分。"""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not text:
        return []

    raw: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in SENTENCE_END:
            raw.append(buf.strip())
            buf = ""
    if buf.strip():
        raw.append(buf.strip())

    segments: list[str] = []
    for sentence in raw:
        if len(sentence) <= max_chars:
            segments.append(sentence)
            continue
        # 长句按逗号切
        cur = ""
        for ch in sentence:
            cur += ch
            if ch in CLAUSE_END and len(cur) >= max_chars * 0.45:
                segments.append(cur.strip())
                cur = ""
        if cur.strip():
            segments.append(cur.strip())

    # 完全没有标点的超长句，按长度硬切
    hard: list[str] = []
    for seg in segments:
        while len(seg) > max_chars:
            hard.append(seg[:max_chars])
            seg = seg[max_chars:]
        if seg:
            hard.append(seg)

    # 合并过短的句子
    merged: list[str] = []
    for seg in hard:
        if merged and len(merged[-1]) + len(seg) <= max_chars and len(merged[-1]) < min_chars:
            merged[-1] += seg
        else:
            merged.append(seg)
    return [s for s in merged if s]


@dataclass
class EdgeParams:
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: int = 0  # -50 ~ +50 (%)
    volume: int = 0
    pitch: int = 0  # Hz


def _pct(value: int) -> str:
    return f"{value:+d}%"


def _hz(value: int) -> str:
    return f"{value:+d}Hz"


async def synth_segment(text: str, params: EdgeParams, out_path: Path) -> Path:
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        params.voice,
        rate=_pct(params.rate),
        volume=_pct(params.volume),
        pitch=_hz(params.pitch),
    )
    await communicate.save(str(out_path))
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TTSError("Edge TTS 返回了空音频，请检查网络或稍后重试")
    return out_path


async def synth_all(
    segments: list[str],
    params: EdgeParams,
    work_dir: Path,
    on_segment: Callable[[int, int], None] | None = None,
    concurrency: int = 3,
) -> list[Path]:
    """并发合成所有分段，返回按顺序排列的 mp3 路径。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max(1, concurrency))
    done = 0
    total = len(segments)
    lock = asyncio.Lock()

    async def worker(index: int, seg: str) -> Path:
        nonlocal done
        async with sem:
            path = work_dir / f"edge_{index:03d}.mp3"
            await synth_segment(seg, params, path)
            async with lock:
                done += 1
                if on_segment:
                    on_segment(done, total)
            return path

    return list(await asyncio.gather(*(worker(i, s) for i, s in enumerate(segments) if s)))
