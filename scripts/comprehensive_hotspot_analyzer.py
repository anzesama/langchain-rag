#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合热点采集与分析系统 v2.0

核心功能：
1. 多数据源并行采集（Tavily、Jina、TrendRadar、Policy、RSS、GitHub）
2. 交叉验证（同一热点在不同平台的出现）
3. 趋势分析（热点上升/下降趋势）
4. 雷达图可视化（多维度热点分布）
5. 智能去重和质量评估

作者：AI Assistant
创建时间：2024-12-08
最后更新：2026-07-01
"""

import os
import sys
import time
import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
import argparse
import subprocess
import requests
import hashlib

# ==================== 环境配置 ====================

# 基础路径配置
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "documents" / "综合热点分析"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 设置全局变量（修复 argparse 语法错误）
OUTPUT_DIR_GLOBAL = OUTPUT_DIR

def fix_encoding():
    """修复 Windows 控制台编码问题"""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

# ==================== 数据源配置 ====================

# 预设热点话题
DEFAULT_TOPICS = [
    "今日热点",
    "AI视频生成",
    "大语言模型",
    "自动驾驶",
    "量子计算",
    "机器人",
    "新能源",
    "芯片半导体",
    "生物科技",
]

# 热点话题关键词映射（用于交叉验证）
TOPIC_KEYWORDS = {
    "AI视频生成": ["视频生成", "AI视频", "Sora", "Runway", "Pika", "可灵", "剪映"],
    "大语言模型": ["LLM", "大语言模型", "GPT", "Claude", "通义千问", "文心一言", "GLM"],
    "自动驾驶": ["自动驾驶", "Waymo", "特斯拉FSD", "小鹏", "蔚来", "百度Apollo"],
    "量子计算": ["量子计算", "Quantum", "IBM量子", "谷歌量子", "量子比特"],
    "机器人": ["机器人", "人形机器人", "Boston Dynamics", "优必选", "Figure AI"],
    "新能源": ["新能源", "光伏", "风电", "储能", "锂电池", "宁德时代"],
    "芯片半导体": ["芯片", "半导体", "ASML", "台积电", "华为芯片", "英伟达"],
    "生物科技": ["生物科技", "基因编辑", "CRISPR", "mRNA", "细胞治疗"],
}

# ==================== 数据源采集器 ====================

class SourceCollector:
    """数据源采集基类"""
    
    def __init__(self, name):
        self.name = name
        self.results = []
        self.error = None
        self.fetch_time = 0
    
    def normalize_url(self, url):
        """标准化 URL 用于去重"""
        if not url:
            return ""
        url = url.lower().strip()
        # 移除跟踪参数
        for param in ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'share']:
            url = url.split(param)[0].rstrip('&')
        return url
    
    def extract_title_hash(self, title):
        """提取标题哈希用于模糊匹配"""
        if not title:
            return ""
        # 移除常见词和标点，提取关键词
        clean_title = re.sub(r'[^\w\s]', ' ', title.lower())
        words = [w for w in clean_title.split() if len(w) > 1]
        return hashlib.md5(' '.join(sorted(words)).encode()).hexdigest()[:16]
    
    def _check_node(self, node_path):
        """检查 Node.js 是否可用"""
        try:
            result = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

class TavilyCollector(SourceCollector):
    """Tavily 搜索采集器"""
    
    def __init__(self):
        super().__init__("Tavily搜索")
        self.api_key = os.getenv("TAVILY_API_KEY", "tvly-xxxxxxxxxxxxxxxxxxxxxxxx")
    
    def search(self, query, max_results=10):
        """使用 Tavily API 搜索"""
        start_time = time.time()
        try:
            # 构建搜索查询
            search_query = f"{query} 新闻 最新 动态 趋势"
            
            # 构建 API URL
            url = "https://api.tavily.com/search"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "query": search_query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_domains": ["news.google.com", "bbc.com", "reuters.com", "techcrunch.com", "venturebeat.com", "bloomberg.com", "cnbc.com", "theverge.com"]
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            # 转换为统一格式
            for result in results:
                item = {
                    "source": self.name,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", ""),
                    "score": result.get("score", 0),
                    "published_date": result.get("published_date", ""),
                    "type": "tavily"
                }
                self.results.append(item)
            
            self.fetch_time = time.time() - start_time
            return len(results)
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [ERROR] {self.name}: {e}")
            return 0

class JinaSearchCollector(SourceCollector):
    """Jina AI 内容采集器"""
    
    def __init__(self):
        super().__init__("Jina搜索")
        self.api_key = os.getenv("JINA_API_KEY", "jina-xxxxxxxxxxxxxxxxxxxxxxxx")
    
    def search(self, query, max_results=10):
        """使用 Jina AI 提取网页内容"""
        start_time = time.time()
        try:
            # 构建搜索查询
            url = f"https://s.jina.ai/{query}?timeout=30"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/plain"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            content = response.text
            # 简单解析标题（Jina AI 返回格式相对固定）
            lines = content.split('\n')
            titles = [line for line in lines if len(line.strip()) > 20 and not line.startswith('#')]
            
            # 转换为统一格式
            for i, title in enumerate(titles[:max_results]):
                item = {
                    "source": self.name,
                    "title": title.strip(),
                    "url": f"https://example.com/search?q={query}&p={i+1}",
                    "content": title.strip()[:200],
                    "score": 80 - i * 5,  # 简单评分
                    "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "jina"
                }
                self.results.append(item)
            
            self.fetch_time = time.time() - start_time
            return len(self.results)
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [WARNING]  {self.name}: {e}（可能未配置API Key）")
            return 0

class RSSCollector(SourceCollector):
    """RSS 新闻采集器"""
    
    def __init__(self):
        super().__init__("RSS/网页")
        self.sources = {
            "Google News": "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "BBC Chinese": "https://www.bbc.com/zhongwen/simp",
            "CCTV": "https://news.cctv.com/"
        }
    
    def fetch_google_news(self, query, max_results=20):
        """从 Google News 获取"""
        start_time = time.time()
        try:
            url = self.sources["Google News"].format(query=query)
            response = requests.get(url, timeout=8)  # 缩短超时时间
            
            # 解析 RSS
            import feedparser
            feed = feedparser.parse(response.content)
            
            count = 0
            for entry in feed.entries[:max_results]:
                item = {
                    "source": f"{self.name}",
                    "title": entry.title,
                    "url": entry.link,
                    "content": entry.summary[:300] if entry.summary else "",
                    "score": 0,
                    "published_date": entry.published,
                    "type": "google_news"
                }
                self.results.append(item)
                count += 1
            
            self.fetch_time = time.time() - start_time
            return count
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [WARNING]  Google News: {e}")
            return 0
    
    def fetch_bbc_chinese(self, max_results=15):
        """从 BBC 中文获取"""
        start_time = time.time()
        try:
            response = requests.get(self.sources["BBC Chinese"], timeout=5)  # 缩短超时时间
            response.raise_for_status()
            
            # 简单提取链接
            import re
            links = re.findall(r'href="(/zhongwen/simp/[^"]+)"', response.text)
            
            count = 0
            for link in links[:max_results]:
                full_url = f"https://www.bbc.com{link}"
                item = {
                    "source": f"{self.name}",
                    "title": f"BBC中文: {link.split('/')[-1]}",
                    "url": full_url,
                    "content": f"BBC中文新闻 - {link.split('/')[-1]}",
                    "score": 0,
                    "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "bbc_chinese"
                }
                self.results.append(item)
                count += 1
            
            self.fetch_time = time.time() - start_time
            return count
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [WARNING]  BBC: {e}")
            return 0
    
    def fetch_cctv(self, max_results=15):
        """从 CCTV 获取"""
        start_time = time.time()
        try:
            response = requests.get(self.sources["CCTV"], timeout=10)
            response.raise_for_status()
            
            # 简单提取新闻链接
            import re
            links = re.findall(r'href="(/[^"]+)"', response.text)
            news_links = [l for l in links if 'news' in l and l.endswith('.html')]
            
            count = 0
            for link in news_links[:max_results]:
                full_url = f"https://news.cctv.com{link}"
                item = {
                    "source": f"{self.name}",
                    "title": f"CCTV: {link.split('/')[-1]}",
                    "url": full_url,
                    "content": f"CCTV新闻 - {link.split('/')[-1]}",
                    "score": 0,
                    "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "cctv"
                }
                self.results.append(item)
                count += 1
            
            self.fetch_time = time.time() - start_time
            return count
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [WARNING]  CCTV: {e}")
            return 0
    
    def fetch_baidu(self, query, max_results=10):
        """从百度获取新闻"""
        start_time = time.time()
        try:
            url = f"https://news.baidu.com/ns?word={query}&tn=news&from=news&cl=2&rn=max_results&ct=1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 解析JSON数据
            import json
            data = json.loads(response.text)
            items = data.get("data", {}).get("list", [])
            
            for item in items[:max_results]:
                news_item = {
                    "source": self.name,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("digest", ""),
                    "score": 0,
                    "published_date": item.get("ctime", ""),
                    "type": "baidu_news",
                }
                self.results.append(news_item)
            self.fetch_time = time.time() - start_time
            return len(items)
        except Exception as e:
            print(f"  [WARNING]  百度新闻: {e}")
        return 0

class TrendRadarCollector(SourceCollector):
    """TrendRadar 多平台热点采集器"""
    
    def __init__(self):
        super().__init__("TrendRadar")
    
    def fetch(self, platforms=None, limit_per_platform=10):
        """从 TrendRadar 获取多平台热点"""
        start_time = time.time()
        try:
            if platforms is None:
                platforms = ["zhihu", "weibo", "douyin", "bilibili", "baidu", "wallstreetcn"]
            
            # 使用 trend_env 环境的 Python 运行 collector.py
            trend_env_python = r"D:\class\miniconda3\envs\trend_env\python.exe"
            trend_collector_path = Path(__file__).parent / "trend-radar" / "collector.py"
            
            if not Path(trend_env_python).exists():
                print(f"  [WARNING]  TrendRadar: trend_env 环境 Python 不存在")
                self.fetch_time = time.time() - start_time
                return 0
            
            if not trend_collector_path.exists():
                print(f"  [WARNING]  TrendRadar: collector.py 不存在于 {trend_collector_path}")
                self.fetch_time = time.time() - start_time
                return 0
            
            import subprocess
            
            # 运行 collector.py 并捕获输出（指定 UTF-8 编码避免 GBK 解码错误）
            result = subprocess.run(
                [trend_env_python, str(trend_collector_path)],
                capture_output=True, text=True, timeout=60,
                encoding='utf-8', errors='replace'
            )
            
            # 从标准输出解析获取到的新闻数量
            output = (result.stdout or '') + (result.stderr or '')
            import re
            count_match = re.search(r'共获取到\s+(\d+)\s+条', output)
            news_count = int(count_match.group(1)) if count_match else 0
            
            if news_count > 0:
                print(f"  [SUCCESS] TrendRadar: 获取 {news_count} 条")
                # 从最新生成的报告中读取
                latest_report = max(
                    (f for f in trend_collector_path.parent.glob("documents/趋势情报/*.md") if f.name.startswith("趋势日报")),
                    key=lambda f: f.stat().st_mtime
                )
                report_content = latest_report.read_text(encoding="utf-8")
                
                # 解析 Markdown 报告为结构化数据
                lines = report_content.split('\n')
                current_item = {}
                in_items = False
                for line in lines:
                    if line.startswith("## [FIRE] 热点新闻"):
                        in_items = True
                        continue
                    if in_items and line.startswith("### "):
                        if current_item:
                            self.results.append(current_item)
                        title = line[4:].strip()
                        current_item = {
                            "source": self.name,
                            "title": title,
                            "url": "",
                            "content": "",
                            "score": 0,
                            "published_date": "",
                            "type": f"trendradar_zhihu",
                            "platform": "",
                        }
                    elif in_items and line.startswith("- **平台**:"):
                        plat = line.split(":")[1].strip()
                        current_item["platform"] = plat
                        current_item["type"] = f"trendradar_{plat}"
                    elif in_items and line.startswith("- **热度**:"):
                        hot = line.split(":")[1].strip()
                        current_item["published_date"] = hot
                    elif in_items and line.startswith("- **链接**:"):
                        hover = line.split(":", 1)[1].strip()
                        current_item["content"] = hover[:300]
                    elif in_items and line.startswith("- **URL**:"):
                        url = line.split(":", 1)[1].strip()
                        current_item["url"] = url
                    elif in_items and line.startswith("---"):
                        if current_item:
                            self.results.append(current_item)
                            current_item = {}
                
                self.fetch_time = time.time() - start_time
                return len(self.results)
            
        except Exception as e:
            print(f"  [ERROR] {self.name}: {e}")
        
        self.fetch_time = time.time() - start_time
        return 0

class GitHubCollector(SourceCollector):
    """GitHub 仓库数据采集器"""
    
    def __init__(self, query=None):
        super().__init__("GitHub")
        self.query = query or ""
        
        # GitHub API 配置
        self.github_api_key = os.getenv("GITHUB_API_KEY", "")
        self.github_api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.github_api_key}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 搜索查询映射
        self.search_queries = {
            "AI视频生成": "Sora OR Runway OR Pika OR video generation OR AI video",
            "大语言模型": "GPT OR large language model OR LLM OR transformer",
            "自动驾驶": "self-driving OR autonomous OR autonomous driving OR Waymo",
            "量子计算": "quantum OR quantum computing OR quantum computer",
            "机器人": "robotics OR robot OR humanoid robot OR Boston Dynamics",
            "新能源": "renewable energy OR solar OR wind OR battery",
            "芯片半导体": "chip OR semiconductor OR AI chip or GPU",
            "生物科技": "biotech OR biotechnology OR genetic OR CRISPR",
        }
    
    def fetch(self, max_results=15):
        """从 GitHub API 获取仓库数据"""
        import requests
        
        start_time = time.time()
        try:
            # 映射查询关键词
            search_query = self.search_queries.get(self.query, self.query)
            
            # 构建 GitHub 搜索 API URL
            search_url = f"{self.github_api_base}/search/repositories?q={search_query}&sort=stars&order=desc&per_page={max_results}"
            
            print(f"  [BOOK] GitHub: 搜索 {search_query}")
            
            try:
                response = requests.get(search_url, headers=self.headers, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                repositories = data.get("items", [])
                
                if not repositories:
                    print(f"  [WARNING]  GitHub: 未找到相关仓库")
                    self.fetch_time = time.time() - start_time
                    return 0
                
                print(f"  [SUCCESS] GitHub: 找到 {len(repositories)} 个仓库")
                
                # 处理每个仓库
                for repo in repositories:
                    repo_info = {
                        "source": self.name,
                        "title": repo.get("full_name", ""),
                        "url": repo.get("html_url", ""),
                        "content": repo.get("description", ""),
                        "score": repo.get("stargazers_count", 0),
                        "published_date": repo.get("created_at", ""),
                        "type": "github_repo",
                        "language": repo.get("language", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "updated_at": repo.get("updated_at", "")
                    }
                    self.results.append(repo_info)
                
                self.fetch_time = time.time() - start_time
                return len(repositories)
                
            except requests.exceptions.HTTPError as e:
                if response.status_code == 403:
                    print(f"  [WARNING]  GitHub: API 调用次数限制，请稍后再试")
                else:
                    print(f"  [WARNING]  GitHub: HTTP 错误 {response.status_code}")
            except Exception as e:
                print(f"  [WARNING]  GitHub: {e}")
                
        except Exception as e:
            print(f"  [ERROR] GitHub: {e}")
        
        self.fetch_time = time.time() - start_time
        return 0
    
    def fetch_issues(self, repo_name, max_issues=10):
        """获取仓库的 issues"""
        try:
            issues_url = f"{self.github_api_base}/repos/{repo_name}/issues?state=open&per_page={max_issues}"
            response = requests.get(issues_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            issues = response.json()
            for issue in issues:
                issue_info = {
                    "source": self.name,
                    "title": f"[{repo_name}] {issue.get('title', '')}",
                    "url": issue.get("html_url", ""),
                    "content": issue.get("body", ""),
                    "score": 0,
                    "published_date": issue.get("created_at", ""),
                    "type": "github_issue",
                    "repo_name": repo_name,
                    "issue_number": issue.get("number", 0),
                    "state": issue.get("state", "open")
                }
                self.results.append(issue_info)
            
            return len(issues)
            
        except Exception as e:
            print(f"  [WARNING]  GitHub Issues: {e}")
            return 0

class PolicyCollector(SourceCollector):
    """政策数据采集器"""
    
    def __init__(self):
        super().__init__("政策数据")
    
    def fetch(self, keyword="", days=7, limit=20):
        """从 MCP 服务器获取政策数据"""
        start_time = time.time()
        try:
            from datetime import timedelta
            mcp_script = Path(__file__).parent / "trend-radar" / "node_modules" / "@iflow-mcp" / "guangxiangdebizi-central-policy-mcp" / "build" / "index.js"
            
            if not mcp_script.exists():
                print(f"  [WARNING]  Policy MCP 未安装")
                self.fetch_time = time.time() - start_time
                return 0
            
            # 检查 Node.js
            node_path = "node"
            if not self._check_node(node_path):
                conda_node = r"D:\class\miniconda3\envs\trend_env\node.exe"
                if Path(conda_node).exists():
                    node_path = conda_node
            
            import subprocess
            import json as _json
            
            search_keyword = keyword or "国务院"
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            # initialize
            init_payload = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "comprehensive-analyzer", "version": "2.0"}}
            }
            
            proc = subprocess.Popen(
                [node_path, str(mcp_script)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace"
            )
            
            proc.stdin.write(_json.dumps(init_payload) + "\n")
            proc.stdin.flush()
            init_resp = proc.stdout.readline()
            
            if "result" not in init_resp:
                print(f"  [WARNING]  Policy MCP 初始化失败")
                self.fetch_time = time.time() - start_time
                return 0
            
            # search
            search_payload = {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {
                    "name": "search_policies",
                    "arguments": {
                        "keyword": search_keyword,
                        "start_date": start_date,
                        "end_date": end_date,
                        "limit": limit
                    }
                }
            }
            
            proc.stdin.write(_json.dumps(search_payload) + "\n")
            proc.stdin.flush()
            search_resp = proc.stdout.readline()
            
            if "result" in search_resp:
                result = _json.loads(search_resp)
                data = result.get("result", {}).get("content", "")
                
                # 简单解析政策数据
                if data:
                    import re
                    policies = re.findall(r'\*\*(.*?)\*\*: (.*?)\n', data)
                    for title, content in policies:
                        item = {
                            "source": self.name,
                            "title": title,
                            "url": "",
                            "content": content[:300],
                            "score": 85,  # 政策数据默认高可信度
                            "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "policy"
                        }
                        self.results.append(item)
                
                self.fetch_time = time.time() - start_time
                return len(policies)
            
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  [ERROR] {self.name}: {e}")
            return 0

# ==================== 交叉验证引擎 ====================

class CrossValidator:
    """交叉验证引擎"""
    
    def __init__(self, results):
        self.results = results
        self.cv_results = {}
    
    def validate(self):
        """执行交叉验证"""
        print("\n" + "=" * 60)
        print("[SEARCH] 交叉验证分析")
        print("=" * 60)
        
        # 1. URL 去重
        url_map = defaultdict(list)
        for i, item in enumerate(self.results):
            url = item.get("url", "")
            norm_url = self._normalize_url(url)
            url_map[norm_url].append(i)
        
        duplicate_urls = len([urls for urls in url_map.values() if len(urls) > 1])
        print(f"  [REPORT] URL 去重: 发现 {duplicate_urls} 条重复URL")
        
        # 2. 标题聚类
        title_clusters = self._cluster_titles()
        print(f"  [REPORT] 标题聚类: 发现 {len(title_clusters)} 组相似标题")
        
        # 3. 平台热力图
        platform_dist = self._analyze_platform_distribution()
        print(f"  [REPORT] 平台热力图: {len(platform_dist)} 个平台有数据")
        
        # 4. 评分计算
        scores = self._calculate_scores(url_map)
        
        self.cv_results = {
            "total_count": len(self.results),
            "unique_count": len(url_map),
            "duplicate_urls": duplicate_urls,
            "title_clusters": title_clusters,
            "platform_distribution": platform_dist,
            "url_map": url_map,
            "scores": scores
        }
        
        return self.cv_results
    
    def _normalize_url(self, url):
        """标准化URL"""
        if not url:
            return ""
        url = url.lower().strip()
        # 移除跟踪参数
        for param in ['?', '&', 'utm_']:
            url = url.split(param)[0]
        return url
    
    def _cluster_titles(self):
        """标题聚类（简化版）"""
        clusters = defaultdict(list)
        for i, item in enumerate(self.results):
            title = item.get("title", "")
            if title:
                # 简单的关键词聚类
                words = re.findall(r'\b[\w\u4e00-\u9fff]+\b', title.lower())
                key_words = [w for w in words if len(w) > 2]
                if key_words:
                    main_keyword = max(set(key_words), key=key_words.count)
                    clusters[main_keyword].append(i)
        
        # 过滤掉单个结果的聚类
        return [cluster for cluster in clusters.values() if len(cluster) > 1]
    
    def _analyze_platform_distribution(self):
        """分析平台分布"""
        platform_count = defaultdict(int)
        for item in self.results:
            source = item.get("source", "未知")
            platform_count[source] += 1
        return dict(platform_count)
    
    def _calculate_scores(self, url_map):
        """计算可信度评分"""
        scores = {}
        
        for item in self.results:
            url = item.get("url", "")
            norm_url = self._normalize_url(url)
            
            # 基础分
            score = 50
            
            # 多平台出现加分
            if norm_url in url_map and len(url_map[norm_url]["cross_sources"]) > 1:
                score += 20 * (len(url_map[norm_url]["cross_sources"]) - 1)
            
            # 有热度数据加分
            if item.get("published_date") and "热度" in str(item.get("published_date", "")):
                score += 10
            
            # 有内容摘要加分
            if item.get("content"):
                score += 10
            
            scores[url] = min(score, 100)
        
        return scores

# ==================== 趋势分析引擎 ====================

class TrendAnalyzer:
    """趋势分析引擎"""
    
    def __init__(self, results, cv_results):
        self.results = results
        self.cv_results = cv_results
        self.trend_analysis = {}
    
    def analyze(self):
        """执行趋势分析"""
        print("\n" + "=" * 60)
        print("[CHART] 趋势分析")
        print("=" * 60)
        
        # 1. 数据来源分布
        source_dist = self._analyze_source_distribution()
        print("  [REPORT] 数据来源分布:")
        for source, count in source_dist.items():
            bar = "█" * min(count // 2, 20)
            print(f"    {source}: {count} 条 {bar}")
        
        # 2. 内容类型分布
        type_dist = self._analyze_type_distribution()
        print("  [REPORT] 内容类型分布:")
        for type_name, count in type_dist.items():
            print(f"    {type_name}: {count} 条")
        
        # 3. 热点排序
        top_hot = self._identify_top_hotspots()
        print("  [REPORT] Top 20 热门内容:")
        for i, item in enumerate(top_hot[:20], 1):
            title = item.get("title", "无标题")[:50] + "..." if len(item.get("title", "")) > 50 else item.get("title", "无标题")
            print(f"    {i}. [{item.get('source', '未知')}] {title}")
        
        # 4. 跨平台热点
        cross_platform = self._identify_cross_platform_hotspots()
        if cross_platform:
            print("  [REPORT] 跨平台热点（多源验证）:")
            for title, info in list(cross_platform.items())[:5]:
                print(f"    - {title[:40]}... ({', '.join(info['sources'])})")
        
        # 5. 可信度分析
        cred_dist = self._analyze_credibility_distribution()
        print("  [REPORT] 可信度分布:")
        for level, count in cred_dist.items():
            print(f"    {level}: {count} 条")
        
        self.trend_analysis = {
            "source_distribution": source_dist,
            "type_distribution": type_dist,
            "top_hot": top_hot,
            "cross_platform_hotspots": cross_platform,
            "credibility_distribution": cred_dist
        }
        
        return self.trend_analysis
    
    def _analyze_source_distribution(self):
        """分析数据来源分布"""
        source_count = defaultdict(int)
        for item in self.results:
            source = item.get("source", "未知")
            source_count[source] += 1
        return dict(source_count)
    
    def _analyze_type_distribution(self):
        """分析内容类型分布"""
        type_count = defaultdict(int)
        for item in self.results:
            type_name = item.get("type", "未知")
            type_count[type_name] += 1
        return dict(type_count)
    
    def _identify_top_hotspots(self):
        """识别热门热点"""
        # 根据标题、来源、类型等综合评分
        scored_items = []
        for item in self.results:
            score = 0
            
            # 根据来源权重
            source_weights = {
                "Tavily搜索": 10,
                "GitHub": 8,
                "Jina搜索": 8,
                "TrendRadar": 6,
                "政策数据": 5,
                "RSS/网页": 4
            }
            score += source_weights.get(item.get("source", ""), 3)
            
            # 根据类型权重
            type_weights = {
                "github_repo": 8,
                "tavily": 7,
                "policy": 6,
                "jina": 5,
                "google_news": 5,
                "bbc_chinese": 4,
                "trendradar_zhihu": 4,
                "baidu_news": 3,
                "cctv": 3,
                "jina": 3
            }
            score += type_weights.get(item.get("type", ""), 1)
            
            # 根据长度（内容更丰富）
            content = item.get("content", "")
            if content:
                score += min(len(content) // 100, 10)
            
            # 根据是否有URL
            if item.get("url"):
                score += 5
            
            item["score"] = score
            scored_items.append(item)
        
        # 按评分排序
        return sorted(scored_items, key=lambda x: x.get("score", 0), reverse=True)
    
    def _identify_cross_platform_hotspots(self):
        """识别跨平台热点"""
        # 简单实现：找出标题相似的内容
        title_groups = defaultdict(list)
        
        for item in self.results:
            title = item.get("title", "")
            if title:
                # 提取核心关键词
                words = re.findall(r'\b[\w\u4e00-\u9fff]+\b', title.lower())
                key_words = [w for w in words if len(w) > 2]
                if key_words:
                    title_key = ' '.join(sorted(key_words[:3]))  # 取前3个关键词
                    title_groups[title_key].append(item)
        
        # 找出跨平台的热点（同一标题关键词出现在多个来源）
        cross_platform = {}
        for title_key, items in title_groups.items():
            sources = set(item.get("source", "") for item in items)
            if len(sources) > 1 and len(items) >= 2:
                # 取第一个作为代表
                representative = items[0]
                cross_platform[representative.get("title", "")] = {
                    "sources": list(sources),
                    "count": len(items)
                }
        
        return cross_platform
    
    def _analyze_credibility_distribution(self):
        """分析可信度分布"""
        cred_levels = defaultdict(int)
        
        for item in self.results:
            source = item.get("source", "")
            type_name = item.get("type", "")
            
            # 简单的可信度评估
            credibility = 50  # 默认
            
            # 根据来源调整
            if source == "政策数据":
                credibility = 85
            elif source in ["Tavily搜索", "GitHub"]:
                credibility = 75
            elif source in ["Jina搜索", "TrendRadar"]:
                credibility = 65
            elif source in ["RSS/网页"]:
                credibility = 60
            
            # 根据类型调整
            if type_name == "policy":
                credibility = 85
            elif type_name == "github_repo":
                credibility = 75
            elif type_name == "tavily":
                credibility = 70
            
            # 分档
            if credibility >= 80:
                level = "高可信(≥80)"
            elif credibility >= 50:
                level = "中可信(50-79)"
            else:
                level = "低可信(<50)"
            
            cred_levels[level] += 1
        
        return dict(cred_levels)

# ==================== 报告生成器 ====================

class ReportGenerator:
    """综合报告生成器"""
    
    def __init__(self, query, trend_analysis, radar_data, cv_results):
        self.query = query
        self.trend_analysis = trend_analysis
        self.radar_data = radar_data
        self.cv_results = cv_results
    
    def generate_markdown(self, all_results):
        """生成完整的 Markdown 报告"""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [
            f"# [REPORT] 综合热点分析报告",
            "",
            f"> **查询主题**: {self.query}",
            f"> **分析时间**: {now_str}",
            f"> **数据源**: Tavily搜索, Jina搜索, TrendRadar, 政策数据, RSS/网页, GitHub",
            f"> **总采集量**: {self.cv_results.get('total_count', 0)} 条",
            f"> **去重后**: {self.cv_results.get('unique_count', 0)} 条",
            "",
            "---",
            "",
        ]
        
        # 1. 雷达图数据
        lines.append("## [TARGET] 多维雷达图数据")
        lines.append("")
        
        radar_table = []
        for dim, score in self.radar_data.items():
            rating = "[STAR][STAR][STAR][STAR][STAR]" if score >= 80 else "[STAR][STAR][STAR][STAR]" if score >= 60 else "[STAR][STAR][STAR]" if score >= 40 else "[STAR][STAR]" if score >= 20 else "[STAR]"
            radar_table.append(f"| {dim} | {score}/100 | {rating} |")
        
        if radar_table:
            lines.extend([
                "| 维度 | 得分 | 评级 |",
                "|------|------|------|"
            ] + radar_table)
        
        lines.append("")
        
        # 2. 数据来源分布
        lines.append("## 📡 数据来源分布")
        lines.append("")
        
        source_dist = self.trend_analysis.get("source_distribution", {})
        if source_dist:
            for source, count in source_dist.items():
                bar = "█" * min(count // 2, 20)
                lines.append(f"- **{source}**: {count} 条 {bar}")
        
        lines.append("")
        
        # 3. 交叉验证结果
        lines.append("## [SEARCH] 交叉验证结果")
        lines.append("")
        lines.append(f"- **重复URL**: {self.cv_results.get('duplicate_urls', 0)} 条")
        lines.append(f"- **标题聚类组**: {len(self.cv_results.get('title_clusters', []))} 组")
        lines.append(f"- **跨平台热点**: {len(self.trend_analysis.get('cross_platform_hotspots', {}))} 个")
        lines.append("")
        
        # 4. 可信度分析
        lines.append("### 可信度分布")
        lines.append("")
        cred = self.trend_analysis.get("credibility_distribution", {})
        for level, count in cred.items():
            lines.append(f"- {level}: {count} 条")
        
        lines.append("")
        
        # 5. Top 热点内容
        lines.append("## [FIRE] Top 20 热门内容")
        lines.append("")
        
        top_hot = self.trend_analysis.get("top_hot", [])
        all_results_map = {r.get("url", ""): r for r in all_results}
        
        for i, item in enumerate(top_hot[:20], 1):
            title = item.get("title", "无标题")
            source = item.get("source", "未知")
            url = item.get("url", "")
            content = item.get("content", "")
            score = item.get("score", 0)
            published_date = item.get("published_date", "")
            
            lines.append(f"### {i}. {title[:60]}...")
            lines.append(f"- **来源**: {source}")
            lines.append(f"- **类型**: {item.get('type', '未知')}")
            
            if published_date:
                lines.append(f"- **热度/时间**: {published_date}")
            
            if url:
                lines.append(f"- **链接**: [{url}]({url})")
            
            if content:
                lines.append(f"- **摘要**: {content[:150]}")
            
            if score > 0:
                lines.append(f"- **评分**: {score}/100")
            
            lines.append("")
        
        # 6. 跨平台热点
        cross_platform = self.trend_analysis.get("cross_platform_hotspots", {})
        if cross_platform:
            lines.append("## [GLOBAL] 跨平台热点（多源验证）")
            lines.append("")
            for title, info in list(cross_platform.items())[:10]:
                lines.append(f"### {title[:60]}...")
                lines.append(f"- **覆盖平台**: {', '.join(info['sources'])}")
                lines.append(f"- **出现次数**: {info['count']}")
                lines.append("")
        
        # 7. 全部原始数据
        lines.append("## [LIST] 完整数据列表")
        lines.append("")
        for i, item in enumerate(all_results, 1):
            lines.append(f"### {i}. {item.get('title', '无标题')}")
            lines.append(f"- **来源**: {item.get('source', '未知')}")
            lines.append(f"- **类型**: {item.get('type', '未知')}")
            if item.get('url'):
                lines.append(f"- **链接**: [{item['url']}]({item['url']})")
            if item.get('content'):
                lines.append(f"- **摘要**: {item['content'][:150]}")
            lines.append("")
        
        lines.extend([
            "---",
            "",
            f"*本报告由综合热点采集与分析系统 v2.0 自动生成*",
            f"*采集时间: {now_str}*",
            ""
        ])
        
        return "\n".join(lines)
    
    def generate_radar_data(self, cv_results, trend_analysis):
        """生成雷达图数据"""
        radar_data = {}
        
        # 1. 数据源覆盖率
        total_sources = 6  # Tavily, Jina, TrendRadar, Policy, RSS, GitHub
        active_sources = len(trend_analysis.get("source_distribution", {}))
        radar_data["data_source_coverage"] = min((active_sources / total_sources) * 100, 100)
        
        # 2. 内容多样性
        type_dist = trend_analysis.get("type_distribution", {})
        max_types = 10  # 假设最多10种类型
        unique_types = len(type_dist)
        radar_data["content_diversity"] = min((unique_types / max_types) * 100, 100)
        
        # 3. 可信度
        cred_dist = trend_analysis.get("credibility_distribution", {})
        high_cred = cred_dist.get("高可信(≥80)", 0)
        total_items = cv_results.get("total_count", 1)
        radar_data["credibility"] = (high_cred / total_items) * 100
        
        # 4. 时效性
        # 简单假设：如果有最近的数据则高分
        radar_data["timeliness"] = 75  # 默认值
        
        # 5. 交叉验证率
        unique_count = cv_results.get("unique_count", 0)
        total_count = cv_results.get("total_count", 1)
        radar_data["cross_validation_rate"] = (unique_count / total_count) * 100
        
        return radar_data

# ==================== 综合热点分析器 ====================

class ComprehensiveHotspotAnalyzer:
    """综合热点分析器主控制器"""
    
    def __init__(self, query):
        self.query = query
        self.collectors = []
        self.all_results = []
        
        # 初始化所有采集器
        self._init_collectors()
    
    def _init_collectors(self):
        """初始化所有数据源采集器"""
        import requests
        
        # 1. Tavily 搜索
        self.collectors.append(TavilyCollector())
        
        # 2. Jina 搜索
        self.collectors.append(JinaSearchCollector())
        
        # 3. RSS/网页（Google News, BBC, CCTV, 百度）
        self.collectors.append(RSSCollector())
        
        # 4. TrendRadar
        self.collectors.append(TrendRadarCollector())
        
        # 5. 政策数据
        self.collectors.append(PolicyCollector())
        
        # 6. GitHub 仓库
        self.collectors.append(GitHubCollector(self.query))
        
        print(f"[SUCCESS] 已初始化 {len(self.collectors)} 个数据源采集器")
    
    def collect_all(self, max_workers=5):
        """
        并行采集所有数据源
        
        Args:
            max_workers: 最大并发线程数
        """
        print("\n" + "=" * 60)
        print(f"[START] 开始多数据源并行采集")
        print(f"   查询: {self.query}")
        print(f"   采集器数量: {len(self.collectors)}")
        print("=" * 60)
        
        total_fetched = 0
        errors = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            # 提交所有采集任务
            for collector in self.collectors:
                future = executor.submit(self._collect_from_source, collector)
                futures[future] = collector.name
            
            # 等待任务完成并处理结果
            for future in as_completed(futures):
                collector_name = futures[future]
                try:
                    count = future.result()
                    total_fetched += count
                    if count == 0:
                        errors.append(f"{collector_name}: 无数据")
                except Exception as e:
                    error_msg = f"{collector_name}: {str(e)}"
                    errors.append(error_msg)
                    print(f"  [ERROR] {error_msg}")
            
            # 收集所有结果
            self.all_results = []
            for collector in self.collectors:
                self.all_results.extend(collector.results)
            
            # 去重
            self.all_results = self._deduplicate(self.all_results)
            
            print(f"\n[SUCCESS] 采集完成!")
            print(f"   总采集: {total_fetched} 条")
            print(f"   去重后: {len(self.all_results)} 条")
            print(f"   错误: {len(errors)} 个")
            
            if errors:
                print("\n   错误详情:")
                for err in errors:
                    print(f"   - {err}")
        
        return len(self.all_results)
    
    def _collect_from_source(self, collector):
        """从单个数据源采集"""
        import requests
        
        if isinstance(collector, TavilyCollector):
            return collector.search(self.query, max_results=10)
        
        elif isinstance(collector, JinaSearchCollector):
            return collector.search(self.query, max_results=10)
        
        elif isinstance(collector, RSSCollector):
            count = 0
            count += collector.fetch_google_news(self.query, max_results=20)
            count += collector.fetch_bbc_chinese(max_results=15)
            count += collector.fetch_cctv(max_results=15)
            count += collector.fetch_baidu(self.query, max_results=10)
            return count
        
        elif isinstance(collector, TrendRadarCollector):
            return collector.fetch(limit_per_platform=10)
        
        elif isinstance(collector, PolicyCollector):
            return collector.fetch(days=7, limit=20)
        
        elif isinstance(collector, GitHubCollector):
            return collector.fetch(max_results=15)
        
        return 0
    
    def _deduplicate(self, results):
        """URL去重"""
        seen_urls = set()
        unique = []
        
        for item in results:
            url = item.get("url", "")
            if url:
                norm_url = url.lower().strip()
                for param in ['?', '&', 'utm_']:
                    norm_url = norm_url.split(param)[0]
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)
            unique.append(item)
        
        return unique
    
    def analyze(self):
        """执行完整的热点分析流程"""
        print("=" * 60)
        print("[START] 综合热点分析系统 v2.0")
        print("=" * 60)
        
        try:
            # 1. 数据采集
            self.collect_all(max_workers=5)
            
            if not self.all_results:
                print("[ERROR] 未采集到任何数据，请检查网络连接和数据源配置")
                return None
            
            # 2. 交叉验证
            validator = CrossValidator(self.all_results)
            cv_results = validator.validate()
            
            # 3. 趋势分析
            trend_analyzer = TrendAnalyzer(self.all_results, cv_results)
            trend_analysis = trend_analyzer.analyze()
            
            # 4. 雷达图数据
            reporter = ReportGenerator(self.query, trend_analysis, {}, cv_results)
            radar_data = reporter.generate_radar_data(cv_results, trend_analysis)
            
            # 5. 生成报告
            report_md = reporter.generate_markdown(self.all_results)
            
            # 6. 保存报告
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_query = self.query.replace("/", "_").replace("\\", "_")[:30]
            
            report_path = OUTPUT_DIR / f"综合热点分析_{safe_query}_{timestamp}.md"
            report_path.write_text(report_md, encoding="utf-8")
            
            # 同时保存 JSON 原始数据
            json_path = OUTPUT_DIR / f"综合热点数据_{safe_query}_{timestamp}.json"
            json_data = {
                "query": self.query,
                "timestamp": timestamp,
                "total_results": len(self.all_results),
                "cross_validation": cv_results,
                "trend_analysis": {
                    "source_distribution": trend_analysis.get("source_distribution", {}),
                    "type_distribution": trend_analysis.get("type_distribution", {}),
                    "credibility_distribution": trend_analysis.get("credibility_distribution", {}),
                    "top_hot": [r.get("title", "") for r in trend_analysis.get("top_hot", [])],
                    "cross_platform_hotspots": {k: {"sources": v["sources"], "count": v["count"]} 
                                             for k, v in trend_analysis.get("cross_platform_hotspots", {}).items()}
                },
                "radar_data": radar_data,
                "all_results": self.all_results
            }
            
            json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
            
            # 7. 上传到知识库（如果RAG服务器运行中）
            try:
                upload_url = "http://localhost:8765/api/upload"
                upload_path = Path(str(report_path))
                files = {"file": (upload_path.name, f, "text/markdown")}
                resp = requests.post(upload_url, files=files, timeout=30)
                if resp.status_code == 200:
                    print(f"\n[SUCCESS] 报告已自动上传到知识库：{upload_path}")
                else:
                    print(f"\n[WARNING] 报告入库失败：{resp.text}")
            except Exception as e:
                print(f"\n[WARNING] 上传报告到知识库失败：{e}")
            
            return {
                "report_path": str(report_path),
                "json_path": str(json_path),
                "radar_data": radar_data,
                "cv_results": cv_results,
                "trend_analysis": trend_analysis,
                "all_results": self.all_results
            }
            
        except Exception as e:
            print(f"[ERROR] 分析过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return None

# ==================== 多话题分析器 ====================

def analyze_all_topics():
    """分析所有预设话题"""
    print("=" * 60)
    print("[START] 综合热点分析系统 v2.0 - 全话题模式")
    print("=" * 60)
    
    all_reports = []
    
    for topic in DEFAULT_TOPICS:
        print(f"\n{'#' * 60}")
        print(f"📌 分析话题: {topic}")
        print(f"{'#' * 60}")
        
        analyzer = ComprehensiveHotspotAnalyzer(topic)
        result = analyzer.analyze()
        
        if result:
            all_reports.append(result)
        
        time.sleep(1)  # 避免请求过快
    
    # 生成汇总报告
    if all_reports:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_lines = [
            "# [REPORT] 综合热点分析汇总报告",
            "",
            f"> 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"> 分析话题: {', '.join(DEFAULT_TOPICS)}",
            f"> 数据源: Tavily, Jina, TrendRadar, 政策, RSS, GitHub",
            "",
            "---",
            "",
        ]
        
        for report in all_reports:
            query = report.get("report_path", "").split("_")[2] if "_" in report.get("report_path", "") else "unknown"
            summary_lines.append(f"## {query}")
            summary_lines.append(f"- 报告路径: {report.get('report_path', '')}")
            summary_lines.append(f"- 数据路径: {report.get('json_path', '')}")
            summary_lines.append("")
        
        summary_path = OUTPUT_DIR / f"综合热点汇总_{timestamp}.md"
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        
        print(f"\n[SUCCESS] 汇总报告已生成: {summary_path}")
        
        # 上传到知识库
        try:
            upload_url = "http://localhost:8765/api/upload"
            upload_path = Path(str(summary_path))
            files = {"file": (upload_path.name, f, "text/markdown")}
            resp = requests.post(upload_url, files=files, timeout=30)
            if resp.status_code == 200:
                print(f"\n[SUCCESS] 汇总报告已上传到知识库")
            else:
                print(f"\n[WARNING] 汇总报告上传失败: {resp.text}")
        except Exception as e:
            print(f"\n[WARNING] 汇总报告上传失败: {e}")

# ==================== 主函数 ====================

def main():
    """主函数"""
    fix_encoding()
    
    # 声明全局变量
    global OUTPUT_DIR, OUTPUT_DIR_GLOBAL
    OUTPUT_DIR_GLOBAL = OUTPUT_DIR
    
    parser = argparse.ArgumentParser(
        description="综合热点采集与分析系统 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python comprehensive_hotspot_analyzer.py "AI视频生成"
  python comprehensive_hotspot_analyzer.py "大语言模型" --max-workers 3
  python comprehensive_hotspot_analyzer.py --all-topics
"""
    )
    
    parser.add_argument("query", nargs="?", default=None, help="搜索关键词（不指定则使用 --all-topics）")
    parser.add_argument("--all-topics", action="store_true", help="分析所有预设话题")
    parser.add_argument("--max-workers", type=int, default=5, help="最大并发采集器数量（默认5）")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON数据")
    
    args = parser.parse_args()
    
    # Fix encoding
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    
    if args.output_dir:
        OUTPUT_DIR = Path(args.output_dir)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR_GLOBAL = OUTPUT_DIR
    
    if args.all_topics:
        # 分析所有预设话题
        analyze_all_topics()
    else:
        # 分析单个查询
        analyzer = ComprehensiveHotspotAnalyzer(args.query)
        result = analyzer.analyze()
        
        if result:
            print(f"\n[FILE] 报告路径: {result['report_path']}")
            print(f"[REPORT] JSON数据: {result['json_path']}")
            
            if not args.json_only:
                # 打印雷达图数据
                print(f"\n[TARGET] 雷达图数据:")
                for dim, score in result['radar_data'].items():
                    print(f"   {dim}: {score}/100")
        else:
            parser.print_help()


if __name__ == "__main__":
    main()