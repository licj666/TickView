"""配置模块: 读写本地 JSON 配置, 损坏时备份并回退默认值."""
import copy
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)

CODE_RE = re.compile(r"^(sh|sz|bj)\d{6}$")

DEFAULT_CONFIG = {
    "stocks": [{"code": "sh600519", "upper": None, "lower": None}],
    "opacity": 0.85,
    "mode": "carousel",        # carousel=单行轮播, list=纵向列表
    "carousel_interval": 5,    # 轮播切换间隔(秒)
    "always_on_top": True,     # 悬浮条是否始终置顶
    "window_x": None,          # 上次窗口位置, None=首次运行用默认位置
    "window_y": None,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "TickView"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TickView"
    return Path.home() / ".config" / "TickView"


def config_path() -> Path:
    return config_dir() / "config.json"


def _to_price(value):
    """预警价: 正数有效, 其余一律视为未设置."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def _validate(data: dict) -> dict:
    """逐字段校验, 非法字段回退默认值."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return cfg

    if isinstance(data.get("stocks"), list):
        stocks = []
        for item in data["stocks"]:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            if not isinstance(code, str) or not CODE_RE.match(code):
                continue
            stocks.append({
                "code": code,
                "upper": _to_price(item.get("upper")),
                "lower": _to_price(item.get("lower")),
            })
        cfg["stocks"] = stocks

    opacity = data.get("opacity")
    if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
        cfg["opacity"] = min(1.0, max(0.3, float(opacity)))

    if data.get("mode") in ("carousel", "list"):
        cfg["mode"] = data["mode"]

    if isinstance(data.get("always_on_top"), bool):
        cfg["always_on_top"] = data["always_on_top"]

    interval = data.get("carousel_interval")
    if isinstance(interval, int) and not isinstance(interval, bool):
        cfg["carousel_interval"] = min(60, max(2, interval))

    for key in ("window_x", "window_y"):
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            cfg[key] = value

    return cfg


def load() -> dict:
    path = config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("配置文件损坏, 已备份并回退默认配置: %s", e)
        try:
            shutil.copy(path, path.with_suffix(".json.bak"))
        except OSError as backup_err:
            log.warning("配置备份失败: %s", backup_err)
        return copy.deepcopy(DEFAULT_CONFIG)
    return _validate(data)


def save(cfg: dict) -> None:
    """原子写入: 先写临时文件再替换, 避免写一半损坏配置."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        tmp = config_path().with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        tmp.replace(config_path())
    except OSError as e:
        log.error("配置保存失败: %s", e)
