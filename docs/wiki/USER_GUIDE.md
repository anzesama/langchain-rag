# Wiki 层用户指南

## 概述

Wiki 层是一个结构化知识管理系统，用于存储和查询《蛊真人》小说中的实体和关系。它提供了事实查询、关系查询和知识图谱可视化功能。

## 核心功能

### 1. 实体管理
- 添加实体（人物、蛊虫、流派、势力等）
- 添加别名
- 存储实体属性
- 查询实体信息

### 2. 关系管理
- 添加实体间的关系（持有、主修、师承等）
- 查询实体的所有关系
- 关系类型分类

### 3. 事实查询
- 自然语言事实查询
- 解析查询意图
- 返回结构化答案

### 4. 知识图谱可视化
- 生成实体关系网络图
- 按实体类型筛选
- 保存为图片文件
- 导出图数据为 JSON

## 快速开始

### 1. 加载种子数据

```bash
# 使用默认 seed.json
python scripts/load_seed.py

# 使用自定义种子文件
python scripts/load_seed.py --seed-file=custom_seed.json
```

### 2. 查看统计信息

```bash
# 使用 Wiki CLI 工具
python scripts/wiki_cli.py stats

# 使用可视化工具查看统计
python rag_core/graph_visualizer.py --show-stats
```

### 3. 查看知识图谱

```bash
# 生成完整知识图谱
python rag_core/graph_visualizer.py

# 按实体类型筛选
python rag_core/graph_visualizer.py --entity-types 人物 蛊虫

# 保存到指定路径
python rag_core/graph_visualizer.py --output=graph.png
```

### 4. 使用 CLI 工具

```bash
# 列出所有实体
python scripts/wiki_cli.py list entities

# 列出所有关系
python scripts/wiki_cli.py list relations

# 添加实体
python scripts/wiki_cli.py add entity --name="方源" --type="人物" --properties="资质=甲等9成"

# 添加关系
python scripts/wiki_cli.py add relationship --source="方源" --target="力道" --rel_type="主修"

# 导出数据
python scripts/wiki_cli.py export --entities --output=data/wiki/export.json
```

## 架构说明

### WikiDB 模块 (`rag_core/wiki_db.py`)

Wiki 数据库模块，提供实体和关系的管理功能。

**核心类**：
```python
WikiDB:
  - add_entity()              # 添加实体
  - add_relationship()         # 添加关系
  - get_entity()              # 查询实体
  - get_relations()           # 查询关系
  - get_fact_query_answer()   # 事实查询
  - get_all_entities()        # 获取所有实体
  - get_stats()               # 获取统计信息
```

**数据结构**：
- `entities` 表：存储实体信息（ID、名称、类型、属性、别名）
- `relationships` 表：存储关系信息（源实体、目标实体、关系类型、属性）

### WikiRouter 模块 (`rag_core/wiki_router.py`)

Wiki 路由模块，判断查询是事实类还是语义类。

**核心类**：
```python
WikiRouter:
  - route()                   # 路由判断
  - is_fact_query()           # 判断是否为事实查询
  - known_entities            # 已知实体集合
```

### WikiUpdater 模块 (`rag_core/wiki_updater.py`)

Wiki 增量更新模块，用于扫描新文本中的实体和关系。

**核心类**：
```python
WikiUpdater:
  - scan_new_entities()       # 扫描实体
  - scan_new_relations()      # 扫描关系
  - batch_add_from_text()     # 批量添加
  - review_candidates()       # 审核候选
```

### GraphVisualizer 模块 (`rag_core/graph_visualizer.py`)

知识图谱可视化模块。

**核心类**：
```python
KnowledgeGraphVisualizer:
  - build_graph()             # 构建图
  - draw_graph()              # 绘制图
  - save_graph_data()         # 保存图数据
  - get_stats()               # 获取统计
```

## 数据模型

### 实体类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 人物 | 小说中的角色 | 方源、元始仙尊 |
| 蛊虫 | 蛊虫实体 | 春秋蝉、全力以赴蛊 |
| 流派 | 功法流派 | 力道、气道、奴道 |
| 势力 | 组织或宗门 | 狐仙福地、张家寨 |
| 福地 | 福地实体 | 狐仙福地、荡魂山 |
| 地点 | 地理位置 | 北原、天庭 |
| 境界 | 境界名称 | 六转、八转 |
| 未分类 | 未分类实体 | - |

### 关系类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 持有 | 持有某物 | 方源 -持有-> 春秋蝉 |
| 主修 | 主修某流派 | 方源 -主修-> 力道 |
| 师承 | 师徒关系 | 元始仙尊 -师承-> 星宿仙尊 |
| 属于 | 属于某组织 | 方源 -属于-> 狐仙福地 |
| 盟友 | 盟友关系 | - |
| 敌对 | 敌对关系 | - |
| 背叛 | 背叛关系 | - |
| 同伴 | 同伴关系 | 方源 -同伴-> 白凝冰 |
| 利用 | 利用关系 | 方源 -利用-> 商心慈 |

## 使用示例

### 示例 1：添加实体

```python
from rag_core.wiki_db import get_wiki_db

wiki_db = get_wiki_db()
wiki_db.init_db()

# 添加实体
wiki_db.add_entity(
    name="龙公",
    entity_type="人物",
    properties={"主修": "气道", "境界": "九转"},
    aliases=["龙公尊者"]
)

# 添加别名
wiki_db.update_aliases("龙公", ["龙公尊者", "龙公"], add=True)

wiki_db.close()
```

### 示例 2：添加关系

```python
# 添加关系
wiki_db.add_relationship(
    source_name="龙公",
    target_name="气道",
    rel_type="主修",
    properties={"置信度": "高"}
)

wiki_db.close()
```

### 示例 3：事实查询

```python
# 事实查询
answer = wiki_db.get_fact_query_answer("龙公主修什么？")
# 返回: 龙公 主修 的对象: 气道

answer = wiki_db.get_fact_query_answer("谁持有春秋蝉？")
# 返回: 春秋蝉 -持有-> 方源

wiki_db.close()
```

### 示例 4：知识图谱可视化

```python
from rag_core.graph_visualizer import KnowledgeGraphVisualizer

visualizer = KnowledgeGraphVisualizer()

# 构建图
graph = visualizer.build_graph()

# 绘制图
output_path = visualizer.draw_graph(
    output_path="dragon_gong_graph.png",
    entity_types=["人物", "蛊虫"],
    node_size=2500,
    font_size=12
)

# 获取统计信息
stats = visualizer.get_stats()
print(f"节点数: {stats['total_nodes']}")
print(f"边数: {stats['total_edges']}")

# 保存图数据
visualizer.save_graph_data("dragon_gong_graph.json")
```

### 示例 5：增量更新

```python
from rag_core.wiki_updater import WikiUpdater

updater = WikiUpdater()

# 扫描新文本中的实体
test_text = """
龙公主修气道，持有真阳蛊。他是气道流派的代表人物。
"""

candidates = updater.scan_new_entities(
    text=test_text,
    source_chapter="第100章",
    min_confidence=1
)

# 批量添加
stats = updater.batch_add_from_text(
    text=test_text,
    source_chapter="第100章",
    min_confidence=1
)

print(f"添加实体: {stats['entities_added']}")
print(f"添加关系: {stats['relations_added']}")
```

## API 参考

### WikiDB

#### add_entity(name, entity_type, properties=None, aliases=None, source_chapter=None, entity_id=None)
添加实体到 Wiki 数据库。

**参数**：
- `name`: 实体名称
- `entity_type`: 实体类型（人物/蛊虫/流派/势力/事件/地点/境界）
- `properties`: 属性字典
- `aliases`: 别名列表
- `source_chapter`: 首次出现章节
- `entity_id`: 实体 ID（可选，默认自动生成）

**返回**：
- `bool`: 是否成功

#### add_relationship(source_name, target_name, rel_type, properties=None, source_chapter=None)
添加实体关系到 Wiki 数据库。

**参数**：
- `source_name`: 源实体名称
- `target_name`: 目标实体名称
- `rel_type`: 关系类型（持有/属于/主修/背叛/盟友/师承等）
- `properties`: 关系属性
- `source_chapter`: 来源章节

**返回**：
- `bool`: 是否成功

#### get_entity(name)
获取实体信息。

**参数**：
- `name`: 实体名称

**返回**：
- `dict`: 实体信息

#### get_relations(entity_name_or_id)
获取实体的所有关系。

**参数**：
- `entity_name_or_id`: 实体名称或 ID

**返回**：
- `list`: 关系列表

#### get_fact_query_answer(query)
执行事实查询。

**参数**：
- `query`: 查询文本

**返回**：
- `str`: 查询答案

#### get_stats()
获取 Wiki 数据库统计信息。

**返回**：
- `dict`: 统计信息

## 故障排除

### 问题 1：数据库未初始化

**错误**：`Wiki database not initialized`

**解决**：调用 `wiki_db.init_db()` 初始化数据库。

### 问题 2：实体已存在

**错误**：`Entity already exists: {name}`

**解决**：使用不同的实体名称，或先删除再添加。

### 问题 3：关系查询失败

**错误**：`Query relationship failed: {entity_id}`

**解决**：检查实体是否存在，或使用实体名称而不是 ID 查询关系。

### 问题 4：中文字符显示乱码

**错误**：日志中出现乱码

**解决**：确保终端支持 UTF-8 编码，或使用 PowerShell 运行脚本。

## 相关文档

- [Wiki 层实现总结](./WIKI_IMPLEMENTATION.md)
- [Week 1 总结](./QUICK_SUMMARY.md)
- [Week 2 总结](./WEEK2_SUMMARY.md)
- [Week 3 总结](./WEEK3_COMPLETE_SUMMARY.md)
- [完整总结](./COMPLETE_SUMMARY.md)

## 更新日志

- **2026-07-08**: 初始版本，支持基本实体和关系管理
- **2026-07-08**: 添加事实查询功能
- **2026-07-08**: 添加 Wiki 路由功能
- **2026-07-08**: 实现 Wiki 增量更新模块
- **2026-07-08**: 添加知识图谱可视化功能
- **2026-07-08**: 完成 Week 1-3 开发

## 贡献指南

欢迎贡献 Wiki 层的功能！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证。

---

**最后更新**：2026-07-09
**维护者**：[你的名字]
