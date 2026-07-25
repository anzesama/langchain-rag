# P1 实施计划：语义级文档切分与质量评估框架

> 创建时间：2026-06-30 22:00
> 状态：🔄 进行中

---

## 目标

1. **语义级文档切分** — 基于标题层级的智能切分，而非固定长度
2. **质量评估框架** — 对每个 chunk 进行完整性、可读性、相关性评分
3. **离线评估数据集** — 创建基准测试集，用于验证切分效果

---

## 任务分解

### 任务 1：标题层级切分器（TitleHierarchyChunker）

**文件**：`langchain-rag/rag_core/chunkers/title_hierarchy.py`

**功能**：
- 解析 Markdown 文档的标题层级（H1, H2, H3）
- 根据标题边界切分文档，而非固定长度
- 保留标题层级信息作为元数据

**实现要点**：
```python
class TitleHierarchyChunker:
    def __init__(self, max_chunk_size=500):
        self.max_chunk_size = max_chunk_size
    
    def split_by_headings(self, markdown_text: str) -> List[Chunk]:
        """基于标题层级切分文档"""
        # 1. 解析标题层级
        headings = self._parse_headings(markdown_text)
        # 2. 按标题边界切分
        chunks = self._create_chunks(headings, markdown_text)
        # 3. 添加元数据（标题路径、层级深度）
        for chunk in chunks:
            chunk.metadata['heading_path'] = self._get_heading_path(chunk)
        return chunks
```

**验收标准**：
- [ ] 能正确解析多级标题结构
- [ ] 切分的 chunk 保持语义完整性
- [ ] 每个 chunk 包含标题路径元数据

### 任务 2：质量评估器（QualityAssessor）

**文件**：`langchain-rag/rag_core/quality/assessor.py`

**功能**：
- 对每个 chunk 进行多维度质量评分
- 提供质量改进建议

**评估维度**：
1. **完整性**（Completeness）— 内容是否完整，有无截断
2. **可读性**（Readability）— 语言是否通顺，有无乱码
3. **相关性**（Relevance）— 与主题的相关程度（需 LLM 辅助）

**实现要点**：
```python
class QualityAssessor:
    def assess(self, chunk: Chunk) -> QualityScore:
        """对单个 chunk 进行质量评估"""
        return QualityScore(
            completeness=self._check_completeness(chunk),
            readability=self._check_readability(chunk),
            relevance=self._check_relevance(chunk)
        )
    
    def _check_completeness(self, chunk: Chunk) -> float:
        """检查内容完整性"""
        # 1. 检查是否有完整的句子结尾
        # 2. 检查标题层级是否完整
        # 3. 检查列表/表格是否完整
        pass
    
    def _check_readability(self, chunk: Chunk) -> float:
        """检查可读性"""
        # 1. 计算句子平均长度
        # 2. 检测乱码/特殊字符
        # 3. 检查段落结构
        pass
```

**验收标准**：
- [ ] 能正确识别不完整的内容片段
- [ ] 能检测常见质量问题（乱码、截断）
- [ ] 评分结果与人工评估一致率 > 80%

### 任务 3：离线评估数据集（Offline Evaluation Dataset）

**文件**：`langchain-rag/tests/evaluation_dataset.json`

**功能**：
- 创建包含不同质量级别的基准测试集
- 用于验证切分器和评估器的效果

**数据集结构**：
```json
{
  "test_cases": [
    {
      "id": "tc_001",
      "document_type": "markdown",
      "content": "# 标题1\n## 标题2\n...",
      "expected_chunks": 3,
      "quality_scores": {
        "tc_001_chunk_0": {"completeness": 0.9, "readability": 0.95},
        "tc_001_chunk_1": {"completeness": 0.7, "readability": 0.8}
      }
    }
  ]
}
```

**验收标准**：
- [ ] 包含至少 10 个不同类型的测试用例
- [ ] 每个用例有预期切分结果和质量评分
- [ ] 能自动运行评估并生成报告

---

## 依赖关系

- [ ] 任务 1 → 任务 2（质量评估需要 chunk 作为输入）
- [ ] 任务 1 → 任务 3（评估数据集需要切分器）
- [ ] 任务 2 → 任务 3（评估数据集需要质量评估器）

---

## 预计工作量

- 任务 1：2-3 小时
- 任务 2：3-4 小时
- 任务 3：1-2 小时

**总计**：6-9 小时

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 标题解析复杂 | 任务延期 | 先支持简单场景，逐步增强 |
| 质量评估不准确 | 效果不佳 | 引入 LLM 辅助评估 |
| 数据集覆盖不足 | 评估偏差 | 收集真实文档样本 |

---

*计划创建完成，等待实施。*
