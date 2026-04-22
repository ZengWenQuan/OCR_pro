from __future__ import annotations

"""后端全局配置读取模块。

默认读取同目录下的 config.yaml。路径类配置支持相对路径，相对 config.yaml
所在目录解析；也支持直接写绝对路径。运行时可通过 OCR_BACKEND_CONFIG 环境变量
指定另一份配置文件。
"""

import os
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = BASE_DIR / "config.yaml"
CONFIG_ENV_VAR = "OCR_BACKEND_CONFIG"

DEFAULT_CONFIG_VALUES: dict[str, Any] = {
    "server": {
        "host": "0.0.0.0",
        "port": 8100,
        "debug": True,
    },
    "paths": {
        "book_dir": "../..",
        "data_dir": "../data",
        "checkpoints_dir": "../checkpoints",
    },
    "ocr": {
        "lang": "en",
        "use_angle_cls": True,
        "show_log": False,
        "min_score": 0.0,
        "cls_model_dir": "../checkpoints/cls/ch_ppocr_mobile_v2.0_cls_infer",
        "det_model_dir": "../checkpoints/det/en/en_PP-OCRv3_det_infer",
        "rec_model_dir": "../checkpoints/rec/en/en_PP-OCRv4_rec_infer",
    },
}


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    debug: bool


@dataclass(frozen=True)
class PathsConfig:
    book_dir: Path
    data_dir: Path
    checkpoints_dir: Path


@dataclass(frozen=True)
class OcrConfig:
    lang: str
    use_angle_cls: bool
    show_log: bool
    min_score: float
    cls_model_dir: Path
    det_model_dir: Path
    rec_model_dir: Path


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    paths: PathsConfig
    ocr: OcrConfig


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_path(raw_path: str | Path, config_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件顶层必须是 YAML 对象: {path}")
    return raw


def load_config(path: str | Path = DEFAULT_CONFIG_FILE) -> AppConfig:
    """加载指定 YAML 配置，并解析成强类型配置对象。"""

    config_path = Path(path).expanduser().resolve()
    values = _deep_merge(DEFAULT_CONFIG_VALUES, _read_yaml(config_path))
    config_dir = config_path.parent

    server = values["server"]
    paths = values["paths"]
    ocr = values["ocr"]
    return AppConfig(
        server=ServerConfig(
            host=str(server["host"]),
            port=int(server["port"]),
            debug=bool(server["debug"]),
        ),
        paths=PathsConfig(
            book_dir=_resolve_path(paths["book_dir"], config_dir),
            data_dir=_resolve_path(paths["data_dir"], config_dir),
            checkpoints_dir=_resolve_path(paths["checkpoints_dir"], config_dir),
        ),
        ocr=OcrConfig(
            lang=str(ocr["lang"]),
            use_angle_cls=bool(ocr["use_angle_cls"]),
            show_log=bool(ocr["show_log"]),
            min_score=float(ocr["min_score"]),
            cls_model_dir=_resolve_path(ocr["cls_model_dir"], config_dir),
            det_model_dir=_resolve_path(ocr["det_model_dir"], config_dir),
            rec_model_dir=_resolve_path(ocr["rec_model_dir"], config_dir),
        ),
    )


def get_config_path() -> Path:
    """返回当前应使用的配置文件路径。"""

    return Path(os.environ.get(CONFIG_ENV_VAR, DEFAULT_CONFIG_FILE)).expanduser().resolve()


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """读取并缓存全局配置。

    这个缓存和 OCR 引擎一样是进程内缓存。修改 YAML 后需要重启后端进程，
    才能让新配置生效。
    """

    return load_config(get_config_path())


def clear_config_cache() -> None:
    """清理配置缓存，主要用于测试。"""

    get_config.cache_clear()
