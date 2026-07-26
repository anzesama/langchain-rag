"""
utils.py — KB Manager 通用工具函数
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


def generate_fingerprint(content: str) -> str:
    """生成内容的 SHA256 指纹，用于去重"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    """当前 ISO 时间字符串"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ttl_until(days: int = 90) -> str:
    """计算 TTL 到期时间"""
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def save_json(filepath: Path, data: Any) -> Path:
    """保存 JSON 文件，自动创建目录"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def load_json(filepath: Path) -> Optional[Any]:
    """加载 JSON 文件"""
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_files(directory: Path, extension: str = ".json") -> list:
    """列出目录下指定扩展名的文件"""
    if not directory.exists():
        return []
    return sorted(directory.glob(f"*{extension}"))


def parse_metadata(filename: str) -> Optional[Dict[str, Any]]:
    """从文件名解析元数据
    格式: {type}_{timestamp}_{fingerprint}.json
    例如: policy_20260625_a1b2c3d4.json
    """
    parts = filename.replace(".json", "").split("_")
    if len(parts) < 2:
        return None
    return {
        "type": parts[0],
        "timestamp": parts[1] if len(parts) > 1 else "",
        "fingerprint": parts[2] if len(parts) > 2 else "",
    }
