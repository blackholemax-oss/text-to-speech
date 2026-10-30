"""命令行入口，用于不启动界面时快速验证链路。"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from app.core.pipeline import GenerateParams, Pipeline
from app.core.voice_store import VoiceStore


def _progress(stage: str, current: int, total: int, detail: str) -> None:
    total = max(total, 1)
    ratio = min(current / total, 1.0)
    bar = "█" * int(ratio * 24) + "·" * (24 - int(ratio * 24))
    sys.stdout.write(f"\r[{bar}] {detail:<28}")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="声涧 · 文字转语音 CLI")
    parser.add_argument("text", nargs="?", help="要合成的文本")
    parser.add_argument("-f", "--file", type=Path, help="从文本文件读取")
    parser.add_argument("-v", "--voice", default="xiaoxiao", help="音色 id 或 Edge voice")
    parser.add_argument("-o", "--out", type=Path, help="输出目录")
    parser.add_argument("--rate", type=int, default=None, help="语速 -50..50，默认取音色设定")
    parser.add_argument("--pitch-shift", type=int, default=None, help="RVC 变调半音数，默认取音色设定")
    parser.add_argument("--list", action="store_true", help="列出音色")
    args = parser.parse_args()

    store = VoiceStore()
    if args.list:
        for p in store.profiles:
            ready, reason = p.model_status()
            print(f"{'✓' if ready else '×'} {p.id:<16} {p.name:<8} {reason}")
        return 0

    if args.file:
        text = args.file.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("没有输入文本", file=sys.stderr)
        return 2

    profile = store.get(args.voice) or store.find_by_voice(args.voice)
    if profile is None:
        print(f"未知音色：{args.voice}，用 --list 查看可用音色", file=sys.stderr)
        return 2

    pipeline = Pipeline()
    base = profile.base or {}
    convert = profile.convert or {}
    params = GenerateParams(
        rate=args.rate if args.rate is not None else int(base.get("rate", 0)),
        pitch_shift=args.pitch_shift
        if args.pitch_shift is not None
        else int(convert.get("pitch", 0)),
        index_rate=float(convert.get("indexRate", 0.75)),
        protect=float(convert.get("protect", 0.33)),
    )
    try:
        result = pipeline.generate(
            text,
            profile,
            params,
            on_progress=_progress,
            cancel=threading.Event(),
            save_to=args.out,
        )
    except RuntimeError as exc:
        print(f"\n生成失败：{exc}", file=sys.stderr)
        return 1

    print()
    for warning in result.warnings:
        print(f"提示：{warning}")
    print(
        f"完成：{result.audio_path}  "
        f"时长 {result.duration:.1f}s  分段 {result.segment_count}  "
        f"耗时 {result.elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
