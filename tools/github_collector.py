#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 数据收集工具

用法：
    python github_collector.py "next-daily-hot"
    python github_collector.py "AI-video-generation" --max-results 5
"""
import os
import sys
import json
import requests
import base64
from datetime import datetime
from pathlib import Path

# 导入配置
sys.path.insert(0, str(Path(__file__).parent.parent))
from rag_config import GITHUB_API_KEY, GITHUB_API_BASE, logger

class GitHubCollector:
    def __init__(self):
        self.headers = {
            "Authorization": f"token {GITHUB_API_KEY}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_dir = Path(__file__).parent.parent / "documents" / "_github_search"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def search_repositories(self, query: str, max_results: int = 5) -> list:
        """
        搜索 GitHub 仓库

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            仓库信息列表
        """
        url = f"{GITHUB_API_BASE}/search/repositories"
        params = {
            "q": query,
            "per_page": min(max_results, 100)
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                repos = data.get("items", [])
                logger.info(f"搜索 '{query}' 找到 {len(repos)} 个仓库")
                return repos
            else:
                logger.error(f"搜索失败: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            logger.error(f"搜索 '{query}' 时发生错误: {e}")
            return []

    def get_repository_info(self, full_name: str) -> dict:
        """
        获取仓库详细信息

        Args:
            full_name: 仓库完整名称，如 "owner/repo"

        Returns:
            仓库详细信息
        """
        url = f"{GITHUB_API_BASE}/repos/{full_name}"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.error(f"获取仓库信息失败 {full_name}: {e}")
            return {}

    def get_readme(self, full_name: str) -> str:
        """
        获取仓库的 README 内容

        Args:
            full_name: 仓库完整名称

        Returns:
            README 内容（Markdown 格式）
        """
        url = f"{GITHUB_API_BASE}/repos/{full_name}/readme"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                readme_data = response.json()
                content = readme_data.get("content", "")

                # 解码 base64 内容
                if content:
                    try:
                        decoded_content = base64.b64decode(content).decode('utf-8')
                        return decoded_content
                    except:
                        logger.error(f"解码 README 内容失败: {full_name}")
                        return content
                return ""
            else:
                logger.debug(f"仓库 {full_name} 没有 README 或无法访问")
                return ""

        except Exception as e:
            logger.error(f"获取 README {full_name} 时发生错误: {e}")
            return ""

    def get_issues(self, full_name: str, max_issues: int = 20) -> list:
        """
        获取仓库的 Issue 信息

        Args:
            full_name: 仓库完整名称
            max_issues: 最大 Issue 数量

        Returns:
            Issue 信息列表
        """
        url = f"{GITHUB_API_BASE}/repos/{full_name}/issues"
        params = {
            "state": "all",  # 包括 open 和 closed
            "per_page": min(max_issues, 100)
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                issues = response.json()
                logger.info(f"获取到 {len(issues)} 个 Issue")
                return issues
            else:
                logger.error(f"获取 Issues 失败 {full_name}: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"获取 Issues {full_name} 时发生错误: {e}")
            return []

    def analyze_repository(self, repo_info: dict, readme_content: str, issues: list) -> dict:
        """
        分析仓库信息并生成摘要

        Args:
            repo_info: 仓库基本信息
            readme_content: README 内容
            issues: Issue 列表

        Returns:
            分析结果
        """
        analysis = {
            "basic_info": {
                "name": repo_info.get("full_name"),
                "description": repo_info.get("description", ""),
                "language": repo_info.get("language", ""),
                "stargazers_count": repo_info.get("stargazers_count", 0),
                "forks_count": repo_info.get("forks_count", 0),
                "created_at": repo_info.get("created_at", ""),
                "updated_at": repo_info.get("updated_at", ""),
                "size": repo_info.get("size", 0),
                "license": repo_info.get("license", {}).get("name", "No License") if repo_info.get("license") else "No License",
                "topics": repo_info.get("topics", [])
            },
            "readme_content": readme_content,
            "issues_count": len(issues),
            "issues_summary": [],
            "analysis_summary": ""
        }

        # 分析 Issues
        open_issues = [issue for issue in issues if issue.get("state") == "open"]
        analysis["issues_summary"] = [
            {
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "comments": issue.get("comments", 0)
            }
            for issue in open_issues[:5]
        ]

        # 生成摘要
        summary_lines = [
            f"仓库: {analysis['basic_info']['name']}",
            f"描述: {analysis['basic_info']['description']}",
            f"Stars: {analysis['basic_info']['stargazers_count']} | "
            f"Forks: {analysis['basic_info']['forks_count']} | "
            f"语言: {analysis['basic_info']['language']}",
            f"Topics: {', '.join(analysis['basic_info']['topics'])}",
            f"Issues: {len(open_issues)} 个开放"
        ]
        analysis["analysis_summary"] = " | ".join(summary_lines)

        return analysis

    def save_analysis(self, query: str, analysis: dict) -> str:
        """
        保存分析结果到文件

        Args:
            query: 搜索关键词
            analysis: 分析结果

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"github_analysis_{query}_{timestamp}.json"
        filepath = self.base_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)

            logger.info(f"分析结果已保存到: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"保存分析结果失败: {e}")
            return ""

    def search_and_import_to_chroma(self, query: str, max_results: int = 5, kb=None):
        """
        搜索 GitHub 仓库并直接导入 ChromaDB

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            kb: 知识库实例（可选，默认自动创建）

        Returns:
            仓库信息列表
        """
        from langchain_core.documents import Document

        if kb is None:
            from rag_core.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()

        logger.info(f"搜索 GitHub 仓库并导入 ChromaDB: {query}")

        # 搜索仓库
        repos = self.search_repositories(query, max_results)

        if not repos:
            logger.warning(f"未找到相关仓库: {query}")
            return []

        results = []

        for repo in repos:
            full_name = repo.get("full_name")
            logger.info(f"正在导入仓库: {full_name}")

            # 获取 README
            readme_content = self.get_readme(full_name)

            # 构建文档内容
            content = f"""## {full_name}

{repo.get('description', '')}

**基本信息:**
- Stars: {repo.get('stargazers_count', 0)}
- Forks: {repo.get('forks_count', 0)}
- 语言: {repo.get('language', 'Unknown')}
- 创建时间: {repo.get('created_at', 'Unknown')}
- 更新时间: {repo.get('updated_at', 'Unknown')}

**Topics:** {', '.join(repo.get('topics', []))}

**README 预览:**
{readme_content[:500] if readme_content else '无 README'}
"""

            # 创建 Document
            doc = Document(
                page_content=content,
                metadata={
                    'source': repo.get('html_url', ''),
                    'news_title': full_name,
                    'document_type': 'github_repo',
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'language': repo.get('language', ''),
                    'topics': repo.get('topics', []),
                }
            )

            # 添加到 ChromaDB
            kb.vector_store.add_documents([doc])

            # 同步 Wiki 层（实体提取）
            kb._sync_wiki_layer([doc], f"github/{query}")

            results.append({
                'full_name': full_name,
                'stars': repo.get('stargazers_count', 0),
                'language': repo.get('language', ''),
                'topics': repo.get('topics', []),
                'html_url': repo.get('html_url', '')
            })

        logger.info(f"成功导入 {len(results)} 个仓库到 ChromaDB")
        return results

    def collect_and_analyze(self, query: str, max_results: int = 5, include_issues: bool = True) -> list:
        """
        完整的数据收集和分析流程

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            include_issues: 是否包含 Issues 分析

        Returns:
            分析结果列表
        """
        logger.info(f"开始收集 GitHub 数据: {query}")

        # 搜索仓库
        repos = self.search_repositories(query, max_results)

        if not repos:
            logger.warning(f"未找到相关仓库: {query}")
            return []

        results = []

        for repo in repos:
            full_name = repo.get("full_name")
            logger.info(f"正在分析仓库: {full_name}")

            # 获取详细信息
            repo_info = self.get_repository_info(full_name)

            # 获取 README
            readme_content = self.get_readme(full_name)

            # 获取 Issues（可选）
            issues = []
            if include_issues:
                issues = self.get_issues(full_name)

            # 分析仓库
            analysis = self.analyze_repository(repo_info, readme_content, issues)

            # 保存结果
            filepath = self.save_analysis(f"{query}_{full_name.replace('/', '_')}", analysis)
            analysis["saved_file"] = filepath

            results.append(analysis)

        return results

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="GitHub 数据收集工具")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--max-results", type=int, default=5, help="最大结果数")
    parser.add_argument("--no-issues", action="store_true", help="不包含 Issues 分析")

    args = parser.parse_args()

    collector = GitHubCollector()
    results = collector.collect_and_analyze(
        query=args.query,
        max_results=args.max_results,
        include_issues=not args.no_issues
    )

    print(f"\n收集完成，共 {len(results)} 个结果:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['basic_info']['name']}")
        print(f"   Star: {result['basic_info']['stargazers_count']}")
        print(f"   描述: {result['basic_info']['description']}")
        if result['saved_file']:
            print(f"   保存到: {result['saved_file']}")

if __name__ == "__main__":
    main()
