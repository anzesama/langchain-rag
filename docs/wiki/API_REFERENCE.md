# Wiki 层 API 参考

本文档提供 Wiki 层的完整 API 参考。

## 目录

- [WikiDB](#wikidb)
  - [add_entity](#add_entity)
  - [add_relationship](#add_relationship)
  - [get_entity](#get_entity)
  - [get_entity_id](#get_entity_id)
  - [get_relations](#get_relations)
  - [get_fact_query_answer](#get_fact_query_answer)
  - [get_all_entities](#get_all_entities)
  - [get_stats](#get_stats)
  - [entity_exists](#entity_exists)
  - [update_aliases](#update_aliases)
  - [init_db](#init_db)
  - [connect](#connect)

- [WikiRouter](#wikirouter)
  - [route](#route)
  - [is_fact_query](#is_fact_query)

- [WikiUpdater](#wikiupdater)
  - [scan_new_entities](#scan_new_entities)
  - [scan_new_relations](#scan_new_relations)
  - [batch_add_from_text](#batch_add_from_text)
  - [review_candidates](#review_candidates)
  - [export_candidates](#export_candidates)
  - [import_candidates](#import_candidates)
  - [get_stats](#get_stats)

- [KnowledgeGraphVisualizer](#knowledgegraphvisualizer)
  - [build_graph](#build_graph)
  - [draw_graph](#draw_graph)
  - [save_graph_data](#save_graph_data)
  - [get_stats](#get_stats)

---

## WikiDB

Wiki 数据库主类，提供实体和关系的管理功能。

### add_entity

添加实体到 Wiki 数据库。

**签名**：
```python
def add_entity(
    self,
    name: str,
    entity_type: str,
    properties: Dict[str, Any] = None,
    aliases: List[str] = None,
    source_chapter: str = None,
    entity_id: str = None
) -> bool
```

**参数**：
- `name`: 实体名称（必需）
- `entity_type`: 实体类型（必需），可选值：人物、蛊虫、流派、势力、事件、地点、境界、未分类
- `properties`: 属性字典（可选）
- `aliases`: 别名列表（可选）
- `source_chapter`: 首次出现章节（可选）
- `entity_id`: 实体 ID（可选，默认自动生成）

**返回**：
- `bool`: 是否成功添加

**示例**：
```python
wiki_db.add_entity(
    name="方源",
    entity_type="人物",
    properties={
        "真名": "古月方源",
        "年龄": "重生时约15岁",
        "核心目标": "永生"
    },
    aliases=["方正", "黑土"],
    source_chapter="第1章"
)
```

### add_relationship

添加实体关系到 Wiki 数据库。

**签名**：
```python
def add_relationship(
    self,
    source_name: str,
    target_name: str,
    rel_type: str,
    properties: Dict[str, Any] = None,
    source_chapter: str = None
) -> bool
```

**参数**：
- `source_name`: 源实体名称（必需）
- `target_name`: 目标实体名称（必需）
- `rel_type`: 关系类型（必需），可选值：持有、属于、主修、背叛、盟友、师承、同伴、利用等
- `properties`: 关系属性（可选）
- `source_chapter`: 来源章节（可选）

**返回**：
- `bool`: 是否成功添加

**示例**：
```python
wiki_db.add_relationship(
    source_name="方源",
    target_name="力道",
    rel_type="主修",
    properties={"置信度": "高"},
    source_chapter="第1章"
)
```

### get_entity

获取实体信息。

**签名**：
```python
def get_entity(self, name: str) -> Optional[Dict[str, Any]]
```

**参数**：
- `name`: 实体名称（必需）

**返回**：
- `dict`: 实体信息，包含以下字段：
  - `id`: 实体 ID
  - `name`: 实体名称
  - `type`: 实体类型
  - `properties`: 属性字典
  - `aliases`: 别名列表
  - `source_chapter`: 来源章节

**示例**：
```python
entity = wiki_db.get_entity("方源")
print(f"实体类型: {entity['type']}")
print(f"属性: {entity['properties']}")
```

### get_entity_id

获取实体 ID。

**签名**：
```python
def get_entity_id(self, name: str) -> Optional[str]
```

**参数**：
- `name`: 实体名称（必需）

**返回**：
- `str`: 实体 ID，如果不存在返回 None

**示例**：
```python
entity_id = wiki_db.get_entity_id("方源")
```

### get_relations

获取实体的所有关系。

**签名**：
```python
def get_relations(self, entity_name_or_id: str, rel_type: str = None) -> List[Dict[str, Any]]
```

**参数**：
- `entity_name_or_id`: 实体名称或 ID（必需）
- `rel_type`: 关系类型（可选，不传则返回所有类型）

**返回**：
- `list`: 关系列表，每个关系包含：
  - `id`: 关系 ID
  - `source`: 源实体名称
  - `target`: 目标实体名称
  - `rel_type`: 关系类型
  - `properties`: 关系属性
  - `source_chapter`: 来源章节

**示例**：
```python
# 获取所有关系
relations = wiki_db.get_relations("方源")

# 获取特定类型的关系
relations = wiki_db.get_relations("方源", "持有")
```

### get_fact_query_answer

执行事实查询。

**签名**：
```python
def get_fact_query_answer(self, query: str) -> Optional[str]
```

**参数**：
- `query`: 查询文本（必需）

**返回**：
- `str`: 查询答案，格式为 "{主体} {关系} 的对象: {目标}"，如果找不到则返回 None

**示例**：
```python
# 查询主修关系
answer = wiki_db.get_fact_query_answer("方源主修什么？")
# 返回: "方源 主修 的对象: 力道, 奴道"

# 查询持有关系
answer = wiki_db.get_fact_query_answer("谁持有春秋蝉？")
# 返回: "春秋蝉 -持有-> 方源"

# 查询师承关系
answer = wiki_db.get_fact_query_answer("元始仙尊师从谁？")
# 返回: "元始仙尊 -师承-> 星宿仙尊"
```

### get_all_entities

获取所有实体。

**签名**：
```python
def get_all_entities(self) -> List[Dict[str, Any]]
```

**返回**：
- `list`: 实体列表，每个实体包含：
  - `id`: 实体 ID
  - `name`: 实体名称
  - `type`: 实体类型
  - `properties`: 属性字典
  - `aliases`: 别名列表
  - `source_chapter`: 来源章节

**示例**：
```python
entities = wiki_db.get_all_entities()
for entity in entities:
    print(f"{entity['name']} ({entity['type']})")
```

### get_stats

获取 Wiki 数据库统计信息。

**签名**：
```python
def get_stats(self) -> Dict[str, Any]
```

**返回**：
- `dict`: 统计信息，包含：
  - `total_entities`: 总实体数
  - `total_relationships`: 总关系数
  - `entities`: 实体类型分布（字典）
  - `relationships`: 关系类型分布（字典）

**示例**：
```python
stats = wiki_db.get_stats()
print(f"总实体数: {stats['total_entities']}")
print(f"总关系数: {stats['total_relationships']}")
```

### entity_exists

检查实体是否存在。

**签名**：
```python
def entity_exists(self, name: str) -> bool
```

**参数**：
- `name`: 实体名称（必需）

**返回**：
- `bool`: 实体是否存在

**示例**：
```python
if wiki_db.entity_exists("方源"):
    print("实体存在")
```

### update_aliases

更新实体的别名列表。

**签名**：
```python
def update_aliases(self, name: str, aliases: List[str], add: bool = True) -> bool
```

**参数**：
- `name`: 实体名称（必需）
- `aliases`: 别名列表（必需）
- `add`: 是否添加（默认 True）

**返回**：
- `bool`: 是否成功

**示例**：
```python
# 添加别名
wiki_db.update_aliases("方源", ["方正", "黑土"], add=True)

# 移除别名
wiki_db.update_aliases("方源", ["方正"], add=False)
```

### init_db

初始化 Wiki 数据库。

**签名**：
```python
def init_db(self) -> None
```

**示例**：
```python
wiki_db.init_db()
```

### connect

获取数据库连接。

**签名**：
```python
def connect(self) -> sqlite3.Connection
```

**返回**：
- `sqlite3.Connection`: 数据库连接对象

**示例**：
```python
conn = wiki_db.connect()
cursor = conn.cursor()
cursor.execute("SELECT * FROM entities")
results = cursor.fetchall()
conn.close()
```

---

## WikiRouter

Wiki 路由模块，判断查询是事实类还是语义类。

### route

路由判断。

**签名**：
```python
def route(self, query: str) -> str
```

**参数**：
- `query`: 查询文本（必需）

**返回**：
- `str`: 路由结果，可选值："wiki"、"rag" 或 "unknown"

**示例**：
```python
router = WikiRouter(known_entities={"方源", "力道", "春秋蝉"})

# 事实查询
route = router.route("方源主修什么？")
# 返回: "wiki"

# 语义查询
route = router.route("为什么方源要杀白凝冰？")
# 返回: "rag"
```

### is_fact_query

判断是否为事实查询。

**签名**：
```python
def is_fact_query(self, query: str) -> bool
```

**参数**：
- `query`: 查询文本（必需）

**返回**：
- `bool`: 是否为事实查询

**示例**：
```python
router = WikiRouter(known_entities={"方源", "力道"})

if router.is_fact_query("方源主修什么？"):
    print("这是事实查询")
```

---

## WikiUpdater

Wiki 增量更新模块。

### scan_new_entities

扫描新文本中的潜在实体。

**签名**：
```python
def scan_new_entities(
    self,
    text: str,
    source_chapter: str = None,
    min_confidence: int = 3
) -> List[Dict[str, Any]]
```

**参数**：
- `text`: 文本内容（必需）
- `source_chapter`: 来源章节（可选）
- `min_confidence`: 最小置信度（默认 3）

**返回**：
- `list`: 候选实体列表，每个实体包含：
  - `name`: 实体名称
  - `type`: 实体类型
  - `confidence`: 置信度
  - `source_chapter`: 来源章节

**示例**：
```python
updater = WikiUpdater()

test_text = """
方源主修力道，持有春秋蝉。元始仙尊是气道流派的代表人物。
"""

candidates = updater.scan_new_entities(
    text=test_text,
    source_chapter="第1章",
    min_confidence=1
)

for candidate in candidates:
    print(f"{candidate['name']} ({candidate['type']}) - 置信度: {candidate['confidence']}")
```

### scan_new_relations

扫描新文本中的潜在关系。

**签名**：
```python
def scan_new_relations(
    self,
    text: str,
    source_chapter: str = None
) -> List[Dict[str, Any]]
```

**参数**：
- `text`: 文本内容（必需）
- `source_chapter`: 来源章节（可选）

**返回**：
- `list`: 候选关系列表，每个关系包含：
  - `source`: 源实体名称
  - `target`: 目标实体名称
  - `rel_type`: 关系类型
  - `confidence`: 置信度
  - `source_chapter`: 来源章节

**示例**：
```python
updater = WikiUpdater()

test_text = """
方源持有春秋蝉，主修力道。元始仙尊师从星宿仙尊。
"""

relations = updater.scan_new_relations(text=test_text, source_chapter="第1章")

for rel in relations:
    print(f"{rel['source']} -{rel['rel_type']}-> {rel['target']}")
```

### batch_add_from_text

批量添加实体和关系。

**签名**：
```python
def batch_add_from_text(
    self,
    text: str,
    source_chapter: str = None,
    min_confidence: int = 3
) -> Dict[str, int]
```

**参数**：
- `text`: 文本内容（必需）
- `source_chapter`: 来源章节（可选）
- `min_confidence`: 最小置信度（默认 3）

**返回**：
- `dict`: 添加统计，包含：
  - `entities_added`: 添加的实体数
  - `relations_added`: 添加的关系数

**示例**：
```python
updater = WikiUpdater()

test_text = """
方源主修力道，持有春秋蝉。元始仙尊师从星宿仙尊。
"""

stats = updater.batch_add_from_text(
    text=test_text,
    source_chapter="第1章",
    min_confidence=1
)

print(f"添加实体: {stats['entities_added']}")
print(f"添加关系: {stats['relations_added']}")
```

### review_candidates

审核候选实体/关系。

**签名**：
```python
def review_candidates(
    self,
    candidates: List[Dict[str, Any]],
    approved: List[str] = None,
    rejected: List[str] = None
) -> Dict[str, int]
```

**参数**：
- `candidates`: 候选列表（必需）
- `approved`: 批准的名称列表（可选）
- `rejected`: 拒绝的名称列表（可选）

**返回**：
- `dict`: 审核统计，包含：
  - `approved`: 批准数
  - `rejected`: 拒绝数
  - `skipped`: 跳过数

**示例**：
```python
updater = WikiUpdater()

candidates = [
    {"name": "测试实体1", "type": "人物", "confidence": 3},
    {"name": "测试蛊1", "type": "蛊虫", "confidence": 2},
]

approved = ["测试实体1"]
rejected = []

stats = updater.review_candidates(candidates, approved=approved, rejected=rejected)

print(f"批准: {stats['approved']}")
print(f"拒绝: {stats['rejected']}")
```

### export_candidates

导出候选实体/关系为 JSON。

**签名**：
```python
def export_candidates(
    self,
    candidates: List[Dict[str, Any]],
    output_path: str = None
) -> str
```

**参数**：
- `candidates`: 候选列表（必需）
- `output_path`: 输出路径（可选）

**返回**：
- `str`: 输出文件路径

**示例**：
```python
updater = WikiUpdater()

candidates = [
    {"name": "测试实体1", "type": "人物", "confidence": 3},
]

output_path = updater.export_candidates(candidates)
print(f"导出到: {output_path}")
```

### import_candidates

从 JSON 导入候选实体/关系。

**签名**：
```python
def import_candidates(self, input_path: str) -> List[Dict[str, Any]]
```

**参数**：
- `input_path`: 输入文件路径（必需）

**返回**：
- `list`: 候选列表

**示例**：
```python
updater = WikiUpdater()

candidates = updater.import_candidates("candidates.json")
print(f"导入 {len(candidates)} 个候选")
```

### get_stats

获取更新统计。

**签名**：
```python
def get_stats(self) -> Dict[str, Any]
```

**返回**：
- `dict`: 统计信息

**示例**：
```python
updater = WikiUpdater()

stats = updater.get_stats()
print(f"总实体数: {stats['total_entities']}")
print(f"总关系数: {stats['total_relationships']}")
```

---

## KnowledgeGraphVisualizer

知识图谱可视化模块。

### build_graph

构建知识图谱。

**签名**：
```python
def build_graph(
    self,
    entity_types: List[str] = None
) -> nx.DiGraph
```

**参数**：
- `entity_types`: 实体类型过滤器（可选）

**返回**：
- `nx.DiGraph`: NetworkX 有向图

**示例**：
```python
visualizer = KnowledgeGraphVisualizer()

graph = visualizer.build_graph()
print(f"节点数: {graph.number_of_nodes()}")
print(f"边数: {graph.number_of_edges()}")
```

### draw_graph

绘制知识图谱。

**签名**：
```python
def draw_graph(
    self,
    output_path: str = "knowledge_graph.png",
    entity_types: List[str] = None,
    show_labels: bool = True,
    node_size: int = 2000,
    font_size: int = 10,
    figsize: tuple = (16, 12)
) -> str
```

**参数**：
- `output_path`: 输出文件路径（默认 knowledge_graph.png）
- `entity_types`: 实体类型过滤器（可选）
- `show_labels`: 是否显示标签（默认 True）
- `node_size`: 节点大小（默认 2000）
- `font_size`: 字体大小（默认 10）
- `figsize`: 图像尺寸（默认 (16, 12)）

**返回**：
- `str`: 输出文件路径

**示例**：
```python
visualizer = KnowledgeGraphVisualizer()

output_path = visualizer.draw_graph(
    output_path="graph.png",
    entity_types=["人物", "蛊虫"],
    node_size=2500,
    font_size=12
)

print(f"图谱已保存到: {output_path}")
```

### save_graph_data

保存图数据为 JSON。

**签名**：
```python
def save_graph_data(self, output_path: str = "graph_data.json") -> str
```

**参数**：
- `output_path`: 输出文件路径（默认 graph_data.json）

**返回**：
- `str`: 输出文件路径

**示例**：
```python
visualizer = KnowledgeGraphVisualizer()

output_path = visualizer.save_graph_data("graph.json")
print(f"图数据已保存到: {output_path}")
```

### get_stats

获取图统计信息。

**签名**：
```python
def get_stats(self) -> Dict[str, Any]
```

**返回**：
- `dict`: 统计信息，包含：
  - `total_nodes`: 总节点数
  - `total_edges`: 总边数
  - `node_types`: 节点类型分布（字典）
  - `edge_types`: 边类型分布（字典）

**示例**：
```python
visualizer = KnowledgeGraphVisualizer()

stats = visualizer.get_stats()
print(f"总节点数: {stats['total_nodes']}")
print(f"总边数: {stats['total_edges']}")

print("\n节点类型分布:")
for entity_type, count in sorted(stats['node_types'].items()):
    print(f"  {entity_type}: {count}")
```

---

## 常用模式

### 添加实体和关系

```python
from rag_core.wiki_db import get_wiki_db

wiki_db = get_wiki_db()
wiki_db.init_db()

# 添加实体
wiki_db.add_entity(
    name="龙公",
    entity_type="人物",
    properties={"主修": "气道", "境界": "九转"}
)

# 添加关系
wiki_db.add_relationship(
    source_name="龙公",
    target_name="气道",
    rel_type="主修"
)

wiki_db.close()
```

### 事实查询

```python
# 查询主修关系
answer = wiki_db.get_fact_query_answer("龙公主修什么？")
print(answer)  # "龙公 主修 的对象: 气道"

# 查询持有关系
answer = wiki_db.get_fact_query_answer("谁持有春秋蝉？")
print(answer)  # "春秋蝉 -持有-> 方源"

wiki_db.close()
```

### 知识图谱可视化

```python
from rag_core.graph_visualizer import KnowledgeGraphVisualizer

visualizer = KnowledgeGraphVisualizer()

# 构建图
graph = visualizer.build_graph()

# 绘制图
output_path = visualizer.draw_graph(
    output_path="graph.png",
    entity_types=["人物", "蛊虫"]
)

# 获取统计信息
stats = visualizer.get_stats()
print(f"节点数: {stats['total_nodes']}")
print(f"边数: {stats['total_edges']}")

wiki_db.close()
```

---

**最后更新**：2026-07-09
