"""全局路径与常量。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
MODELS_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / "cache"
PROFILES_PATH = ROOT / "profiles.json"
SETTINGS_PATH = ROOT / "settings.json"

APP_NAME = "声涧"
APP_VERSION = "0.1.0"


def ensure_dirs() -> None:
    for d in (MODELS_DIR, OUTPUT_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
