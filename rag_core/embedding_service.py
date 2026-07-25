"""
Embedding 服务 — 支持本地模型和 OpenAI 兼容 API 切换
"""
import os
from typing import List

from rag_config import logger, EMBEDDING_MODE, LOCAL_EMBEDDING_MODEL, OPENAI_EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE

# ==================== 设置 HuggingFace 国内镜像 ====================
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# ==================== 全局模型缓存 ====================
_MODEL_CACHE = None


def get_embeddings(texts: List[str], batch_size: int = None) -> List[List[float]]:
    if batch_size is None:
        batch_size = EMBEDDING_BATCH_SIZE

    if EMBEDDING_MODE == "local":
        return _get_local_embeddings(texts, batch_size)
    elif EMBEDDING_MODE == "openai":
        return _get_openai_embeddings(texts, batch_size)
    else:
        raise ValueError(f"未知的 embedding 模式: {EMBEDDING_MODE}")


def _get_local_embeddings(texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
    from sentence_transformers import SentenceTransformer
    import torch
    global _MODEL_CACHE

    # 1. 加载模型（全局缓存，只加载一次）
    if _MODEL_CACHE is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            torch.cuda.set_per_process_memory_fraction(0.8)
            print(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            os.environ["OMP_NUM_THREADS"] = "2"
            print("Using CPU (thread limit enabled)")
        _MODEL_CACHE = SentenceTransformer(LOCAL_EMBEDDING_MODEL, device=device)
        if device == "cuda":
            _MODEL_CACHE.half()   # 半精度省显存

    model = _MODEL_CACHE

    # 2. 过滤无效文本
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        if '>>>' in text or 'array(' in text:
            continue
        valid_texts.append(text)
        valid_indices.append(i)

    if not valid_texts:
        return []

    # 3. 分批编码
    all_embeddings = []
    total = len(valid_texts)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = valid_texts[start:end]
        batch_emb = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.extend(batch_emb.tolist())

    # 4. 重建结果（被过滤的用零向量占位）
    if not all_embeddings:
        return []
    result = [[0.0] * len(all_embeddings[0]) for _ in range(len(texts))]
    for j, idx in enumerate(valid_indices):
        result[idx] = all_embeddings[j]
    return result


def _get_openai_embeddings(texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
    from openai import OpenAI

    kwargs = {}
    api_key = os.getenv("RAG_OPENAI_API_KEY", "")
    base_url = os.getenv("RAG_OPENAI_BASE_URL", None)

    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)

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