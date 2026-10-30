"""RVC 音色转换：把 Edge TTS 的底声换成目标音色。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import MODELS_DIR
from app.core.audio_utils import ensure_ffmpeg_on_path


class RVCError(RuntimeError):
    """RVC 转换失败。"""


RMVPE_URLS = (
    "https://hf-mirror.com/r3gm/sonitranslate_voice_models/resolve/main/rmvpe.pt",
    "https://huggingface.co/r3gm/sonitranslate_voice_models/resolve/main/rmvpe.pt",
)


def ensure_rmvpe() -> Path | None:
    """把 rmvpe.pt 下载到 models/pretrained，避免污染项目根目录。"""
    target_dir = MODELS_DIR / "pretrained"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "rmvpe.pt"
    if target.exists() and target.stat().st_size > 1024 * 1024:
        return target

    import urllib.request

    for url in RMVPE_URLS:
        try:
            tmp = target.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            if tmp.stat().st_size > 1024 * 1024:
                tmp.replace(target)
                return target
        except Exception:
            continue
    return None


@dataclass
class RVCParams:
    pitch: int = 0
    index_rate: float = 0.75
    protect: float = 0.33
    f0_method: str = "rmvpe"


class RVCConverter:
    """懒加载 BaseLoader；同一音色多次转换会复用已加载的模型。"""

    def __init__(self) -> None:
        self._loader: Any = None
        self._tag: str | None = None
        self._device: str = "未知"

    @property
    def device(self) -> str:
        return self._device

    def _ensure_loader(self) -> Any:
        if self._loader is not None:
            return self._loader
        # HuBERT 预训练模型走国内镜像，避免 huggingface 直连失败
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        ensure_ffmpeg_on_path()
        try:
            from infer_rvc_python import BaseLoader
        except Exception as exc:  # pragma: no cover
            raise RVCError(
                "RVC 依赖未安装或加载失败："
                f"{exc}。请执行 uv pip install infer-rvc-python==1.3.1"
            ) from exc

        try:
            import torch

            self._device = "CUDA" if torch.cuda.is_available() else "CPU"
        except Exception:
            self._device = "CPU"

        rmvpe = ensure_rmvpe()
        try:
            # only_cpu=False 时自动优先 CUDA，无 CUDA 时回落 CPU
            self._loader = BaseLoader(
                only_cpu=self._device == "CPU",
                rmvpe_path=str(rmvpe) if rmvpe else None,
            )
        except Exception as exc:
            raise RVCError(f"RVC 初始化失败：{exc}") from exc
        return self._loader

    def load(
        self,
        model_path: Path,
        index_path: Path | None,
        params: RVCParams,
        tag: str = "current",
    ) -> None:
        if not model_path.exists():
            raise RVCError(f"RVC 模型不存在：{model_path}")
        loader = self._ensure_loader()
        try:
            loader.apply_conf(
                tag=tag,
                file_model=str(model_path),
                pitch_algo=params.f0_method,
                pitch_lvl=int(params.pitch),
                file_index=str(index_path) if index_path and index_path.exists() else "",
                index_influence=float(params.index_rate),
                consonant_breath_protection=float(params.protect),
            )
        except Exception as exc:
            raise RVCError(f"RVC 模型加载失败：{exc}") from exc
        self._tag = tag

    def convert_many(self, wav_paths: list[Path]) -> list[Path]:
        """一次调用批量转换：模型与 HuBERT 只加载一次，显著省时。"""
        if self._loader is None or self._tag is None:
            raise RVCError("RVC 尚未加载模型")
        try:
            result = self._loader(
                [str(p) for p in wav_paths],
                self._tag,
                overwrite=False,
                parallel_workers=1,
                show_progress=False,
            )
        except Exception as exc:
            raise RVCError(f"RVC 转换失败：{exc}") from exc

        if isinstance(result, str):
            outputs = [Path(result)]
        else:
            outputs = [Path(str(p)) for p in result]
        if len(outputs) < len(wav_paths):
            raise RVCError("RVC 转换中断，部分分段未生成音频")
        for out in outputs[: len(wav_paths)]:
            if not out.exists():
                raise RVCError(f"RVC 输出缺失：{out.name}")
        return outputs[: len(wav_paths)]

    def unload(self) -> None:
        if self._loader is not None:
            try:
                self._loader.unload_models()
            except Exception:
                pass
        self._loader = None
        self._tag = None
