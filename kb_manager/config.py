"""
config.py — KB Manager 统一配置
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
RAG_DIR = BASE_DIR / "langchain-rag"
KB_MANAGER_DIR = RAG_DIR / "kb_manager"

# 数据目录
RAW_DIR = KB_MANAGER_DIR / "raw"
ANALYSIS_DIR = KB_MANAGER_DIR / "analysis"
METADATA_DIR = KB_MANAGER_DIR / "metadata"

# 确保目录存在
for d in [RAW_DIR, ANALYSIS_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 默认 TTL（天） — 分析结果有效期
DEFAULT_TTL_DAYS = 90

# 知识库新鲜度阈值（天）— 超过这个天数视为"过期"
FRESHNESS_THRESHOLD_DAYS = 30

# 采集配置
COLLECTOR_CONFIG = {
    "trend_radar_dir": BASE_DIR / "trend-radar",
    "policy_collector": "policy_collector.py",
    "default_days": 30,
    "default_limit": 30,
}

# 主题关键词映射（用于自动判断知识库覆盖度）
THEME_KEYWORDS = {
    "政策": ["政策", "国务院", "部委", "文件", "通知", "规划"],
    "经济": ["经济", "GDP", "财政", "货币", "利率", "通胀"],
    "消费": ["消费", "零售", "汽车", "电商", "免税"],
    "就业": ["就业", "失业", "招聘", "创业", "社保"],
    "科技": ["科技", "AI", "人工智能", "芯片", "半导体", "数据"],
    "能源": ["能源", "电力", "光伏", "风电", "石油", "天然气"],
    "环保": ["环保", "生态", "碳排放", "碳达峰", "碳中和"],
    "房地产": ["房地产", "住房", "楼市", "房价", "土地"],
    "教育": ["教育", "学校", "高考", "考研", "培训"],
    "医疗": ["医疗", "医保", "医院", "药品", "卫生"],
}
