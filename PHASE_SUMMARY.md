# 阶段复盘：批量关系抽取功能实现

- 时间：2026-08-02 09:40
- 状态：✅ 完成

## ✅ 做得好的点
- 批量关系抽取脚本 `scripts/batch_extract_relations.py` 完成
- 支持 `--source` 和 `--all` 两种模式
- 自动从数据库读取实体和chunks
- 使用 AGNES API 进行 LLM 关系提取
- 支持 JSON 解析容错（空响应、无效JSON）
- 修复 Web 知识图谱渲染 bug（`graphEdges` 填充顺序）

## 📊 执行结果

### 批量抽取统计
- 总来源：16
- 成功：8
- 失败：8
- 新增关系：43 条
- 新增实体：22 个

### 最终数据库状态
- 实体总数：136
- 关系总数：77
- 有关系的实体：82
- 孤立实体：54 (39.7%)

### 关系类型分布
- 适用：20
- 使用：14
- 依赖：9
- 优化：8
- 组成：6
- 关联：5
- 传递：5
- 实现：2
- 转换：2
- 验证：2
- 继承：1
- 等价：1
- 包含：1
- 父类：1

## 🐛 遇到的问题

### 1. chunks 参数类型不匹配
- 问题：`extract_relations` 期望列表，但传入的是字符串
- 解决：修改批量抽取脚本传入字典列表格式

### 2. _parse_json 处理空响应失败
- 问题：LLM 返回空响应时抛出 JSONDecodeError
- 解决：添加空响应检查和 JSON 提取容错

### 3. 数据库查询编码问题
- 问题：`row['text_content']` 在 Windows GBK 编码下报错
- 解决：改用 `row[0]` 索引访问

### 4. Web 知识图谱渲染 bug
- 问题：`loadGraph` 中 `graphEdges` 填充顺序错误，导致 degree 数组全是 0
- 影响：所有节点大小/位置都一样，无法体现连接数差异
- 解决：调整代码顺序，先填充 `graphEdges` 再计算 degree

## 📦 产出物

1. `scripts/batch_extract_relations.py` - 批量关系抽取脚本
2. 修复了 `rag_core/llm_refiner.py` 的 `_parse_json` 方法
3. 修复了 `scripts/wiki_manager_web.py` 的 `loadGraph` 函数
4. 成功提取并导入 43 条关系，新增 22 个实体

## ➡️ 下一步

### 短期（已完成）
- [x] 跑一次 `--all` 补全历史文档的关系

### 中期
- [ ] 修复失败文档的关系抽取（可能是 LLM 对某些文档无响应）
- [ ] 在 Web UI 中显示关系抽取进度
- [ ] 更新 SLO 进度文档

### 长期
- [ ] 在 `import.py` 的 Step 4 中集成关系抽取逻辑
- [ ] 新文档导入时自动补全关系
- [ ] 优化 LLM prompt 提高抽取准确率
