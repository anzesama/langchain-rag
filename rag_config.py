"""
RAG 系统统一配置
"""
import os
from pathlib import Path

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).parent.resolve()
DOCUMENTS_DIR = BASE_DIR / "documents"       # 文档存放目录
STORAGE_DIR = BASE_DIR / "storage"            # ChromaDB 存储目录

# 确保目录存在
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 向量存储配置 ====================
VECTOR_STORE_NAME = "knowledge_base"
VECTOR_STORE_PERSIST_DIR = STORAGE_DIR / VECTOR_STORE_NAME

# 向量维度（与 embedding 模型匹配）
# bge-small-zh-v1.5 是 512 维
VECTOR_DIMENSION = 512

# ChromaDB 持久化目录
LIBSQL_DICTIONARY_PATH = STORAGE_DIR / "knowledge_base.db"

# ==================== Embedding 配置 ====================
EMBEDDING_MODE = os.getenv("RAG_EMBEDDING_MODE", "local")  # "local" | "openai"

# 本地 Embedding 模型（中文优化）
LOCAL_EMBEDDING_MODEL = os.getenv(
    "RAG_LOCAL_EMBEDDING_MODEL",
    "BAAI/bge-small-zh-v1.5"
)
LOCAL_EMBEDDING_DIM = 512  # bge-small-zh-v1.5 的输出维度

# OpenAI 兼容 Embedding 配置
OPENAI_EMBEDDING_MODEL = os.getenv(
    "RAG_OPENAI_EMBEDDING_MODEL",
    "text-embedding-ada-002"
)
OPENAI_API_KEY = os.getenv("RAG_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("RAG_OPENAI_BASE_URL", None)

# ==================== GitHub API 配置 ====================
GITHUB_API_KEY = os.getenv("RAG_GITHUB_API_KEY", "")
GITHUB_API_BASE = "https://api.github.com"

# ==================== 数据源配置 ====================
ENABLE_GITHUB_SEARCH = os.getenv("RAG_ENABLE_GITHUB_SEARCH", "true").lower() == "true"
ENABLE_TAVILY_SEARCH = os.getenv("RAG_ENABLE_TAVILY_SEARCH", "true").lower() == "true"

# ==================== LLM 配置（云端推理） ====================
LLM_MODEL = os.getenv("RAG_LLM_MODEL", "agnes-2.0-flash")
LLM_TEMPERATURE = float(os.getenv("RAG_LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("RAG_LLM_MAX_TOKENS", "2048"))

AGNES_API_KEY = os.getenv("RAG_AGNES_API_KEY", "sk-MEQQLoMut6kdisHzDdRWnjPr0bmz3bLcGBD5A7zJHUKASnvS")
AGNES_API_BASE = os.getenv("RAG_AGNES_API_BASE", "https://apihub.agnes-ai.com")

# ==================== 自动资源平衡 ====================
import psutil

def get_optimal_threads():
    """根据 CPU 核心数计算最优线程数（保留 1-2 核给系统）"""
    cpu_count = os.cpu_count() or 4
    return max(1, cpu_count // 2) if cpu_count > 2 else 1

def get_optimal_batch_size():
    """根据可用内存动态计算 Embedding 批次大小"""
    try:
        mem = psutil.virtual_memory()
        safe_mem = mem.available / (1024**3) * 0.3  # 使用可用内存的 30%
        if safe_mem > 16:
            return 128
        elif safe_mem > 8:
            return 64
        elif safe_mem > 4:
            return 32
        else:
            return 16
    except ImportError:
        # psutil 未安装时降级为默认值
        return 64

# 自动计算的值（供脚本使用）
AUTO_OMP_THREADS = get_optimal_threads()
AUTO_EMBEDDING_BATCH_SIZE = get_optimal_batch_size()

# ==================== 文档加载配置 ====================
CHUNK_SIZE = 500           # 每块字符数
CHUNK_OVERLAP = 50         # 块之间重叠字符数

# 分批加载配置（大文件自动分批）
ADD_BATCH_SIZE = 500       # ChromaDB 每批插入文档数
EMBEDDING_BATCH_SIZE = AUTO_EMBEDDING_BATCH_SIZE  # 使用自动计算的批次大小

# ==================== LSH 索引配置 ====================
LSH_INDEX_PATH = STORAGE_DIR / "novel_lsh.index"  # FAISS LSH 索引文件
ID_MAP_PATH = STORAGE_DIR / "id_map.pkl"          # ID 映射文件
LOAD_STATE_PATH = STORAGE_DIR / "load_state.json" # 加载进度文件
LSH_DIM = 512  # 与 bge-small-zh-v1.5 模型维度一致
LSH_NBITS = 2048  # LSH 位数（dim × 4）

# ==================== 小说加载配置 ====================
NOVEL_SPLIT_PATTERN = r"第[一二三四五六七八九十百千0-9]+[章节回卷集篇]"
NOVEL_CHAPTERS_DIR = DOCUMENTS_DIR / "novel_chapters"

# ==================== LSH 索引存储 ====================
LSH_INDEX_DIR = STORAGE_DIR / "lsh_index"
LSH_INDEX_FILE = LSH_INDEX_DIR / "index.faiss"
LSH_ID_MAP_FILE = LSH_INDEX_DIR / "id_map.pkl"
LSH_LOAD_STATE_FILE = LSH_INDEX_DIR / "load_state.json"

# ==================== 召回阈值 ====================
LSH_RECALL_MIN_COUNT = 5       # LSH 最少返回数
LSH_RECALL_MIN_SCORE = 0.6     # 最低相似度分数

# ==================== 同步双写 ====================
SYNC_DOUBLE_WRITE = True       # True=同步双写, False=仅写ChromaDB

# ==================== 架构开关 ====================
USE_NEW_ARCHITECTURE = True    # True=使用新架构, False=回滚到旧版本

# 支持的文档类型
SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".rst", ".docx", ".pptx",
    ".xlsx", ".xls", ".csv", ".json", ".html", ".htm"
}

# ==================== 检索配置 ====================
TOP_K = 5                  # 检索返回的 top-K 相似文档块
SCORE_THRESHOLD = 0.3      # 相似度阈值（0-1），低于此值视为不相关

# ==================== RAG Prompt 模板 ====================
RAG_SYSTEM_PROMPT = """你是一个智能知识库助手。请根据以下检索到的文档内容回答问题。

要求：
1. 只基于提供的文档内容作答，不要编造信息
2. 如果文档中没有相关信息，明确告知"根据现有文档，无法回答此问题"
3. 引用来源时标注文档文件名
4. 回答要简洁、准确、有条理
5. 如果多个文档有冲突信息，指出差异并提供各自出处

检索到的文档内容：
{context}

用户问题：
{question}
"""

# ==================== HTTP 服务配置 ====================
RAG_SERVER_HOST = os.getenv("RAG_SERVER_HOST", "0.0.0.0")
RAG_SERVER_PORT = int(os.getenv("RAG_SERVER_PORT", "8765"))

# ==================== 日志配置 ====================
# ==================== 日志配置 ====================
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(STORAGE_DIR / "rag.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("rag")

# 禁用 ChromaDB 遥测（防止发送使用数据）
os.environ["POSTHOG_OFF"] = "1"
os.environ["POSTHOG_JS_OFF"] = "1"

# ==================== 事实核查配置 ====================
ENABLE_FACT_CHECKING = os.getenv("RAG_ENABLE_FACT_CHECKING", "false").lower() == "true"
MAX_SOURCES_FOR_VERIFICATION = int(os.getenv("RAG_MAX_SOURCES_FOR_VERIFICATION", "3"))
