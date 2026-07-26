"""
MultiSourceKB - 多源知识库统一检索系统

功能：
- 整合本地知识库（ChromaDB）
- 实时网络搜索（Tavily API）
- GitHub 仓库/Issue 搜索
- 政策情报（MCP 服务器）
- TrendRadar 热点采集

用法：
    python tools/multi_source_kb.py --query "AI视频生成" --sources all
    python tools/multi_source_kb.py --query "今日热点" --sources tavily
    python tools/multi_source_kb.py --query "人工智能" --sources github
    python tools/multi_source_kb.py --query "就业" --sources policy
    python tools/multi_source_kb.py --query "" --sources trend --fetch
    python tools/multi_source_kb.py --query "" --sources all --fetch
"""

import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.knowledge_base import KnowledgeBase


class MultiSourceKB:
    """多源知识库统一检索系统"""

    def __init__(self):
        self.local_kb = None
        self.tavily_results = []
        self.github_results = []
        self.policy_results = []
        self.trend_results = []

    def get_local_kb(self):
        """获取本地知识库实例（懒加载）"""
        if self.local_kb is None:
            try:
                self.local_kb = KnowledgeBase()
            except Exception as e:
                print(f"[ERROR] 本地知识库初始化失败: {e}")
                self.local_kb = None
        return self.local_kb

    # ==================== 1. 本地知识库搜索 ====================

    def search_local(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        搜索本地知识库
        
        Args:
            query: 搜索关键词
            top_k: 返回结果数
            
        Returns:
            搜索结果列表
        """
        kb = self.get_local_kb()
        if not kb:
            return []

        print(f"\n[LOCAL] 搜索本地知识库...")
        results = []

        try:
            docs = kb.vector_store.vectorstore.similarity_search(query, k=top_k)
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get('source', 'unknown')
                doc_type = doc.metadata.get('document_type', 'unknown')

                results.append({
                    'id': i,
                    'source_type': 'local',
                    'title': doc.metadata.get('news_title', doc.metadata.get('policy_title', 'N/A')),
                    'source': source,
                    'document_type': doc_type,
                    'content': doc.page_content[:200],
                    'score': None,
                })

            print(f"  [OK] 找到 {len(results)} 条结果")
        except Exception as e:
            print(f"  [ERROR] 搜索失败: {e}")

        return results

    # ==================== 2. Tavily 网络搜索 ====================

    def search_tavily(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        使用 Tavily API 进行网络搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        print(f"\n[TAVILY] 搜索网络...")

        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from tavily_search import tavily_search, format_results

            data = tavily_search(query, max_results=max_results)

            if not data:
                print("  [WARN] 搜索失败或无数据")
                return []

            results = []
            for i, r in enumerate(data.get('results', [])[:max_results], 1):
                results.append({
                    'id': i,
                    'source_type': 'tavily',
                    'title': r.get('title', '无标题'),
                    'source': r.get('url', 'unknown'),
                    'document_type': 'web_article',
                    'content': r.get('content', '')[:200],
                    'score': r.get('score', 0),
                    'published_date': r.get('published_date', '未知'),
                })

            print(f"  [OK] 找到 {len(results)} 条结果")
            self.tavily_results = results
            return results

        except ImportError:
            print("  [ERROR] 无法导入 tavily_search 模块")
            return []
        except Exception as e:
            print(f"  [ERROR] 搜索失败: {e}")
            return []

    # ==================== 3. GitHub 搜索 ====================

    def search_github(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        搜索 GitHub 仓库
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        print(f"\n[GITHUB] 搜索 GitHub...")

        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from github_collector import GitHubCollector

            collector = GitHubCollector()
            repos = collector.search_repositories(query, max_results=max_results)

            if not repos:
                print("  [WARN] 未找到相关仓库")
                return []

            results = []
            for i, repo in enumerate(repos[:max_results], 1):
                readme = collector.get_readme(repo['full_name'])

                results.append({
                    'id': i,
                    'source_type': 'github',
                    'title': repo.get('full_name', 'unknown'),
                    'source': repo.get('html_url', ''),
                    'document_type': 'github_repo',
                    'content': f"{repo.get('description', '')}\nStars: {repo.get('stargazers_count', 0)}\nLanguage: {repo.get('language', '')}",
                    'score': repo.get('score', 0),
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'language': repo.get('language', ''),
                    'readme_preview': readme[:200] if readme else '',
                })

            print(f"  [OK] 找到 {len(results)} 个仓库")
            self.github_results = results
            return results

        except ImportError:
            print("  [ERROR] 无法导入 github_collector 模块")
            return []
        except Exception as e:
            print(f"  [ERROR] 搜索失败: {e}")
            return []

    # ==================== 4. 政策情报搜索 ====================

    def search_policy(self, keyword: str = "", days: int = 7, limit: int = 10) -> List[Dict]:
        """
        搜索政策情报
        
        Args:
            keyword: 搜索关键词
            days: 最近 N 天
            limit: 最多返回条数
            
        Returns:
            搜索结果列表
        """
        print(f"\n[POLICY] 搜索政策情报...")

        try:
            trend_dir = project_root.parent / "trend-radar"
            policy_dir = trend_dir / "documents" / "政策情报"

            if not policy_dir.exists():
                print(f"  [WARN] 政策目录不存在: {policy_dir}")
                return []

            # 读取所有政策报告文件
            policy_files = sorted(policy_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)

            results = []
            for filepath in policy_files[:limit]:
                content = filepath.read_text(encoding='utf-8')

                # 解析政策条目
                policy_pattern = r'### \d+\.\s+(.+?)\n- \*\*发文机关\*\*: (.+?)\n- \*\*发布日期\*\*: (.+?)\n- \*\*文件编号\*\*: (.+?)\n- \*\*分类\*\*: (.+?)\n- \*\*摘要\*\*: (.+?)\n- \*\*链接\*\*: (.+?)\n'

                for match in re.finditer(policy_pattern, content):
                    title = match.group(1).strip()
                    authority = match.group(2).strip()
                    publish_date = match.group(3).strip()
                    doc_number = match.group(4).strip()
                    category = match.group(5).strip()
                    summary = match.group(6).strip()
                    link = match.group(7).strip()

                    # 如果有关键词过滤
                    if keyword and keyword not in title and keyword not in summary:
                        continue

                    results.append({
                        'id': len(results) + 1,
                        'source_type': 'policy',
                        'title': title,
                        'source': f"policy/{filepath.name}",
                        'document_type': 'government_policy',
                        'content': f"{authority} | {publish_date} | {doc_number}\n{summary}",
                        'score': None,
                        'authority': authority,
                        'publish_date': publish_date,
                        'doc_number': doc_number,
                        'category': category,
                        'link': link,
                    })

            print(f"  [OK] 找到 {len(results)} 条政策")
            self.policy_results = results
            return results

        except Exception as e:
            print(f"  [ERROR] 搜索失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    # ==================== 5. TrendRadar 热点采集 ====================

    def fetch_trend(self, platforms: List[str] = None, limit_per_platform: int = 10) -> List[Dict]:
        """
        从 TrendRadar 采集热点新闻
        
        Args:
            platforms: 平台列表
            limit_per_platform: 每个平台数量
            
        Returns:
            热点新闻列表
        """
        print(f"\n[TREND] 采集 TrendRadar 热点...")

        try:
            trend_dir = project_root.parent / "trend-radar"
            collector_path = trend_dir / "collector.py"

            if not collector_path.exists():
                print(f"  [WARN] TrendRadar collector 不存在")
                return []

            # 动态导入
            import importlib.util
            spec = importlib.util.spec_from_file_location("trend_collector", collector_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            collector = module.TrendCollector()
            news_items = collector.fetch_hot_news(platforms=platforms, limit_per_platform=limit_per_platform)

            if not news_items:
                print("  [WARN] 未获取到热点数据")
                return []

            results = []
            for i, item in enumerate(news_items, 1):
                extra = item.get('extra', {})
                results.append({
                    'id': i,
                    'source_type': 'trend',
                    'title': item.get('title', '无标题'),
                    'source': f"trend/{item.get('platform', 'unknown')}",
                    'document_type': 'hot_news',
                    'content': f"平台: {item.get('platform', '')}\n热度: {extra.get('info', 'N/A')}\n{item.get('url', '')}",
                    'score': None,
                    'platform': item.get('platform', ''),
                    'hotness': extra.get('info', 'N/A'),
                    'url': item.get('url', ''),
                })

            print(f"  [OK] 采集到 {len(results)} 条热点")
            self.trend_results = results
            return results

        except Exception as e:
            print(f"  [ERROR] 采集失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    # ==================== 统一查询接口 ====================

    def search_all(self, query: str, top_k: int = 5) -> Dict[str, List[Dict]]:
        """
        从所有来源搜索
        
        Args:
            query: 搜索关键词
            top_k: 每来源返回结果数
            
        Returns:
            各来源搜索结果字典
        """
        results = {
            'local': self.search_local(query, top_k),
            'tavily': self.search_tavily(query, top_k),
            'github': self.search_github(query, top_k),
            'policy': self.search_policy(query, top_k),
        }

        return results

    def search_by_sources(self, query: str, sources: List[str], top_k: int = 5) -> Dict[str, List[Dict]]:
        """
        按指定来源搜索
        
        Args:
            query: 搜索关键词
            sources: 来源列表 ['local', 'tavily', 'github', 'policy', 'trend']
            top_k: 每来源返回结果数
            
        Returns:
            各来源搜索结果字典
        """
        results = {}

        if 'local' in sources:
            results['local'] = self.search_local(query, top_k)

        if 'tavily' in sources:
            results['tavily'] = self.search_tavily(query, top_k)

        if 'github' in sources:
            results['github'] = self.search_github(query, top_k)

        if 'policy' in sources:
            results['policy'] = self.search_policy(query, top_k)

        if 'trend' in sources:
            results['trend'] = self.fetch_trend(top_k)

        return results

    # ==================== 格式化输出 ====================

    def format_results(self, results: Dict[str, List[Dict]]) -> str:
        """
        格式化搜索结果输出
        
        Args:
            results: 搜索结果字典
            
        Returns:
            Markdown 格式字符串
        """
        lines = []
        lines.append("# 多源知识库搜索结果")
        lines.append(f"\n> 搜索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        total_count = sum(len(v) for v in results.values())
        lines.append(f"**总计：{total_count} 条结果**\n")

        for source_type, items in results.items():
            if not items:
                continue

            source_names = {
                'local': '[本地] 知识库',
                'tavily': '[网络] 搜索',
                'github': '[GitHub] 仓库',
                'policy': '[政策] 情报',
                'trend': '[趋势] 热点',
            }

            lines.append(f"## {source_names.get(source_type, source_type)} ({len(items)} 条)")
            lines.append("")

            for item in items:
                lines.append(f"### {item['id']}. {item['title']}")
                lines.append("")
                lines.append(f"- **来源**: {item['source']}")
                lines.append(f"- **类型**: {item['document_type']}")

                if item['source_type'] == 'github':
                    lines.append(f"- **Stars**: {item.get('stars', 0)}")
                    lines.append(f"- **语言**: {item.get('language', '')}")

                if item['source_type'] == 'policy':
                    lines.append(f"- **发文机关**: {item.get('authority', '')}")
                    lines.append(f"- **发布日期**: {item.get('publish_date', '')}")
                    lines.append(f"- **文件编号**: {item.get('doc_number', '')}")

                if item['source_type'] == 'trend':
                    lines.append(f"- **平台**: {item.get('platform', '')}")
                    lines.append(f"- **热度**: {item.get('hotness', '')}")

                lines.append(f"\n{item['content'][:300]}")
                lines.append("")
                lines.append("---")
                lines.append("")

        return "\n".join(lines)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="多源知识库统一检索系统")
    parser.add_argument("--query", "-q", default="", help="搜索关键词")
    parser.add_argument("--sources", "-s", nargs='+', default=['local'],
                       choices=['local', 'tavily', 'github', 'policy', 'trend', 'all'],
                       help="搜索来源")
    parser.add_argument("--no-local", action="store_true",
                       help="实时搜索模式：自动排除本地知识库（适合搜今日热点等实时信息）")
    parser.add_argument("--realtime", "-r", action="store_true",
                       help="实时搜索模式：自动排除本地知识库，只搜 Tavily/TrendRadar")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="每来源返回结果数")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径")
    parser.add_argument("--fetch", action="store_true", help="主动采集数据（trend/policy）")

    args = parser.parse_args()

    # 转换 sources
    if 'all' in args.sources:
        sources = ['local', 'tavily', 'github', 'policy', 'trend']
    else:
        sources = args.sources

    # 创建多源知识库
    kb = MultiSourceKB()

    print("=" * 60)
    print("多源知识库检索系统")
    print("=" * 60)
    print(f"搜索词: {args.query or '(采集模式)'}")
    print(f"来源: {', '.join(sources)}")
    print("=" * 60)

    # 执行搜索
    if args.fetch:
        # 采集模式
        if 'trend' in sources:
            kb.fetch_trend(args.top_k)
        if 'policy' in sources:
            kb.search_policy(args.query, args.top_k)
    else:
        # 搜索模式
        results = kb.search_by_sources(args.query, sources, args.top_k)

        # 格式化输出
        output = kb.format_results(results)

        # 打印或保存
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n[OK] 结果已保存到: {args.output}")
        else:
            print("\n" + output)


if __name__ == "__main__":
    main()
