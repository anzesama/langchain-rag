# 图检索 + 父子文档检索设计方案

> 日期：2026-07-27
> 状态：设计阶段

## 一、核心目标

1. **图检索**：将知识图谱关系向量化，支持向量召回 + 2-hop 扩展
2. **父子文档检索**：支持多级父子关系（章→节→段），检索时返回完整上下文
3. **模块合并**：两种检索方式独立实现，最终在 RAG 流程中合并

## 二、数据库变更

### 2.1 chunks 表结构

```sql
ALTER TABLE chunks ADD COLUMN parent_id TEXT;
```

**设计思路**：
- `parent_id` = 父块的 chunk_id
- 支持多级父子关系
- 现有数据 parent_id = NULL（向后兼容）

### 2.2 关系向量化表

**不需要额外表**，复用 chunks 表：
- content = `source --[type]--> target | description`
- metadata.type = "relation"

## 三、模块结构

```
rag_core/
├── graph_retriever/              # 图检索模块（新建）
│   ├── __init__.py
│   ├── indexer.py                # 关系向量化索引
│   ├── retriever.py              # 图检索逻辑
│   └── utils.py                  # 格式解析
├── parent_document_retriever/    # 父子检索模块（新建）
│   ├── __init__.py
│   ├── retriever.py              # 父子检索逻辑
│   └── utils.py                  # 分块策略
├── hybrid_retriever.py           # 混合检索器（修改）
└── knowledge_base.py             # RAG 入口（修改）
```

## 四、图检索实现

### 4.1 关系格式

```
source --[rel_type]--> target | description
```

**示例**：
```
CatBoost --[对比]--> XGBoost | CatBoost 训练速度更快
```

### 4.2 索引流程

```python
# 从 WikiDB 读取所有关系
relations = wiki_db.get_all_relationships()

# 编码为文本
content = f"{source} --[{rel_type}]--> {target} | {description}"

# 写入向量库
vector_store.add_documents([
    Document(page_content=content, metadata={
        "type": "relation",
        "source": source,
        "target": target,
        "rel_type": rel_type,
        "description": description
    })
])
```

### 4.3 检索流程

```
用户查询
  ↓
向量召回关系句（top_k=5）
  ↓
解析实体（source + target）
  ↓
2-hop 图库扩展
  ↓
生成 Fact List
  ↓
返回给 LLM
```

### 4.4 代码结构

**utils.py**：
- `encode_relation()` - 编码关系文本
- `decode_relation()` - 解码关系文本

**indexer.py**：
- `index_all_relations()` - 从 WikiDB 索引所有关系

**retriever.py**：
- `retrieve()` - 图检索主入口
- `to_prompt_context()` - 转换为 Prompt 上下文

## 五、父子文档检索实现

### 5.1 分块策略（精细模式）

```python
class RecursiveParentTextSplitter:
    """递归父子文本分割器"""
    
    def __init__(self, parent_chunk_size=2000, child_chunk_size=500):
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
    
    def split_text(self, text: str, parent_id: str = None):
        """递归分割文本"""
        # 1. 先分割成父块（整章/节）
        parent_chunks = self._split_parents(text, parent_id)
        
        # 2. 对每个父块，继续分割成子块（节/段）
        all_chunks = []
        for parent_chunk in parent_chunks:
            child_chunks = self._split_children(parent_chunk['content'], parent_chunk['chunk_id'])
            all_chunks.extend(child_chunks)
        
        return all_chunks
    
    def _split_parents(self, text: str, parent_id: str = None):
        """分割父块"""
        # 按章节标题分割
        # 返回父块列表（每个父块有 chunk_id 和 content）
        pass
    
    def _split_children(self, content: str, parent_id: str):
        """分割子块"""
        # RecursiveCharacterTextSplitter
        # 每个 child_chunk 有 parent_id
        pass
```

### 5.2 检索流程

```python
class ParentDocumentRetriever:
    """父子文档检索器"""
    
    def retrieve(self, query: str, top_k: int = 10):
        """检索父子文档"""
        # 1. 向量检索子块
        child_chunks = vector_store.search(query, top_k=top_k * 2)
        
        # 2. 提取父块 ID
        parent_ids = set(chunk.metadata.get('parent_id') for chunk in child_chunks)
        
        # 3. 召回父块
        parent_chunks = vector_store.search_by_ids(parent_ids, top_k=top_k)
        
        # 4. 返回父子上下文
        return child_chunks + parent_chunks
```

## 六、ChromaDB 适配

### 6.1 auto_search_import.py

**修改前**：
```python
def import_to_chromadb(self, query: str, parsed: list) -> int:
    kb.add_documents(parsed)  # ChromaDB
```

**修改后**：
```python
def import_to_chromadb(self, query: str, parsed: list) -> int:
    vector_store = VectorStoreManager()
    vector_store.add_documents(parsed)  # libsql
```

### 6.2 rag_cli.py

**修改前**：
```python
def _import_search_to_chromadb(results, query, kb):
    kb.add_documents(results)  # ChromaDB
```

**修改后**：
```python
def _import_search_to_chromadb(results, query, kb):
    vector_store = VectorStoreManager()
    vector_store.add_documents(results)  # libsql
```

## 七、RAG 流程合并

### 7.1 检索流程

```
用户查询
  ↓
┌─────────────────────────────────────────┐
│ 1. 图检索（GraphRetriever）              │
│    - 向量召回关系句                      │
│    - 2-hop 扩展                         │
│    - 生成 Fact List                     │
├─────────────────────────────────────────┤
│ 2. 父子检索（ParentDocumentRetriever）   │
│    - 向量检索子块                        │
│    - 召回父块                            │
│    - 返回完整上下文                      │
└─────────────────────────────────────────┘
  ↓
合并上下文：Fact List + 父子文档块
  ↓
LLM 生成回答
```

### 7.2 代码结构

**knowledge_base.py**：
```python
def query(self, query: str, top_k: int = 10) -> str:
    # 1. 图检索
    graph_result = graph_retriever.retrieve(query, top_k=5, hops=2)
    graph_context = graph_retriever.to_prompt_context(graph_result)
    
    # 2. 父子检索
    parent_result = parent_retriever.retrieve(query, top_k=5)
    parent_context = "\n\n".join([c.page_content for c in parent_result])
    
    # 3. 合并上下文
    combined = graph_context + "\n\n" + parent_context
    
    # 4. 生成回答
    return self._generate_answer(query, combined)
```

## 八、实现顺序

1. **数据库变更**
   - 删除现有数据库
   - 重新创建（parent_id 字段自动为 NULL）
   
2. **graph_retriever 模块**
   - utils.py - 格式解析
   - indexer.py - 关系向量化
   - retriever.py - 图检索逻辑
   
3. **parent_document_retriever 模块**
   - utils.py - 分块策略
   - retriever.py - 父子检索逻辑
   
4. **ChromaDB 适配**
   - auto_search_import.py
   - rag_cli.py
   
5. **RAG 流程合并**
   - 修改 hybrid_retriever.py（可选）
   - 修改 knowledge_base.py
   - 重新导入数据

## 九、测试策略

### 9.1 单元测试

```python
# tests/test_graph_retriever.py
def test_decode_relation()
def test_index_all_relations()
def test_retrieve()
def test_to_prompt_context()

# tests/test_parent_document_retriever.py
def test_split_text()
def test_retrieve()
```

### 9.2 集成测试

```python
def test_graph_retriever_integration()
def test_parent_retriever_integration()
def test_rag_query_with_both_retrievers()
```

## 十、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据库删除导致数据丢失 | 高 | 提前备份 |
| parent_id 设置复杂 | 中 | 先实现简单版本 |
| 检索性能下降 | 中 | 限制 top_k 和 hops |
| ChromaDB 适配错误 | 低 | 逐模块测试 |

## 十一、成功标准

1. 图检索能正确召回关系句并扩展到 2-hop
2. 父子检索能返回完整的父子上下文
3. RAG 查询能同时使用两种检索方式
4. 所有测试通过
