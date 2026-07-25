#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 知识库命令行工具（统一入口）

用法：
    # === 文档管理 ===
    python rag_cli.py add <文件路径>              # 添加单个文档
    python rag_cli.py add-dir                     # 批量添加 documents 目录下所有文档
    python rag_cli.py add-novel <小说文件路径>     # 添加小说（支持断点续传）
    
    # === 知识库操作 ===
    python rag_cli.py search "你的问题"            # 搜索并回答问题
    python rag_cli.py search "今日热点" --web      # 搜索并回答问题（本地无结果时搜网络）
    python rag_cli.py search "今日热点" -r         # 实时模式：只搜网络，排除本地 KB
    python rag_cli.py search-raw <关键词>          # 原始检索（不生成回答）
    python rag_cli.py list                         # 列出已入库文档
    python rag_cli.py stats                        # 查看统计信息
    python rag_cli.py status                       # 完整状态检查（含源文件、存储使用）
    python rag_cli.py view                         # 快速查看知识库内容
    python rag_cli.py rebuild [--novel-only]       # 重建知识库
    python rag_cli.py clean                        # 清空知识库
    
    # === 自动导入 ===
    python rag_cli.py auto-import                  # 扫描并自动导入新文件
    
    # === 小说管理 ===
    python rag_cli.py novel list                   # 列出已加载的小说章节
    python rag_cli.py novel add <章节文件>          # 添加单个小说章节
    python rag_cli.py novel add-all                # 批量加载所有章节
    python rag_cli.py novel status                 # 查看加载进度
    
    # === 服务管理 ===
    python rag_cli.py service start                # 启动 RAG 服务
    python rag_cli.py service stop                 # 停止 RAG 服务
    python rag_cli.py service status               # 检查服务状态
    
    # === 其他 ===
    python rag_cli.py github "AI视频生成"           # 搜索 GitHub 仓库
    python rag_cli.py preload                      # 预下载 Embedding 模型
"""
import sys
import argparse
import os
import socket
import subprocess
from pathlib import Path
from datetime import datetime

# Fix GBK encoding issue on Windows console
if sys.platform == "win32":
    import io
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag_config import logger, DOCUMENTS_DIR, NOVEL_CHAPTERS_DIR, STORAGE_DIR
from rag_core.knowledge_base import KnowledgeBase
from rag_core.auto_importer import AutoImportManager
from tools.multi_source_kb import MultiSourceKB


# ==================== 文档管理 ====================

def cmd_add(args):
    """添加单个文档"""
    kb = KnowledgeBase()
    success = kb.add_document(args.file)
    if success:
        print(f"[OK] 文档已添加: {args.file}")
    else:
        print(f"[FAIL] 添加失败: {args.file}")
        sys.exit(1)


def cmd_add_dir(args):
    """添加整个目录"""
    kb = KnowledgeBase()
    count = kb.add_directory()
    print(f"[OK] 目录批量添加完成，共 {count} 个文件")


def cmd_add_novel(args):
    """添加小说（支持断点续传）"""
    novel_file = Path(args.file)
    if not novel_file.exists():
        print(f"[FAIL] 文件不存在: {novel_file}")
        sys.exit(1)
    
    print(f"[INFO] 添加小说: {novel_file.name}")
    print(f"[OK] 文件大小: {novel_file.stat().st_size / 1024 / 1024:.2f} MB")
    
    kb = KnowledgeBase()
    print("[INFO] 开始添加文档...")
    success = kb.add_document(str(novel_file))
    
    if success:
        final_count = kb.vector_store.get_stats()['total_documents']
        print(f"[OK] 添加完成！最终记录数: {final_count}")
    else:
        print("[FAIL] 添加失败！")
        sys.exit(1)


# ==================== 自动入库辅助 ====================

def _import_search_to_chromadb(results, query, kb):
    """将搜索结果自动导入到 ChromaDB"""
    import tempfile
    from pathlib import Path
    
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp(prefix="rag_search_"))
    
    imported_count = 0
    
    for source_type, source_results in results.items():
        if not source_results:
            continue
        
        for i, item in enumerate(source_results):
            try:
                # 构建文档内容
                title = item.get('title', 'No title')
                content = item.get('content', '')
                url = item.get('url', '')
                score = item.get('score', 0)
                
                doc_content = f"标题：{title}\n\n{content}\n\n来源：{source_type}\n链接：{url}\n相似度：{score:.4f}"
                
                # 保存为临时文件
                filename = f"{source_type}_{i}.txt"
                filepath = temp_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(doc_content)
                
                # 使用 add_document 导入
                if kb.add_document(str(filepath)):
                    imported_count += 1
                    print(f"  [OK] {title[:50]}... ({source_type})")
                    
            except Exception as e:
                print(f"  [WARN] 导入失败: {item.get('title', 'unknown')} - {e}")
    
    print(f"[INFO] 共导入 {imported_count} 个搜索结果到 ChromaDB")
    return imported_count


# ==================== 搜索 ====================

def cmd_search(args):
    """搜索并回答问题（支持实时数据源 + 自动入库）"""
    kb = KnowledgeBase()
    
    # 实时模式：只搜 Tavily + GitHub（TrendRadar 暂时跳过）
    if args.realtime:
        multi_kb = MultiSourceKB()
        results = multi_kb.search_by_sources(
            args.query,
            ['tavily', 'github'],
            args.top_k
        )
        
        # 自动入库到 ChromaDB
        if any(results.values()):
            print("\n[IMPORT] 开始自动入库搜索结果...")
            _import_search_to_chromadb(results, args.query, kb)
            print("[OK] 入库完成")
        
        # 生成回答（如果需要）
        if args.generate:
            context = "\n\n".join([
                f"【{r['source_type'].upper()}】{r['title']}\n{r['content']}"
                for r in results['tavily'] + results['trend'] + results['github']
            ])
            
            llm = get_llm()
            if llm:
                answer = llm.predict(f"根据以下信息回答问题：\n\n{context}\n\n问题：{args.query}")
                print(f"\n[ANSWER]\n{answer}")
            else:
                print("[WARN] 未配置 LLM，无法生成回答")
                print(f"\n[CONTEXT]\n{context}")
        else:
            # 打印原始结果
            output = multi_kb.format_results(results)
            print(output)
        return
    
    # 普通搜索模式：先搜本地 KB，如果没结果再搜实时数据
    result = kb.search(args.query, top_k=args.top_k, use_web=args.web)
    
    # 如果使用了实时数据，自动入库
    if result.get('has_web') and result.get('web_results'):
        print("\n[IMPORT] 开始自动入库搜索结果...")
        web_results = {'tavily': result.get('web_results', [])}
        _import_search_to_chromadb(web_results, args.query, kb)
        print("[OK] 入库完成")
    
    print(f"\n[QUERY] {result['query']}")
    
    # 如果使用了实时数据，显示提示
    if result.get('has_web'):
        print("\n[INFO] 本次结果包含实时网络搜索数据")
    
    print(f"\n[ANSWER]")
    print(result['answer'])
    
    if result.get('sources'):
        print(f"\n[SOURCES]")
        for i, src in enumerate(result['sources'], 1):
            print(f"  [{i}] {src['source']} (score: {src['score']:.4f})")
            print(f"      {src['content'][:100]}...")


def cmd_search_raw(args):
    """原始检索（不生成回答）"""
    kb = KnowledgeBase()
    results = kb.search_raw(args.query, top_k=args.top_k, score_threshold=args.threshold)
    
    print(f"[QUERY] {args.query}")
    print(f"[RESULTS] {len(results)} found")
    print("-" * 60)
    
    for i, r in enumerate(results, 1):
        content = r.get('content', '')[:150]
        source = r.get('source', 'unknown')
        score = r.get('score', 0)
        print(f"  [{i}] [{score:.3f}] {source}")
        print(f"      {content}...")


# ==================== 列表与统计 ====================

def cmd_list(args):
    """列出已入库文档"""
    kb = KnowledgeBase()
    docs = kb.list_documents()
    
    if not docs:
        print("[EMPTY] 知识库为空，请先添加文档")
        return
    
    print(f"[TOTAL] 知识库中共 {len(docs)} 个文档块:")
    print("-" * 60)
    for doc in docs:
        print(f"  ID: {doc['id']}")
        print(f"  来源: {doc['source']}")
        print(f"  元数据: {doc['metadata']}")
        print("-" * 60)


def get_llm():
    """获取 LLM 实例（优先使用 Agnes API）"""
    try:
        from langchain_openai import ChatOpenAI
        
        # 优先使用 Agnes API
        agnes_api_key = os.getenv("RAG_AGNES_API_KEY")
        agnes_base_url = os.getenv("RAG_AGNES_API_BASE", "https://apihub.agnes-ai.com/v1")
        
        if agnes_api_key:
            return ChatOpenAI(
                model_name="agnes-2.0-flash",
                base_url=agnes_base_url,
                api_key=agnes_api_key,
                temperature=0.1
            )
        else:
            return None
    except Exception:
        return None


def cmd_stats(args):
    """查看统计信息"""
    kb = KnowledgeBase()
    stats = kb.get_stats()
    
    print(f"[STATS]")
    print(f"  总文档块数: {stats['total_documents']}")
    print(f"  存储路径: {stats['persist_dir']}")
    print(f"  文档目录: {DOCUMENTS_DIR}")


def cmd_status(args):
    """完整状态检查（含源文件、存储使用）"""
    print("=" * 60)
    print("知识库状态检查")
    print("=" * 60)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    kb = KnowledgeBase(auto_import=False, auto_build_parent=False)
    
    # 知识库统计
    stats = kb.get_stats()
    print(f"\n[知识库状态]")
    print(f"  状态: 正常")
    print(f"  文档总数: {stats.get('total_documents', 0)}")
    print(f"  存储路径: {stats.get('persist_dir', 'N/A')}")
    
    # 小说状态
    novel_status = kb.get_novel_status()
    if novel_status:
        print(f"\n[小说加载状态]")
        print(f"  全局计数器: {novel_status.get('global_counter', 0)}")
        print(f"  LSH 总向量: {novel_status.get('lsh_total_vectors', 0)}")
    
    # 源文件状态
    print(f"\n[源文件状态]")
    if DOCUMENTS_DIR.exists():
        doc_files = [f for f in DOCUMENTS_DIR.rglob('*') if f.is_file()]
        print(f"  源文档目录: {len(doc_files)} 个文件")
    else:
        print("  源文档目录不存在")
    
    if NOVEL_CHAPTERS_DIR and NOVEL_CHAPTERS_DIR.exists():
        chapter_files = list(NOVEL_CHAPTERS_DIR.glob('*.txt'))
        print(f"  小说章节目录: {len(chapter_files)} 个文件")
    elif NOVEL_CHAPTERS_DIR:
        print("  小说章节目录不存在")
    
    # 存储使用情况
    print(f"\n[存储使用]")
    if STORAGE_DIR.exists():
        total_size = sum(f.stat().st_size for f in STORAGE_DIR.rglob('*') if f.is_file())
        print(f"  总用量: {total_size / (1024*1024):.2f} MB")
        
        for item in STORAGE_DIR.iterdir():
            if item.is_dir():
                item_size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                print(f"    {item.name}: {item_size / (1024*1024):.2f} MB")
    else:
        print("  存储目录不存在")


def cmd_view(args):
    """快速查看知识库内容"""
    kb = KnowledgeBase(auto_import=False, auto_build_parent=False)
    
    # 统计信息
    stats = kb.get_stats()
    print("=" * 60)
    print("知识库统计")
    print("=" * 60)
    print(f"总文档块: {stats.get('total_documents', 0)}")
    print(f"存储路径: {stats.get('persist_dir', 'N/A')}")
    
    # 小说状态
    novel = kb.get_novel_status()
    print(f"\n小说状态")
    print(f"全局计数器: {novel.get('global_counter', 0)}")
    print(f"LSH 总向量: {novel.get('lsh_total_vectors', 0)}")
    
    # 文档列表
    docs = kb.list_documents()
    print(f"\n来源文件 ({len(docs)} chunks)")
    print("-" * 60)
    
    sources = {}
    for doc in docs:
        source = doc.get('source', 'unknown')
        basename = os.path.basename(source) if source != 'unknown' else source
        sources[basename] = sources.get(basename, 0) + 1
    
    sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
    
    for i, (name, count) in enumerate(sorted_sources[:30]):
        print(f"{i+1:2d}. {name} ({count} chunks)")
    
    if len(sorted_sources) > 30:
        print(f"... plus {len(sorted_sources)-30} more files")
    
    # 搜索测试
    print(f"\n搜索测试")
    print("-" * 60)
    
    queries = ["方源", "修仙", "资源"]
    for query in queries:
        results = kb.search_raw(query, top_k=3, score_threshold=0.1)
        print(f"\nQuery '{query}': {len(results)} results")
        for i, r in enumerate(results[:2]):
            content = r.get('content', '')[:100]
            source = r.get('source', 'unknown')
            score = r.get('score', 0)
            print(f"  {i+1}. [{score:.3f}] {source}")
            print(f"     {content}...")


# ==================== 重建与清理 ====================

def cmd_rebuild(args):
    """重建知识库"""
    kb = KnowledgeBase()
    novel_only = getattr(args, 'novel_only', False)
    count = kb.rebuild(novel_only=novel_only)
    if novel_only:
        print("OK 小说知识库重建完成")
    else:
        print(f"OK 知识库重建完成，加载了 {count} 个文档块")


def cmd_clean(args):
    """清空知识库"""
    kb = KnowledgeBase()
    kb.vector_store.vectorstore._collection.delete(where={})
    print("OK 知识库已清空")


# ==================== 自动导入 ====================

def cmd_auto_import(args):
    """手动触发自动导入"""
    mgr = AutoImportManager()
    result = mgr.scan_and_import()
    print("自动导入结果:")
    print(f"  扫描: {result['scanned']} 个文件")
    print(f"  新增: {result['added']} 个")
    print(f"  更新: {result['updated']} 个")
    print(f"  删除: {result['deleted']} 个")
    print(f"  跳过: {result['skipped']} 个")
    print(f"  错误: {result['errors']} 个")


# ==================== 小说管理 ====================

def cmd_novel_list(args):
    """列出已加载的小说章节"""
    kb = KnowledgeBase()
    docs = kb.list_documents()
    novel_docs = [d for d in docs if 'novel_chapters' in d.get('source', '')]
    print(f"小说文档: {len(novel_docs)} 个文件")
    for d in novel_docs[:20]:
        print(f"  - {d['source']}")


def cmd_novel_add(args):
    """添加单个小说章节"""
    kb = KnowledgeBase()
    success = kb.add_document(args.file)
    if success:
        print(f"OK 添加成功: {args.file}")
    else:
        print(f"FAIL 添加失败: {args.file}")


def cmd_novel_add_all(args):
    """批量加载所有章节"""
    kb = KnowledgeBase()
    chapter_dir = NOVEL_CHAPTERS_DIR
    
    if not chapter_dir.exists():
        print(f"FAIL 章节目录不存在: {chapter_dir}")
        return
    
    chapters = sorted(chapter_dir.glob("*.txt"))
    print(f"找到 {len(chapters)} 个章节文件")
    
    for i, chapter in enumerate(chapters, 1):
        print(f"[{i}/{len(chapters)}] 加载: {chapter.name}")
        kb.add_document(str(chapter))
        print(f"  OK 加载完成")
    
    print(f"OK 批量加载完成: {len(chapters)} 个章节")


def cmd_novel_status(args):
    """查看加载进度"""
    kb = KnowledgeBase()
    status = kb.get_novel_status()
    print(f"小说加载状态:")
    print(f"  Global Counter: {status['global_counter']}")
    print(f"  LSH 总向量: {status['lsh_total_vectors']}")


def cmd_github(args):
    """搜索 GitHub 仓库"""
    from tools.github_collector import GitHubCollector
    from tools.multi_source_kb import MultiSourceKB
    
    collector = GitHubCollector()
    kb = KnowledgeBase()
    
    # 导入到 ChromaDB
    results = collector.search_and_import_to_chroma(
        query=args.query,
        max_results=args.top_k,
        kb=kb
    )
    
    # 格式化输出
    multi_kb = MultiSourceKB()
    results_dict = {'github': results}
    output = multi_kb.format_results(results_dict)
    
    print(output)
    
    print(f"\n[INFO] 共导入 {len(results)} 个仓库到 ChromaDB")
    print(f"[INFO] 可以使用 'rag_cli.py search' 命令搜索这些仓库内容")


# ==================== 服务管理 ====================

def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def cmd_service_start(args):
    """启动 RAG 服务"""
    server_script = PROJECT_ROOT / "scripts" / "rag_server_v2.py"
    
    if not server_script.exists():
        print(f"FAIL 找不到服务器脚本: {server_script}")
        sys.exit(1)
    
    if is_port_in_use(8765):
        print("[WARN] 端口 8765 已被占用，服务可能已在运行")
        return
    
    env = os.environ.copy()
    env['OMP_NUM_THREADS'] = '1'
    env['TOKENIZERS_PARALLELISM'] = 'false'
    
    print("[INFO] 正在启动 RAG 服务...")
    try:
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"OK 服务已启动 (PID: {process.pid})")
    except Exception as e:
        print(f"FAIL 启动失败: {e}")
        sys.exit(1)


def cmd_service_stop(args):
    """停止 RAG 服务"""
    if not is_port_in_use(8765):
        print("[INFO] 端口 8765 未被占用，服务未运行")
        return
    
    # Windows 下终止占用端口的进程
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True
        )
        for line in result.stdout.split('\n'):
            if ':8765' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                print(f"OK 已停止 PID: {pid}")
                return
    except Exception as e:
        print(f"FAIL 停止失败: {e}")


def cmd_service_status(args):
    """检查服务状态"""
    if is_port_in_use(8765):
        print("[OK] RAG 服务正在运行 (端口 8765)")
        try:
            import urllib.request
            resp = urllib.request.urlopen('http://localhost:8765/health', timeout=2)
            data = resp.read().decode()
            print(f"  健康检查: {data}")
        except Exception as e:
            print(f"  健康检查失败: {e}")
    else:
        print("[INFO] RAG 服务未运行")
        print("  启动命令: python rag_cli.py service start")


# ==================== 其他 ====================

def cmd_preload(args):
    """预下载 Embedding 模型"""
    import os
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    
    print("[INFO] 正在下载 Embedding 模型...")
    try:
        from sentence_transformers import SentenceTransformer
        from rag_config import LOCAL_EMBEDDING_MODEL
        
        model = SentenceTransformer(LOCAL_EMBEDDING_MODEL, device="cpu")
        dims = model._modules['0'].get_sentence_embedding_dimension()
        print(f"OK 模型下载完成: {LOCAL_EMBEDDING_MODEL}")
        print(f"   维度: {dims}")
    except Exception as e:
        print(f"FAIL 模型下载失败: {e}")
        print("   提示：请检查网络连接或使用国内镜像")
        sys.exit(1)


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(
        description="RAG 知识库命令行工具（统一入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python rag_cli.py add documents/test.txt
  python rag_cli.py search "方源的目标是什么"
  python rag_cli.py status
  python rag_cli.py service start
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # === 文档管理 ===
    p_add = subparsers.add_parser("add", help="添加单个文档")
    p_add.add_argument("file", help="文档路径")
    p_add.set_defaults(func=cmd_add)
    
    p_add_dir = subparsers.add_parser("add-dir", help="批量添加 documents 目录下所有文档")
    p_add_dir.set_defaults(func=cmd_add_dir)
    
    p_add_novel = subparsers.add_parser("add-novel", help="添加小说（支持断点续传）")
    p_add_novel.add_argument("file", help="小说文件路径")
    p_add_novel.set_defaults(func=cmd_add_novel)
    
    # === 搜索 ===
    p_search = subparsers.add_parser("search", help="搜索并回答问题")
    p_search.add_argument("query", help="搜索问题")
    p_search.add_argument("--top-k", type=int, default=5, help="返回结果数")
    p_search.add_argument("--web", action="store_true", help="启用实时网络搜索（本地无结果时自动搜）")
    p_search.add_argument("--realtime", "-r", action="store_true", help="实时模式：只搜 Tavily/TrendRadar，排除本地 KB")
    p_search.add_argument("--generate", action="store_true", help="实时模式下生成 LLM 回答")
    p_search.set_defaults(func=cmd_search)
    
    p_search_raw = subparsers.add_parser("search-raw", help="原始检索（不生成回答）")
    p_search_raw.add_argument("query", help="搜索关键词")
    p_search_raw.add_argument("--top-k", type=int, default=5, help="返回结果数")
    p_search_raw.add_argument("--threshold", type=float, default=0.3, help="相似度阈值")
    p_search_raw.set_defaults(func=cmd_search_raw)
    
    # === 列表与统计 ===
    p_list = subparsers.add_parser("list", help="列出已入库文档")
    p_list.set_defaults(func=cmd_list)
    
    p_stats = subparsers.add_parser("stats", help="查看统计信息")
    p_stats.set_defaults(func=cmd_stats)
    
    p_status = subparsers.add_parser("status", help="完整状态检查（含源文件、存储使用）")
    p_status.set_defaults(func=cmd_status)
    
    p_view = subparsers.add_parser("view", help="快速查看知识库内容")
    p_view.set_defaults(func=cmd_view)
    
    # === 重建与清理 ===
    p_rebuild = subparsers.add_parser("rebuild", help="重建知识库")
    p_rebuild.add_argument("--novel-only", dest="novel_only", action="store_true",
                           help="仅清空小说数据")
    p_rebuild.set_defaults(func=cmd_rebuild)
    
    p_clean = subparsers.add_parser("clean", help="清空知识库")
    p_clean.set_defaults(func=cmd_clean)
    
    # === 自动导入 ===
    p_auto_import = subparsers.add_parser("auto-import", help="扫描并自动导入 documents 目录的新文件")
    p_auto_import.set_defaults(func=cmd_auto_import)
    
    # === 小说管理 ===
    p_novel = subparsers.add_parser("novel", help="小说管理命令")
    p_novel_subparsers = p_novel.add_subparsers(dest="novel_command", help="小说子命令")
    
    p_novel_list = p_novel_subparsers.add_parser("list", help="列出已加载的小说章节")
    p_novel_list.set_defaults(func=cmd_novel_list)
    
    p_novel_add = p_novel_subparsers.add_parser("add", help="添加单个小说章节")
    p_novel_add.add_argument("file", help="章节文件路径")
    p_novel_add.set_defaults(func=cmd_novel_add)
    
    p_novel_add_all = p_novel_subparsers.add_parser("add-all", help="批量加载所有章节")
    p_novel_add_all.set_defaults(func=cmd_novel_add_all)
    
    p_novel_status = p_novel_subparsers.add_parser("status", help="查看加载进度")
    p_novel_status.set_defaults(func=cmd_novel_status)
    
    # === GitHub 搜索 ===
    p_github = subparsers.add_parser("github", help="搜索 GitHub 仓库")
    p_github.add_argument("query", help="搜索关键词")
    p_github.add_argument("--top-k", type=int, default=5, help="返回结果数")
    p_github.set_defaults(func=cmd_github)
    
    # === 服务管理 ===
    p_service = subparsers.add_parser("service", help="RAG 服务管理")
    p_service_subparsers = p_service.add_subparsers(dest="service_command", help="服务子命令")
    
    p_svc_start = p_service_subparsers.add_parser("start", help="启动 RAG 服务")
    p_svc_start.set_defaults(func=cmd_service_start)
    
    p_svc_stop = p_service_subparsers.add_parser("stop", help="停止 RAG 服务")
    p_svc_stop.set_defaults(func=cmd_service_stop)
    
    p_svc_status = p_service_subparsers.add_parser("status", help="检查服务状态")
    p_svc_status.set_defaults(func=cmd_service_status)
    
    # === 其他 ===
    p_preload = subparsers.add_parser("preload", help="预下载 Embedding 模型")
    p_preload.set_defaults(func=cmd_preload)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # 处理 novel 子命令
    if args.command == "novel" and not hasattr(args, "novel_command"):
        p_novel.print_help()
        sys.exit(0)
    
    # 处理 service 子命令
    if args.command == "service" and not hasattr(args, "service_command"):
        p_service.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == "__main__":
    main()
