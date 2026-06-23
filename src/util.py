"""共通ユーティリティ: 設定読み込み・パス・ログ。"""
from __future__ import annotations
import os
import sys
import json
import logging
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
TMP_DIR = ROOT / "tmp"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("autopilot")


def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_affiliates() -> dict:
    path = CONFIG_DIR / "affiliates.yaml"
    if not path.exists():
        return {"programs": [], "disclosure": ""}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    return val


def require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"環境変数 {key} が未設定です。GitHub Secrets / .env を確認してください。")
    return val


def ensure_dirs() -> None:
    for d in (DATA_DIR, SITE_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)
