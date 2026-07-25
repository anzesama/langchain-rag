# 多源知识库快速配置指南

> 快速设置所有必需的 API Keys
> 更新时间：2026-07-10

---

## 📋 必需配置

### 1. Tavily API Key（实时搜索）

**用途**: 搜索实时网络信息（今日热点、最新新闻）

**获取地址**: https://tavily.com

**配置方法**:

#### Windows (PowerShell)
```powershell
$env:TAVILY_API_KEY = "your_tavily_api_key_here"
```

#### Windows (CMD)
```cmd
set TAVILY_API_KEY=your_tavily_api_key_here
```

#### Linux/Mac
```bash
export TAVILY_API_KEY=your_tavily_api_key_here
```

**验证**:
```bash
python tools/multi_source_kb.py --query "今日热点" --sources tavily --top-k 2
```

---

### 2. OpenAI API Key（生成回答）

**用途**: 生成 LLM 回答

**获取地址**: https://platform.openai.com/api-keys

**配置方法**:

#### Windows (PowerShell)
```powershell
$env:RAG_OPENAI_API_KEY = "your_openai_api_key_here"
```

#### Windows (CMD)
```cmd
set RAG_OPENAI_API_KEY=your_openai_api_key_here
```

#### Linux/Mac
```bash
export RAG_OPENAI_API_KEY=your_openai_api_key_here
```

**验证**:
```bash
python scripts/rag_cli.py search "蛊真人" --top-k 2
```

---

## 📋 可选配置

### 3. GitHub API Key（GitHub 搜索）

**用途**: 搜索 GitHub 仓库（技术问题、开源项目）

**获取地址**: https://github.com/settings/tokens

**步骤**:

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token" → "Generate new token (classic)"
3. 设置过期时间（建议 90 天）
4. 勾选权限：
   - ✅ `repo`（完整的仓库访问权限）
5. 点击 "Generate token"
6. 复制生成的 Token

**配置方法**:

#### Windows (PowerShell)
```powershell
$env:RAG_GITHUB_API_KEY = "your_github_token_here"
```

#### Windows (CMD)
```cmd
set RAG_GITHUB_API_KEY=your_github_token_here
```

#### Linux/Mac
```bash
export RAG_GITHUB_API_KEY=your_github_token_here
```

**验证**:
```bash
python scripts/rag_cli.py github "langchain" --top-k 2
```

---

## 🎯 完整配置脚本

### Windows (PowerShell)

```powershell
# 设置环境变量（请替换为你的 API Keys）
$env:TAVILY_API_KEY = "your_tavily_api_key_here"
$env:RAG_OPENAI_API_KEY = "your_openai_api_key_here"
$env:RAG_GITHUB_API_KEY = "your_github_token_here"

# 验证配置
echo "配置完成！"
python tools/multi_source_kb.py --query "测试" --sources all --top-k 2
```

### Linux/Mac (Bash)

```bash
# 设置环境变量（请替换为你的 API Keys）
export TAVILY_API_KEY="your_tavily_api_key_here"
export RAG_OPENAI_API_KEY="your_openai_api_key_here"
export RAG_GITHUB_API_KEY="your_github_token_here"

# 验证配置
echo "配置完成！"
python tools/multi_source_kb.py --query "测试" --sources all --top-k 2
```

---

## 📝 测试配置

### 测试 1: Tavily 实时搜索

```bash
python tools/multi_source_kb.py --query "今日热点" --sources tavily --top-k 2
```

**预期结果**: 找到 2 条实时网络搜索结果

### 测试 2: OpenAI 生成回答

```bash
python scripts/rag_cli.py search "蛊真人" --top-k 2
```

**预期结果**: 找到 2 条本地 KB 结果

### 测试 3: GitHub 搜索

```bash
python scripts/rag_cli.py github "langchain" --top-k 2
```

**预期结果**: 找到 2 个 langchain 仓库（需要配置 GitHub API Key）

### 测试 4: 实时搜索 + 生成回答

```bash
python scripts/rag_cli.py search "今日热点" --realtime --generate --top-k 2
```

**预期结果**: 找到 2 条实时搜索结果并生成回答（需要配置 OpenAI API Key）

---

## 🔧 常见问题

### Q1: Tavily 搜索失败，返回 401 错误

**A**: 检查 `TAVILY_API_KEY` 是否正确设置：
```bash
echo $env:TAVILY_API_KEY
```

### Q2: OpenAI 生成回答失败，返回 401 错误

**A**: 检查 `RAG_OPENAI_API_KEY` 是否正确设置：
```bash
echo $env:RAG_OPENAI_API_KEY
```

### Q3: GitHub 搜索失败，返回 401 错误

**A**: 检查 `RAG_GITHUB_API_KEY` 是否正确设置：
```bash
echo $env:RAG_GITHUB_API_KEY
```

### Q4: 环境变量在重启后失效

**A**: 需要将环境变量添加到系统环境变量或配置文件中。

**Windows**:
- 打开"系统属性" → "高级" → "环境变量"
- 添加或修改用户/系统环境变量

**Linux/Mac**:
- 添加到 `~/.bashrc` 或 `~/.zshrc`
- 执行 `source ~/.bashrc` 或 `source ~/.zshrc`

### Q5: 找不到模块

**A**: 确保在项目根目录执行命令：
```bash
cd D:/class/project-config/langchain-rag
python scripts/rag_cli.py search "蛊真人"
```

---

## 📊 配置检查清单

### 必需配置

- [ ] Tavily API Key 已设置
- [ ] OpenAI API Key 已设置

### 可选配置

- [ ] GitHub API Key 已设置（可选）

### 功能测试

- [ ] Tavily 实时搜索测试通过
- [ ] OpenAI 生成回答测试通过
- [ ] GitHub 搜索测试通过（可选）

---

## 🚀 快速开始

### 1. 设置必需 API Keys

```bash
# Windows (PowerShell)
$env:TAVILY_API_KEY = "your_tavily_api_key_here"
$env:RAG_OPENAI_API_KEY = "your_openai_api_key_here"
```

### 2. 测试搜索功能

```bash
# 测试本地 KB
python scripts/rag_cli.py search "蛊真人" --top-k 2

# 测试实时搜索
python scripts/rag_cli.py search "今日热点" --realtime --top-k 2
```

### 3. 开始使用

```bash
# 搜索本地 KB
python scripts/rag_cli.py search "你的问题"

# 搜索实时数据
python scripts/rag_cli.py search "今日热点" --realtime

# 搜索 GitHub
python scripts/rag_cli.py github "AI视频生成" --top-k 5
```

---

## 📚 相关文档

- `MULTI_SOURCE_COMPLETE_SUMMARY.md` - 多源集成完成总结
- `REALTIME_SEARCH_IMPLEMENTATION.md` - 实时搜索实施总结
- `GITHUB_INTEGRATION_IMPLEMENTATION.md` - GitHub 集成实施总结
- `MULTI_SOURCE_INTEGRATION_PLAN.md` - 多源集成改进计划

---

**状态**: ✅ 配置指南完成
**下一步**: 设置 API Keys 并测试功能
