# 项目经验总结

- 创建时间：2026-06-30 23:10
- 最后更新：2026-07-10
- 整理来源：各阶段复盘文档
- 目的：避免重复犯错，提升开发效率

---

## 📚 经验分类

### 0. 🆕 新增功能经验

#### 属性推导系统（2026-07-10）

**问题**：人物实体属性不完整，部分角色缺少关键属性

**解决**：
- 扩展 `wiki_reasoner.py`，新增 4 条属性推导规则
- 实现 `derive_entity_properties()` 方法
- 实现 `apply_derived_properties()` 方法
- 添加 CLI 命令支持

**规则设计**：
1. **持有蛊虫→获得功能**：X 持有 Y（蛊虫），Y 有"功能"属性 → X 获得该能力
2. **持有蛊虫→获得境界**：X 持有 Y（蛊虫），Y 有"境界"属性 → X 获得对应境界信息
3. **师承→继承流派**：X 师承 Y，Y 有"主修"属性 → X 可能继承该流派
4. **持有流派→获得特点**：X 持有/主修 Y（流派），Y 有"特点"属性 → X 获得该特点

**效果**：
- 方源属性从 9 个增加到 13 个
- 新增 4 个属性（能力、掌握境界、流派特点、流派优势）

**经验**：
- ✅ 零成本：纯规则实现，无需 LLM
- ✅ 低延迟：O(n) 时间复杂度
- ✅ 可解释：每个推导都有详细原因
- ✅ 灵活：支持单个实体或批量应用
- ✅ 去重：自动跳过已有属性

**局限性**：
- 属性推导依赖于目标实体已有属性
- 低置信度规则（如师承→继承流派，0.5）需要人工审核
- 需要定期执行以保持数据更新

**使用建议**：
- 定期运行：`python wiki_cli.py reason --apply-properties`
- 人工审核：`python wiki_cli.py reason --show-results`


#### 大文件分批加载（2026-07-01）

**问题**：加载大文件（如 18,000+ chunks 的小说）时超出长度限制，导致 OOM/超时

**解决**：
- `VectorStoreManager.add_documents()` — 自动分批插入 ChromaDB（500/批）
- `get_embeddings()` — 自动分批编码（256/批）
- `KnowledgeBase.add_directory()` — 逐文件处理，不再合并所有 chunks

**经验**：
- ✅ 处理大量数据时必须分批，不要一次性加载全部
- ✅ Embedding 模型和向量数据库都有批次大小限制
- ✅ 大文件（>10MB）特别需要注意分批策略
- ✅ 分批配置集中在 `rag_config.py`，方便统一调整

---

#### 断点续传功能优化（2026-07-08）

**问题**：
- 每次调用 `add_document()` 都会重新分块整个文件（~23秒）
- 进度文件和 ChromaDB 数据不一致
- Windows GBK 编码无法显示 emoji

**解决**：
```python
# 1. 修复 _sync_from_chromadb() 方法
# 旧代码：只同步 'guzhenren' 的 chunk
if 'guzhenren' in meta.get('source', ''):
    chunk_id = f"novel_{global_order}"

# 新代码：同步所有 chunk
chunk_id = meta.get('chunk_id')
if chunk_id and chunk_id not in self.loaded_ids:
    self.loaded_ids.add(chunk_id)

# 2. 添加 ChromaDB 检查优化
if self.progress_file.exists() and len(self.loaded_ids) > 0:
    chromadb_count = self.vs_manager.vectorstore._collection.count()
    if chromadb_count > 0:
        logger.info(f"ChromaDB 中已有 {chromadb_count} 个 chunk，全部已加载，无需继续")
        return 0

# 3. 移除 emoji 避免编码错误
✅ → [OK], 📝 → [Note], 💾 → [Save], 🚀 → [Using GPU]
```

**效果**：
- 第二次加载：从 ~23秒 → 0.6秒
- 进度文件和 ChromaDB 数据一致
- 避免编码错误

**经验**：
- ✅ 断点续传必须同步所有 chunk ID，不仅仅是特定文件
- ✅ 添加 ChromaDB 检查，避免重复分块
- ✅ 移除 emoji，使用 ASCII-safe 符号
- ✅ 进度文件保存 `loaded_chunks`, `total_chunks`, `loaded_ids`
- ✅ 从 ChromaDB 同步可以避免重复分块

---

#### RAG 服务自动启动（2026-07-08）

**问题**：搜索知识库前需要确保 RAG 服务正常运行，否则报错 `fetch failed`

**解决**：修改 `rag_extension/pi_rag_tool.ts` 实现自动启动
```typescript
// 功能：
// 1. 调用 API 前检查端口是否监听
// 2. 如未运行，自动启动 rag_server.py
// 3. 等待服务就绪（最多 10 秒）
// 4. 再执行实际请求
```

**经验**：
- ✅ 扩展工具中集成自动启动逻辑，用户无需手动操作
- ✅ 使用 `/health` 端点检查服务就绪状态
- ✅ 超时处理避免无限等待

---

#### GitHub 数据自动保存

**解决**：
```python
# 创建 github_collector.py
class GitHubCollector:
    def fetch_data(self, query, max_results=20):
        # 从 GitHub API 获取数据
        pass
    
    def save_to_db(self, data):
        # 保存到 SQLite
        pass
    
    def save_to_kb(self, data):
        # 保存到 ChromaDB
        pass
```

**经验**：
- GitHub API 需要处理速率限制
- 数据结构化存储比直接保存文档更高效
- 可以同时支持 SQLite（结构化查询）和 ChromaDB（语义搜索）

---

### 1. 🐛 常见问题与解决方案

#### Windows 环境问题

**问题**：Git Bash 执行 Python 报错 `No such file or directory`

**原因**：bash 将 `\\` 当作转义字符

**解决**：
```bash
# ❌ 错误
python D:\\class\\project-config\\rag_core\\rag_pipeline.py

# ✅ 正确
python D:/class/project-config/rag_core/rag_pipeline.py
```

**经验**：
- Windows 路径统一使用 `/` 而非 `\`
- JSON 中用 `\\` 或 `/` 均可
- Markdown 中统一用正斜杠 `/`

---

**问题**：Conda activate 报错

**原因**：conda init 未执行

**解决**：
```bash
conda init powershell
```

**经验**：
- 首次使用 conda 前必须执行 `conda init`
- Python 解释器位置在环境根目录，不在 `Scripts/` 下

---

#### Python 操作

**问题**：环境隔离

**原因**：不同项目需要不同 Python 版本和依赖

**解决**：
- `base` - 仅通用工具
- `ml_env` (Python 3.9) - 数据分析、ML、可视化
- `mycode` (Python 3.10) - 爬虫、通用脚本、自动化

**经验**：
- 严禁自行安装/卸载，除非明确指示
- 报错先截图，不要自己修

---

#### 编码问题

**问题**：GBK 编码错误，无法输出 `✓` 等符号

**原因**：Windows 控制台默认 GBK 编码

**解决**：
```python
# ❌ 错误
print(f"✓ Dataset saved: {path}")

# ✅ 正确
print(f"[OK] Dataset saved: {path}")
```

**经验**：
- Windows 控制台使用 ASCII-safe 符号
- 统一使用 `[OK]`, `[PASS]`, `[FAIL]` 等符号
- **避免使用 emoji、特殊符号**（导致 GBK 编码错误）
- 所有日志输出必须 ASCII-safe

---

**问题**：subprocess UnicodeDecodeError

**原因**：Windows 终端 GBK vs Python UTF-8

**解决**：
```python
# ✅ 正确
result = subprocess.run(
    cmd,
    encoding='utf-8',
    errors='replace'
)
```

**经验**：
- subprocess 添加 `encoding='utf-8', errors='replace'`
- 处理中文路径和输出

---

### 2. 🔧 开发规范

#### 文件操作

**问题**：文件复制/移动操作通过模型中转

**原因**：增加不必要的步骤

**解决**：
```bash
# ✅ 正确：直接用命令
cp source.txt dest.txt
mv file.py ../another_dir/
```

**经验**：
- 避免让模型做"搬运工"式的重复劳动
- 文件操作直接使用命令执行

---

#### 路径规范

**问题**：路径不一致导致错误

**解决**：
- bash 中使用 `/` 而非 `\`
- Windows 路径在 JSON 中用 `\\` 或 `/` 均可
- Markdown 中统一用正斜杠 `/`

**经验**：
- 统一路径规范，避免混用

---

#### 文档更新经验

**问题**：文档与实际文件结构不一致

**解决**：
```bash
# 每次更新后检查文件结构
find langchain-rag -type f -name "*.py" -o -name "*.md" | wc -l

# 检查目录结构
tree -L 2 langchain-rag/
```

**经验**：
- 定期更新文档以反映实际文件结构
- 使用 `find` 和 `tree` 命令快速检查
- 文档更新频率：每次重大更改后

---

---

### 3. 🎯 架构设计

#### 数据源完整性

**问题**：数据源不全，只用了 1-2 个

**原因**：没有全面利用所有可用数据源

**解决**：
- Tavily - 实时搜索
- Jina - 搜索引擎聚合
- TrendRadar - 趋势雷达
- Policy - 政策分析
- RSS - 订阅源

**经验**：
- 必须应用所有现有数据源进行分析和交叉验证
- 设计降级策略，容忍单个源失败

---

#### 工作流逻辑

**问题**：查询"今日热点"却直接搜空知识库

**原因**：逻辑错误

**解决**：
```python
# ✅ 正确
if kb_status == "empty" or kb_status == "stale":
    # 直接调用热点分析器
    analyzer.analyze("今日热点")
else:
    # 搜索知识库
    results = kb.search(query)
```

**经验**：
- "想要" → "得到" → "做到"
- 不在空知识库上搜索实时数据

---

### 4. 🐛 调试经验

#### 调试原则

**止损规则**：
- 单一报错排查超过 **5 分钟** → 立即停手
- 同一问题尝试 **3 次**仍未解决 → 立即停手
- 涉及修改底层依赖/系统配置 → 必须询问主管

**经验**：
- 不要在同一个问题上花费过多时间
- 及时寻求帮助

---

#### 调试方法

**问题**：Environment misconfiguration

**解决**：
- 首先确认环境变量
- 检查 Python 路径
- 验证依赖版本

**经验**：
- 环境问题优先检查配置，不要盲目尝试

---

### 5. 📁 项目管理

#### 文档管理

**问题**：文档分散，难以查找

**解决**：
- 创建 `docs/` 目录集中存放项目文档
- 创建 `archive/` 目录存放历史文档
- 根目录仅保留关键依赖

**经验**：
- 按类别组织文档
- 定期整理，避免文件散乱

---

#### 归档策略

**问题**：根目录文件过多，难以维护

**解决**：
- 知识库项目 → `langchain-rag/`
- 项目文档 → `docs/`
- 归档文档 → `archive/`
- 根目录 → 仅保留关键依赖

**经验**：
- 项目结构清晰化
- 便于理解和维护

---

## 🔍 经验总结

### ✅ 做得好的点

1. **系统化测试** - 每个功能都写测试用例
2. **文档完整** - 每个阶段都写复盘文档
3. **问题记录** - 每个问题都记录解决方案
4. **代码规范** - 统一路径、编码、命名规范
5. **断点续传优化** - 添加 ChromaDB 检查，避免重复分块

### ⚠️ 常见错误

1. **路径问题** - Windows 路径分隔符混用
2. **编码问题** - GBK vs UTF-8, emoji 符号
3. **环境问题** - Conda 环境未正确激活
4. **遗漏问题** - 检查不够系统
5. **断点续传问题** - 未同步所有 chunk ID

### 📖 改进方向

1. **系统检查** - 移动后用 `find` 扫描所有内容
2. **经验沉淀** - 定期整理项目经验到文档
3. **自动化** - 使用脚本辅助检查
4. **审查** - 提交前检查是否符合规范
5. **文档同步** - 每次代码更新后同步更新文档
6. **断点续传优化** - 添加 ChromaDB 检查，避免重复分块

---

## 📚 相关文档

- [故障排除指南](troubleshooting.md)
- [项目开发规范](AGENTS.md)
- [项目规则](PROJECT_RULES.md)
- [各阶段复盘文档](docs/)
- [断点续传功能](../fix/KNOWLEDGE_BASE_ISSUES.md) - 知识库问题修复记录

---

*经验总结旨在避免重复犯错，提升开发效率。*
