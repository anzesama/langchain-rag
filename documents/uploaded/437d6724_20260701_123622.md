# 项目技术文档

## 概述
本项目是一个基于 LangChain 的本地 RAG 知识库系统。

## 架构设计
- 文档加载：支持 PDF/TXT/CSV/Word/Excel/JSON 等多种格式
- 向量存储：使用 ChromaDB 进行本地持久化
- Embedding：使用 BAAI/bge-small-zh-v1.5 中文模型
- 检索策略：余弦相似度搜索，可配置 top-k 和阈值

## 使用方法
1. 将文档放入 documents 目录
2. 运行 `python rag_cli.py add-dir` 加载所有文档
3. 运行 `python rag_cli.py search "你的问题"` 进行搜索
