"""音色档案的读写与模型导入。"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import MODELS_DIR, PROFILES_PATH
from app.core.edge_engine import CURATED_VOICES

DEFAULT_PROFILES: list[dict[str, Any]] = [
    {
        "id": "xiaoxiao",
        "name": "晓晓",
        "desc": "温暖女声 · 自然讲述",
        "base": {"engine": "edge", "voice": "zh-CN-XiaoxiaoNeural"},
        "convert": None,
    },
    {
        "id": "yunxi",
        "name": "云希",
        "desc": "清朗少年 · 轻快",
        "base": {"engine": "edge", "voice": "zh-CN-YunxiNeural"},
        "convert": None,
    },
    {
        "id": "yunjian",
        "name": "云健",
        "desc": "浑厚男声 · 有力",
        "base": {"engine": "edge", "voice": "zh-CN-YunjianNeural"},
        "convert": None,
    },
    {
        "id": "xiaoyi",
        "name": "晓伊",
        "desc": "甜糯女声 · 活泼",
        "base": {"engine": "edge", "voice": "zh-CN-XiaoyiNeural"},
        "convert": None,
    },
    {
        "id": "dafeiyu",
        "name": "大肥鱼",
        "desc": "软亮女声 · 语速快 · 略带不耐",
        "base": {
            "engine": "edge",
            "voice": "zh-CN-XiaoyiNeural",
            "rate": 22,
            "volume": 0,
            "style": {"opening": "哼，", "short_len": 18, "trail": "……"},
        },
        "convert": {
            "type": "rvc",
            "model": str(MODELS_DIR / "dafeiyu" / "dafeiyu.pth"),
            "index": str(MODELS_DIR / "dafeiyu" / "added_IVF1314_Flat_nprobe_1_dafeiyu_v2.index"),
            "pitch": -3,
            "indexRate": 0.72,
            "protect": 0.30,
            "f0Method": "rmvpe",
        },
    },
    {
        "id": "ruannv",
        "name": "软糯女声",
        "desc": "软糯年轻女声 · 标准普通话 · 语速稍快",
        "base": {
            "engine": "edge",
            "voice": "zh-CN-XiaoxiaoNeural",
            "rate": 12,
            "volume": 0,
        },
        "convert": {
            "type": "rvc",
            "model": str(MODELS_DIR / "dafeiyu" / "dafeiyu.pth"),
            "index": str(MODELS_DIR / "dafeiyu" / "added_IVF1314_Flat_nprobe_1_dafeiyu_v2.index"),
            "pitch": 0,
            "indexRate": 0.75,
            "protect": 0.33,
            "f0Method": "rmvpe",
        },
    },
]


@dataclass
class Profile:
    id: str
    name: str
    desc: str = ""
    base: dict[str, Any] = field(default_factory=dict)
    convert: dict[str, Any] | None = None

    @property
    def is_rvc(self) -> bool:
        return bool(self.convert and self.convert.get("type") == "rvc")

    @property
    def initial(self) -> str:
        return self.name[:1]

    def model_status(self) -> tuple[bool, str]:
        """返回（是否可直接使用, 提示文案）。"""
        if not self.is_rvc:
            return True, "Edge 原生音色"
        model = (self.convert or {}).get("model", "")
        if not model:
            return False, "尚未导入 .pth 模型"
        if not Path(model).exists():
            return False, "模型文件不存在，请重新导入"
        return True, "RVC 音色已就绪"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc,
            "base": self.base,
            "convert": self.convert,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        return cls(
            id=data.get("id") or uuid.uuid4().hex[:8],
            name=data.get("name", "未命名"),
            desc=data.get("desc", ""),
            base=data.get("base") or {"engine": "edge", "voice": "zh-CN-XiaoxiaoNeural"},
            convert=data.get("convert"),
        )


class VoiceStore:
    def __init__(self, path: Path = PROFILES_PATH) -> None:
        self.path = path
        self.profiles: list[Profile] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.profiles = [Profile.from_dict(item) for item in raw]
                if self.profiles:
                    return
            except Exception:
                pass
        self.profiles = [Profile.from_dict(item) for item in DEFAULT_PROFILES]
        self.save()

    def save(self) -> None:
        self.path.write_text(
            json.dumps([p.to_dict() for p in self.profiles], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, profile_id: str) -> Profile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def find_by_voice(self, voice: str) -> Profile | None:
        return next((p for p in self.profiles if p.base.get("voice") == voice), None)

    def upsert(self, profile: Profile) -> Profile:
        for i, existing in enumerate(self.profiles):
            if existing.id == profile.id:
                self.profiles[i] = profile
                break
        else:
            self.profiles.append(profile)
        self.save()
        return profile

    def create_edge_profile(self, voice_id: str, name: str | None = None) -> Profile:
        meta = next((v for v in CURATED_VOICES if v[0] == voice_id), None)
        display = name or (meta[1] if meta else voice_id)
        profile_id = "edge-" + re.sub(r"[^a-z0-9]+", "", voice_id.lower())[-12:]
        profile = Profile(
            id=profile_id,
            name=display,
            desc=(meta[2] if meta else "Edge 原生音色"),
            base={"engine": "edge", "voice": voice_id},
            convert=None,
        )
        self.upsert(profile)
        return profile

    def import_rvc_model(
        self,
        profile: Profile,
        model_path: Path,
        index_path: Path | None,
        base_voice: str | None = None,
    ) -> Profile:
        """把 .pth/.index 复制进 models/<id>/，避免原文件被移动或删除。"""
        target_dir = MODELS_DIR / profile.id
        target_dir.mkdir(parents=True, exist_ok=True)
        model_dst = target_dir / model_path.name
        shutil.copy2(model_path, model_dst)
        index_dst = None
        if index_path and index_path.exists():
            index_dst = target_dir / index_path.name
            shutil.copy2(index_path, index_dst)

        base = profile.base or {"engine": "edge", "voice": "zh-CN-YunxiNeural"}
        if base_voice:
            base = {"engine": "edge", "voice": base_voice}
        convert = profile.convert or {
            "type": "rvc",
            "pitch": 0,
            "indexRate": 0.75,
            "protect": 0.33,
            "f0Method": "rmvpe",
        }
        convert.update(
            {
                "type": "rvc",
                "model": str(model_dst),
                "index": str(index_dst) if index_dst else "",
            }
        )
        profile.convert = convert
        profile.base = base
        return self.upsert(profile)
