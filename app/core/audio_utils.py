"""音频处理工具：ffmpeg 定位、格式转换、拼接、响度归一。"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import soundfile as sf

_SAMPLE_RATE = 44100


class AudioError(RuntimeError):
    """音频处理失败。"""


@functools.lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    """优先使用系统 PATH 中的 ffmpeg，其次使用 imageio-ffmpeg 自带的二进制。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - 依赖缺失时的兜底
        raise AudioError(
            "未找到 ffmpeg。请安装 ffmpeg 并加入 PATH（winget install Gyan.FFmpeg），"
            "或安装 imageio-ffmpeg。"
        ) from exc


@functools.lru_cache(maxsize=1)
def ensure_ffmpeg_on_path() -> str:
    """RVC 内部直接调用 `ffmpeg` 命令，这里保证它一定能在 PATH 里找到。"""
    exe = Path(ffmpeg_path())
    if exe.name.lower() == "ffmpeg.exe":
        exe_dir = exe.parent
    else:
        bin_dir = Path(__file__).resolve().parent.parent.parent / "cache" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        shim = bin_dir / "ffmpeg.exe"
        if not shim.exists() or shim.stat().st_size != exe.stat().st_size:
            shutil.copy2(exe, shim)
        exe_dir = bin_dir
    current = os.environ.get("PATH", "")
    if str(exe_dir) not in current.split(os.pathsep):
        os.environ["PATH"] = str(exe_dir) + os.pathsep + current
    return str(exe_dir / "ffmpeg.exe")


def _run(args: list[str]) -> None:
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    if proc.returncode != 0:
        raise AudioError((proc.stderr or "ffmpeg 执行失败").strip()[-500:])


def mp3_to_wav(src: Path, dst: Path, sample_rate: int = _SAMPLE_RATE) -> Path:
    """Edge TTS 输出的 mp3 转成单声道 16bit wav，供 RVC 使用。"""
    _run(
        [
            "-i", str(src),
            "-ac", "1",
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            str(dst),
        ]
    )
    return dst


def wav_to_mp3(src: Path, dst: Path, bitrate: str = "192k", normalize: bool = True) -> Path:
    """输出 mp3。normalize=True 时做单通道响度归一，避免音量忽大忽小。"""
    filters = ["loudnorm=I=-16:TP=-1.5:LRA=11"] if normalize else []
    args = ["-i", str(src), "-ac", "1"]
    if filters:
        args += ["-af", ",".join(filters)]
    args += ["-c:a", "libmp3lame", "-b:a", bitrate, str(dst)]
    _run(args)
    return dst


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def write_wav(path: Path, data: np.ndarray, sr: int) -> Path:
    sf.write(str(path), data, sr, subtype="PCM_16")
    return path


def concat_wavs(paths: Iterable[Path], dst: Path, gap_seconds: float = 0.12) -> Path:
    """按顺序拼接 wav，段间插入短暂静音，避免换段处听感突兀。"""
    chunks: list[np.ndarray] = []
    sr = _SAMPLE_RATE
    for p in paths:
        data, sr = read_wav(Path(p))
        chunks.append(data)
        gap = np.zeros(int(sr * gap_seconds), dtype=np.float32)
        chunks.append(gap)
    if not chunks:
        raise AudioError("没有可拼接的音频")
    merged = np.concatenate(chunks[:-1]) if chunks[-1].size == 0 else np.concatenate(chunks)
    return write_wav(dst, merged, sr)


def duration_of(path: Path) -> float:
    try:
        info = sf.info(str(path))
        return float(info.duration)
    except Exception:
        return 0.0


def play_file(path: Path) -> None:
    """用系统默认播放器打开音频。"""
    if sys.platform == "win32":
        import os

        os.startfile(str(path))  # type: ignore[attr-defined]
    else:  # pragma: no cover
        import subprocess as sp

        opener = "open" if sys.platform == "darwin" else "xdg-open"
        sp.Popen([opener, str(path)])
