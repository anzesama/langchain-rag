"""
Embedding 服务 — 支持本地模型和 OpenAI 兼容 API 切换
"""
import os
from typing import List

from rag_config import logger, EMBEDDING_MODE, LOCAL_EMBEDDING_MODEL, OPENAI_EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE

# ==================== 设置 HuggingFace 国内镜像 ====================
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def get_embeddings(texts: List[str], batch_size: int = None) -> List[List[float]]:
    """
    获取文本的 embedding 向量
    
    Args:
        texts: 待嵌入的文本列表
        batch_size: 每批数量，默认使用 EMBEDDING_BATCH_SIZE
        
    Returns:
        embedding 向量列表
    """
    if batch_size is None:
        batch_size = EMBEDDING_BATCH_SIZE
    
    if EMBEDDING_MODE == "local":
        return _get_local_embeddings(texts, batch_size)
    elif EMBEDDING_MODE == "openai":
        return _get_openai_embeddings(texts, batch_size)
    else:
        raise ValueError(f"未知的 embedding 模式: {EMBEDDING_MODE}")


def _get_local_embeddings(texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
    """使用本地 sentence-transformers 模型（分批处理）
    
    注意：会过滤掉导致 embedding 失败的文本
    """
    from sentence_transformers import SentenceTransformer
    
    model = SentenceTransformer(LOCAL_EMBEDDING_MODEL, device="cpu")
    
    # 过滤掉可能导致 embedding 失败的文本
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        if '>>>' in text:
            continue
        if 'array(' in text:
            continue
        valid_texts.append(text)
        valid_indices.append(i)
    
    if not valid_texts:
        return []
    
    # 分批编码
    all_embeddings = []
    total = len(valid_texts)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = valid_texts[start:end]
        logger.debug(f"Embedding batch [{start}:{end}]/{total}")
        batch_emb = model.encode(batch, normalize_embeddings=True)
        all_embeddings.extend(batch_emb.tolist())
    
    # 构建结果：被过滤的用零向量占位
    result = [[0.0] * len(all_embeddings[0]) for _ in range(len(texts))]
    for j, idx in enumerate(valid_indices):
        result[idx] = all_embeddings[j]
    
    return result


def _get_openai_embeddings(texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
    """使用 OpenAI 兼容 API（分批处理，避免请求过大）"""
    from openai import OpenAI
    
    kwargs = {}
    api_key = os.getenv("RAG_OPENAI_API_KEY", "")
    base_url = os.getenv("RAG_OPENAI_BASE_URL", None)
    
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    
    client = OpenAI(**kwargs)
    
    # OpenAI API 有单次请求 token 限制，分批处理
    all_embeddings = []
    total = len(texts)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = texts[start:end]
        logger.debug(f"OpenAI embedding batch [{start}:{end}]/{total}")
        response = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])
    
    return all_embeddings
