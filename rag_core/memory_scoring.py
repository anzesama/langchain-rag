"""脑启发性记忆评分 —— 纯函数（无 IO、无全局状态）

设计依据：
- 三层记忆模型 + LUFY 六维重要性（规则版先行，Q1=C 的「规则打底」部分）
- 艾宾浩斯**软遗忘**：只降权，不删除

保持「平铺模块 + 纯函数」，便于单测（YAGNI）。

⚠️ 半衰期语义：`forgetting_decay` 的 `half_life_days` 是**真正的半衰期**，
   经过 1 个半衰期后记忆强度恰好剩 50%（`2 ** (-Δ/H)`）。
   设计草稿写的是 `exp(-Δ/H)`，那实际是「1/e 点」（36.8%），与「半衰期」之名不符 ——
   此处按语义修正为真半衰期。
"""
import math
import os
import re
from datetime import datetime
from typing import Optional, Tuple, Union

# ------------------------------------------------------------------ 常量

#: 半衰期（天）——Q2=A 用户选定 7 天；可用环境变量 `RAG_RECALL_HALF_LIFE` 覆盖
DEFAULT_HALF_LIFE_DAYS = 7.0

#: 命中次数达到该值即「巩固」为长期记忆
CONSOLIDATE_THRESHOLD = 3

#: 检索命中时的突触强化系数
REINFORCE_FACTOR = 1.05

#: 访问频率加成上限
MAX_ACCESS_BONUS = 1.5

#: 访问频率加成系数
ACCESS_BONUS_COEF = 0.1

#: 重要性的中性基线（避免「无信号」文本被打到 0）
BASE_IMPORTANCE = 0.3

#: 文本过短罚分
SHORT_TEXT_PENALTY = 0.15
SHORT_TEXT_THRESHOLD = 50

#: 长文本加分（可能是重要章节）
LONG_TEXT_BONUS = 0.1
LONG_TEXT_THRESHOLD = 1000

#: 命中「重要性信号」词时的加分
PATTERN_BONUS = 0.2

#: 重要性信号（LUFY 六维的规则近似：有用性 / 情感强度 / 关联度）
IMPORTANT_PATTERNS = (
    r"重要.{0,6}发现|关键.{0,6}结论|核心.{0,6}观点",
    r"经验.{0,6}总结|教训|最佳实践",
    r"错误|失败|bug|修复|事故|报错",
    r"决策|决定|选择",
)

#: 来源权重（前缀匹配，小写比较）
SOURCE_WEIGHTS = (
    ("troubleshooting", 0.5),
    ("project_info", 0.4),
    ("research", 0.25),
    ("readme", 0.2),
    ("novel", -0.15),
)

_IMPORTANT_RE = [re.compile(p, re.IGNORECASE) for p in IMPORTANT_PATTERNS]


# ------------------------------------------------------------------ 工具

def _resolve_half_life() -> float:
    """从环境变量读取半衰期，非法值回退默认"""
    raw = os.environ.get("RAG_RECALL_HALF_LIFE")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return DEFAULT_HALF_LIFE_DAYS


def _parse_time(value: Union[None, str, datetime]) -> Optional[datetime]:
    """把 ISO 字符串 / datetime 统一成 naive datetime；无法解析返回 None"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).replace(tzinfo=None)
        except ValueError:
            return None
    return None


# ------------------------------------------------------- 静态重要性评分

def compute_importance(text: str, source: str = "", metadata: Optional[dict] = None) -> float:
    """静态重要性评分（导入时一次性计算），返回 0.0 ~ 1.0。

    规则版先行（Q1=C：规则引擎打底，灰区再交 LLM 复核）。
    维度近似：有用性（关键词）/ 频率（来源）/ 时效性（长度）等。
    """
    text = text or ""
    source = (source or "").lower()
    score = BASE_IMPORTANCE

    # 1. 长度信号
    length = len(text)
    if length < SHORT_TEXT_THRESHOLD:
        score -= SHORT_TEXT_PENALTY
    elif length > LONG_TEXT_THRESHOLD:
        score += LONG_TEXT_BONUS

    # 2. 关键词信号（命中一个即加一次，不叠加同类多次）
    for pattern in _IMPORTANT_RE:
        if pattern.search(text):
            score += PATTERN_BONUS

    # 3. 来源权重（首个命中的前缀）
    for prefix, weight in SOURCE_WEIGHTS:
        if source.startswith(prefix):
            score += weight
            break

    return max(0.0, min(1.0, score))


# ----------------------------------------------------------- 软遗忘衰减

def forgetting_decay(
    last_access: Union[None, str, datetime],
    now: Optional[datetime] = None,
    half_life_days: Optional[float] = None,
) -> float:
    """艾宾浩斯软遗忘衰减，返回 0.0 ~ 1.0。

    - `last_access is None`（从未被检索）→ 1.0，**不惩罚新内容**
    - 未来时间戳（时钟漂移）→ 钳制到 1.0，不产生额外加成
    - 半衰期语义：Δ = half_life_days 时返回 0.5

    :param last_access: datetime / ISO 字符串 / None
    :param now: 参照时间，默认 `datetime.utcnow()`
    :param half_life_days: 半衰期（天），默认取 `RAG_RECALL_HALF_LIFE` 或 7.0
    """
    last = _parse_time(last_access)
    if last is None:
        return 1.0

    reference = now.replace(tzinfo=None) if isinstance(now, datetime) else datetime.utcnow()
    half_life = _resolve_half_life() if half_life_days is None else float(half_life_days)
    if half_life <= 0:
        half_life = DEFAULT_HALF_LIFE_DAYS

    elapsed_days = (reference - last).total_seconds() / 86400.0
    if elapsed_days <= 0:
        return 1.0

    return max(0.0, min(1.0, 2.0 ** (-elapsed_days / half_life)))


# ------------------------------------------------------------- 综合评分

def compute_final_score(
    similarity: float,
    importance: float,
    decay: float,
    access_count: int,
) -> float:
    """综合评分 = 相似度 × 重要性加成 × 访问加成 × 遗忘衰减。

    - 重要性加成 ∈ [0.5, 1.0]
    - 访问加成 ∈ [1.0, 1.5]（封顶，防高频内容霸榜）
    - 软遗忘铁律：衰减只降权，**永不归零到「删除」**
    """
    importance = max(0.0, min(1.0, float(importance or 0.0)))
    decay = max(0.0, float(decay if decay is not None else 1.0))
    count = max(0, int(access_count or 0))

    importance_bonus = 0.5 + 0.5 * importance
    access_bonus = min(MAX_ACCESS_BONUS, 1.0 + ACCESS_BONUS_COEF * math.log1p(count))

    return float(similarity) * importance_bonus * access_bonus * decay


# --------------------------------------------------------- 检索后强化

def update_after_retrieval(access_count: int, importance: float) -> Tuple[int, float]:
    """检索命中后的「突触强化」：命中次数 +1，重要性 ×1.05（封顶 1.0）。

    （`last_access` 与 `consolidated` 由 DB 层负责，纯函数不做 IO。）
    """
    new_count = max(0, int(access_count or 0)) + 1
    new_importance = min(1.0, max(0.0, float(importance or 0.0)) * REINFORCE_FACTOR)
    return new_count, new_importance
