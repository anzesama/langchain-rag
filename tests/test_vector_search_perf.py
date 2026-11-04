"""向量检索性能与正确性（2026-11-03 事故回归防护）。

背景：`_cosine_similarity_query` 旧实现逐行 `np.dot`，且**每轮循环重算**
`np.linalg.norm(query_embedding)`，并对全部行做 `json.loads`。
实测 13198 chunks 时 `/api/search_raw` avg 11.2s / max 50.9s，
而向量化 `matrix @ q` 仅 ~0.07s。

本测试用合成向量库（不依赖 embedding 模型）验证：
1. top-k 结果与 numpy 参考实现一致（正确性）
2. 大规模检索在合理时间内完成（性能）
"""
import json
import sqlite3
import time

import numpy as np
import pytest

from rag_core.vector_store_libsql import VectorStoreManager

N = 20000
DIM = 512
TOP_K = 5
# 向量化实现约 0.05~0.1s；逐行旧实现约 0.5~0.7s。阈值取其间的 0.35s。
TIME_BUDGET_SEC = 0.35


@pytest.fixture
def populated_store(tmp_path):
    """临时库里塞入 N 条合成向量（隔离：绝不碰生产库）"""
    vs = VectorStoreManager(persist_dir=tmp_path)
    rng = np.random.default_rng(20261103)
    vecs = rng.normal(size=(N, DIM)).astype(np.float32)

    rows = [
        (
            f"chunk_{i}",
            f"合成文本 {i}",
            vs._vector_to_blob(vecs[i]),
            json.dumps({"source": f"doc_{i % 50}.txt", "idx": i}),
            f"doc_{i % 50}.txt",
        )
        for i in range(N)
    ]
    conn = sqlite3.connect(str(vs.db_path))
    conn.executemany(
        "INSERT INTO chunks (chunk_id, text_content, vector, metadata, source) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return vs, vecs, rng


def _reference_topk(vecs: np.ndarray, q: np.ndarray, k: int):
    """numpy 参考实现：标准余弦相似度 top-k"""
    qn = q / (np.linalg.norm(q) or 1.0)
    vn = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)
    sims = vn @ qn
    order = np.argsort(-sims)[:k]
    return [f"chunk_{i}" for i in order]


def test_cosine_search_matches_reference(populated_store):
    """正确性：返回的 top-k 与 numpy 参考一致"""
    vs, vecs, rng = populated_store
    q = rng.normal(size=DIM).astype(np.float32)

    results = vs._cosine_similarity_query(q, top_k=TOP_K)

    assert len(results) == TOP_K
    got_ids = [r[0]["chunk_id"] for r in results]
    expected_ids = _reference_topk(vecs, q, TOP_K)
    assert got_ids == expected_ids, f"top-k 不一致: {got_ids} vs {expected_ids}"

    # 相似度单调不增
    scores = [r[1] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_cosine_search_is_fast_on_large_store(populated_store):
    """性能：N=20000 检索必须在预算内完成（旧逐行实现会超时）"""
    vs, _vecs, rng = populated_store
    q = rng.normal(size=DIM).astype(np.float32)

    # 预热（排除首次调用的缓存/分配开销）
    vs._cosine_similarity_query(q, top_k=TOP_K)

    t0 = time.perf_counter()
    results = vs._cosine_similarity_query(q, top_k=TOP_K)
    elapsed = time.perf_counter() - t0
    print(f"elapsed(N={N}) = {elapsed:.3f}s")

    assert len(results) == TOP_K
    assert elapsed < TIME_BUDGET_SEC, (
        f"检索太慢: {elapsed:.2f}s（预算 {TIME_BUDGET_SEC}s）。"
        f"疑似回退到逐行 np.dot / 循环内重算 norm 的实现。"
    )
