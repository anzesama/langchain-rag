"""
关系句格式工具：编码 / 解析

格式：source --[rel_type]--> target | description
"""

import re
from typing import Optional, Dict

PATTERN = re.compile(r'^(.*?) --\[(.*?)\]--> (.*?)(?:\| (.*?))?$')


def encode_relation(source: str, target: str, rel_type: str, description: str = "") -> str:
    """
    编码关系为文本格式

    Args:
        source: 源实体名
        target: 目标实体名
        rel_type: 关系类型
        description: 关系描述

    Returns:
        格式化的关系文本：source --[rel_type]--> target | description
    """
    if description:
        return f"{source} --[{rel_type}]--> {target} | {description}"
    return f"{source} --[{rel_type}]--> {target}"


def decode_relation(text: str) -> Optional[Dict[str, str]]:
    """
    解码关系文本

    Args:
        text: 格式化的关系文本

    Returns:
        包含 source, rel_type, target, description 的字典，解析失败返回 None
    """
    match = PATTERN.match(text.strip())
    if not match:
        return None
    return {
        "source": match.group(1).strip(),
        "rel_type": match.group(2).strip(),
        "target": match.group(3).strip(),
        "description": match.group(4).strip() if match.group(4) else ""
    }
