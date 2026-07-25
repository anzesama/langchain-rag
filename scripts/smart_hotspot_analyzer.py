#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能热点采集与分析系统 v3.0

核心改进：
1. 先启动知识库服务，再进行搜索
2. 知识库搜索 + 实时热点采集双通道
3. 交叉验证 + 趋势分析 + 雷达图

用法：
    python smart_hotspot_analyzer.py "今日热点"
    python smart_hotspot_analyzer.py "AI视频生成" --no-rag
    python smart_hotspot_analyzer.py --all-topics
"""

import sys
import os
import json
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 修复 GBK 编码问题
if sys.platform == "win32":
    import io
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ==================== 配置 ====================

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "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")

OUTPUT_DIR = Path(__file__).parent / "documents" / "综合热点分析"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# RAG 服务配置
PROJECT_ROOT = Path(__file__).parent
RAG_SERVER_DIR = PROJECT_ROOT / "langchain-rag"
RAG_SERVER_PY = RAG_SERVER_DIR / "rag_server.py"
RAG_SERVER_HOST = "127.0.0.1"
RAG_SERVER_PORT = 8765  # 与 rag_config.py 保持一致
RAG_SERVER_URL = f"http://{RAG_SERVER_HOST}:{RAG_SERVER_PORT}"

# trend_env 配置
TREND_ENV_PYTHON = r"D:\class\miniconda3\envs\trend_env\python.exe"
TREND_COLLECTOR = PROJECT_ROOT / "trend-radar" / "collector.py"

# 预设话题
DEFAULT_TOPICS = [
    "AI视频生成", "大语言模型", "自动驾驶", "量子计算",
    "机器人", "新能源", "芯片半导体", "生物科技",
]


# ==================== 知识库服务管理 ====================

class RAGServiceManager:
    """知识库服务管理器 — 确保服务运行后再搜索"""
    
    def __init__(self):
        self.process = None
        self.is_running = False
    
    def start_if_not_running(self):
        """
        启动 RAG 服务（如果未运行）
        
        正确流程：
        1. 检查端口是否被占用
        2. 如果被占用 → 服务已在运行
        3. 如果未被占用 → 启动服务
        4. 等待服务就绪
        5. 返回服务状态
        """
        print("\n🔧 检查知识库服务状态...")
        
        # 1. 检查端口是否被占用
        if self._is_port_in_use():
            print(f"  ✅ 知识库服务已在运行（端口 {RAG_SERVER_PORT}）")
            self.is_running = True
            return True
        
        # 2. 服务未运行，启动它
        print(f"  🚀 启动知识库服务...")
        
        # 检查 ml_env 是否存在
        ml_env_python = r"D:\class\miniconda3\envs\ml_env\python.exe"
        if not Path(ml_env_python).exists():
            print(f"  ❌ ml_env 环境不存在: {ml_env_python}")
            return False
        
        # 启动服务（后台进程）
        try:
            self.process = subprocess.Popen(
                [ml_env_python, str(RAG_SERVER_PY)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(RAG_SERVER_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            print(f"  📡 服务进程已启动（PID: {self.process.pid}）")
        except Exception as e:
            print(f"  ❌ 启动失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 3. 等待服务就绪（最多等待 15 秒）
        print(f"  ⏳ 等待服务就绪...")
        for i in range(30):  # 30 * 0.5s = 15s
            time.sleep(0.5)
            if self._is_port_in_use():
                print(f"  ✅ 知识库服务已就绪（等待 {i*0.5:.1f}s）")
                self.is_running = True
                return True
            if i % 6 == 0:  # 每 3 秒打印一次
                print(f"     等待中... ({i*0.5:.1f}s)")
        
        # 4. 超时检查
        if self.process and self.process.poll() is not None:
            stdout, stderr = self.process.communicate()
            print(f"  ❌ 服务进程已退出")
            print(f"     stdout: {stdout.decode('utf-8', errors='replace')[:200]}")
            print(f"     stderr: {stderr.decode('utf-8', errors='replace')[:200]}")
            return False
        
        print(f"  ⚠️  服务启动超时（15s），可能仍在加载中")
        return False
    
    def stop(self):
        """停止服务（可选）"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
            print(f"  🛑 知识库服务已停止")
    
    def _is_port_in_use(self):
        """检查端口是否被占用"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((RAG_SERVER_HOST, RAG_SERVER_PORT))
        sock.close()
        return result == 0
    
    def search_knowledge_base(self, query, top_k=5):
        """
        搜索知识库（服务必须已运行）
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            
        Returns:
            dict: {"query": ..., "answer": ..., "sources": [...]}
        """
        if not self.is_running:
            print(f"  ❌ 知识库服务未运行，无法搜索")
            return None
        
        try:
            url = f"{RAG_SERVER_URL}/api/search"
            response = requests.post(
                url,
                json={"query": query, "top_k": top_k},
                timeout=60  # 知识库首次搜索可能需要加载模型，增加超时
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"  ❌ 无法连接到知识库服务: {RAG_SERVER_URL}")
            return None
        except requests.exceptions.Timeout:
            print(f"  ⚠️  知识库服务请求超时（可能是首次加载模型）")
            return None
        except Exception as e:
            print(f"  ❌ 知识库搜索失败: {e}")
            return None


# ==================== 数据源采集器 ====================

class SourceCollector:
    """数据源采集基类"""
    
    def __init__(self, name):
        self.name = name
        self.results = []
        self.error = None
        self.fetch_time = 0


class TavilyCollector(SourceCollector):
    """Tavily 搜索引擎采集器"""
    
    def __init__(self):
        super().__init__("Tavily搜索")
    
    def search(self, query, max_results=10):
        start_time = time.time()
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": min(max_results, 10),
                "search_depth": "basic",
                "include_answer": True,
            }
            r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            for item in data.get("results", []):
                self.results.append({
                    "source": self.name,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0),
                    "published_date": item.get("published_date", ""),
                    "type": "tavily",
                })
            
            self.fetch_time = time.time() - start_time
            return len(self.results)
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  ❌ {self.name}: {e}")
            return 0


class TrendRadarCollector(SourceCollector):
    """TrendRadar 多平台热点采集器"""
    
    def __init__(self):
        super().__init__("TrendRadar")
    
    def fetch(self):
        start_time = time.time()
        try:
            if not Path(TREND_ENV_PYTHON).exists():
                print(f"  ⚠️  TrendRadar: trend_env 不存在")
                self.fetch_time = time.time() - start_time
                return 0
            
            if not TREND_COLLECTOR.exists():
                print(f"  ⚠️  TrendRadar: collector.py 不存在")
                self.fetch_time = time.time() - start_time
                return 0
            
            result = subprocess.run(
                [TREND_ENV_PYTHON, str(TREND_COLLECTOR)],
                capture_output=True, text=True, timeout=60,
                encoding='utf-8', errors='replace'
            )
            
            output = (result.stdout or '') + (result.stderr or '')
            import re
            count_match = re.search(r'共获取到\s+(\d+)\s+条', output)
            news_count = int(count_match.group(1)) if count_match else 0
            
            if news_count > 0:
                print(f"  ✅ TrendRadar: 获取 {news_count} 条")
                # 从最新报告解析
                trend_docs_dir = TREND_COLLECTOR.parent / "documents" / "趋势情报"
                if trend_docs_dir.exists():
                    latest_report = max(
                        (f for f in trend_docs_dir.glob("趋势日报*.md") if f.is_file()),
                        key=lambda f: f.stat().st_mtime,
                        default=None
                    )
                    if latest_report:
                        report_content = latest_report.read_text(encoding="utf-8")
                        lines = report_content.split('\n')
                        current_item = {}
                        in_items = False
                        for line in lines:
                            if line.startswith("## 🔥 热点新闻"):
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
                                    "type": "trendradar_general",
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
                        if current_item:
                            self.results.append(current_item)
            
            self.fetch_time = time.time() - start_time
            return news_count
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  ❌ {self.name}: {e}")
            return 0


class PolicyCollector(SourceCollector):
    """政策数据采集器"""
    
    def __init__(self):
        super().__init__("政策数据")
    
    def fetch(self, keyword="", days=7, limit=20):
        start_time = time.time()
        try:
            mcp_script = Path(__file__).parent / "trend-radar" / "node_modules" / "@iflow-mcp" / "guangxiangdebizi-central-policy-mcp" / "build" / "index.js"
            
            if not mcp_script.exists():
                print(f"  ⚠️  Policy MCP 未安装")
                self.fetch_time = time.time() - start_time
                return 0
            
            node_path = "node"
            if not self._check_node(node_path):
                conda_node = r"D:\class\miniconda3\envs\trend_env\node.exe"
                if Path(conda_node).exists():
                    node_path = conda_node
            
            import subprocess as sp
            import json as _json
            from datetime import timedelta
            
            search_keyword = keyword or "国务院"
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            init_payload = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "smart-analyzer", "version": "3.0"}}
            }
            
            proc = sp.Popen(
                [node_path, str(mcp_script)],
                stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE,
                encoding="utf-8", errors="replace"
            )
            
            proc.stdin.write(_json.dumps(init_payload) + "\n")
            proc.stdin.flush()
            init_resp = proc.stdout.readline()
            
            if "result" not in init_resp:
                proc.terminate()
                self.fetch_time = time.time() - start_time
                return 0
            
            call_payload = {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {
                    "name": "get_latest_policies",
                    "arguments": {"keyword": search_keyword, "startdate": start_date,
                                 "enddate": end_date, "limit": min(limit, 100)}
                }
            }
            
            proc.stdin.write(_json.dumps(call_payload) + "\n")
            proc.stdin.flush()
            call_resp = proc.stdout.readline()
            proc.stdin.close()
            proc.wait(timeout=5)
            
            if not call_resp or "result" not in call_resp:
                self.fetch_time = time.time() - start_time
                return 0
            
            data = _json.loads(call_resp)
            content = data.get("result", {}).get("content", [])
            
            for item in content:
                text_data = item.get("text", "{}") if isinstance(item, dict) else str(item)
                try:
                    pdata = _json.loads(text_data)
                except:
                    continue
                
                for p in pdata.get("items", [])[:limit]:
                    title = p.get("title", "")
                    url = p.get("url", "")
                    if not title or not url:
                        continue
                    
                    self.results.append({
                        "source": self.name,
                        "title": title,
                        "url": url,
                        "content": p.get("summary", ""),
                        "score": 0,
                        "published_date": p.get("date", ""),
                        "type": "policy",
                        "level": p.get("level", ""),
                        "issuing_agency": p.get("issuing_agency", ""),
                    })
            
            self.fetch_time = time.time() - start_time
            return len(self.results)
        except Exception as e:
            self.error = str(e)
            self.fetch_time = time.time() - start_time
            print(f"  ❌ {self.name}: {e}")
            return 0
    
    def _check_node(self, node_path):
        try:
            import subprocess
            result = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False


# ==================== 主控制器 ====================

class SmartHotspotAnalyzer:
    """智能热点分析器 — 先启动知识库，再采集"""
    
    def __init__(self, query, use_rag=True):
        self.query = query
        self.use_rag = use_rag
        self.rag_manager = RAGServiceManager() if use_rag else None
        self.collectors = []
        self.all_results = []
        self.rag_results = None
    
    def run(self):
        """
        执行完整流程：
        1. 启动知识库服务（如果启用）
        2. 搜索知识库（如果启用）
        3. 并行采集实时数据
        4. 交叉验证 + 趋势分析
        5. 生成报告
        """
        print("=" * 60)
        print("🚀 智能热点采集与分析系统 v3.0")
        print(f"   查询: {self.query}")
        print(f"   知识库搜索: {'✅ 启用' if self.use_rag else '❌ 禁用'}")
        print("=" * 60)
        
        # ========== 第 1 步：启动知识库服务 ==========
        if self.use_rag and self.rag_manager:
            print("\n📚 第 1 步：启动知识库服务...")
            rag_ready = self.rag_manager.start_if_not_running()
            
            if rag_ready:
                # ========== 第 2 步：搜索知识库 ==========
                print(f"\n📚 第 2 步：搜索知识库 '{self.query}'...")
                self.rag_results = self.rag_manager.search_knowledge_base(self.query, top_k=5)
                if self.rag_results:
                    print(f"  ✅ 知识库返回 {len(self.rag_results.get('sources', []))} 条结果")
                else:
                    print(f"  ⚠️  知识库搜索无结果或失败")
            else:
                print(f"  ⚠️  知识库服务启动失败，跳过知识库搜索")
                self.rag_results = None
        else:
            print(f"\n⏭️  跳过知识库搜索")
            self.rag_results = None
        
        # ========== 第 3 步：并行采集实时数据 ==========
        print("\n📡 第 3 步：并行采集实时数据...")
        self._init_collectors()
        self._collect_all()
        
        # ========== 第 4 步：合并 + 去重 ==========
        print("\n🔗 第 4 步：合并数据源...")
        self.all_results = self._merge_and_deduplicate()
        print(f"  ✅ 合并后共 {len(self.all_results)} 条数据")
        
        # ========== 第 5 步：交叉验证 + 趋势分析 ==========
        print("\n📊 第 5 步：交叉验证与趋势分析...")
        analysis = self._perform_analysis()
        
        # ========== 第 6 步：生成报告 ==========
        print("\n📝 第 6 步：生成报告...")
        report = self._generate_report(analysis)
        
        # ========== 完成 ==========
        print(f"\n{'=' * 60}")
        print(f"✅ 分析完成！")
        print(f"   知识库结果: {len(self.rag_results.get('sources', [])) if self.rag_results else 0} 条")
        print(f"   实时采集: {len(self.all_results)} 条")
        print(f"   报告: {report['report_path']}")
        print(f"   数据: {report['json_path']}")
        print(f"{'=' * 60}")
        
        return report
    
    def _init_collectors(self):
        """初始化所有采集器"""
        self.collectors = [
            TavilyCollector(),
            TrendRadarCollector(),
            PolicyCollector(),
        ]
        print(f"  ✅ 已初始化 {len(self.collectors)} 个采集器")
    
    def _collect_all(self):
        """并行采集所有数据源"""
        total = 0
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            
            for collector in self.collectors:
                if isinstance(collector, TavilyCollector):
                    future = executor.submit(collector.search, self.query, 10)
                elif isinstance(collector, TrendRadarCollector):
                    future = executor.submit(collector.fetch)
                elif isinstance(collector, PolicyCollector):
                    future = executor.submit(collector.fetch, "", 7, 20)
                else:
                    future = executor.submit(collector.fetch if hasattr(collector, 'fetch') else collector.search, self.query, 10)
                futures[future] = collector
            
            for future in as_completed(futures):
                collector = futures[future]
                try:
                    count = future.result()
                    total += count
                except Exception as e:
                    print(f"  ❌ {collector.name}: {e}")
        
        print(f"  ✅ 采集完成，共 {total} 条")
    
    def _merge_and_deduplicate(self):
        """合并所有采集器结果并去重"""
        merged = []
        seen_urls = set()
        
        for collector in self.collectors:
            for item in collector.results:
                url = item.get("url", "")
                if url:
                    norm_url = url.lower().strip()
                    for param in ['?', '&', 'utm_']:
                        norm_url = norm_url.split(param)[0]
                    if norm_url in seen_urls:
                        continue
                    seen_urls.add(norm_url)
                merged.append(item)
        
        return merged
    
    def _perform_analysis(self):
        """执行交叉验证和趋势分析"""
        source_dist = Counter(r.get("source", "unknown") for r in self.all_results)
        type_dist = Counter(r.get("type", "unknown") for r in self.all_results)
        
        scored = sorted(self.all_results, key=lambda x: x.get("score", 0), reverse=True)[:20]
        
        return {
            "source_distribution": dict(source_dist),
            "type_distribution": dict(type_dist),
            "top_hot": scored,
            "total_count": len(self.all_results),
        }
    
    def _generate_report(self, analysis):
        """生成报告"""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        safe_query = self.query.replace("/", "_").replace("\\", "_")[:30]
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # Markdown 报告
        lines = [
            f"# 📊 智能热点分析报告",
            "",
            f"> **查询主题**: {self.query}",
            f"> **分析时间**: {now_str}",
            f"> 知识库: {'✅ 已搜索' if self.rag_results else '❌ 未搜索'}",
            f"> 实时采集: {analysis['total_count']} 条",
            "",
            "---",
            "",
        ]
        
        # 知识库结果
        if self.rag_results:
            lines.append("## 📚 知识库搜索结果")
            lines.append("")
            if self.rag_results.get("answer"):
                lines.append(f"> {self.rag_results['answer']}")
                lines.append("")
            for i, src in enumerate(self.rag_results.get("sources", []), 1):
                lines.append(f"### {i}. {src.get('source', '未知')}")
                lines.append(f"- 内容: {src.get('content', '')[:200]}")
                lines.append(f"- 相似度: {src.get('score', 0):.2f}")
                lines.append("")
        
        # 数据来源分布
        lines.append("## 📡 数据来源分布")
        lines.append("")
        source_dist_counter = Counter(analysis["source_distribution"])
        for source, count in source_dist_counter.most_common():
            bar = "█" * count
            lines.append(f"- **{source}**: {count} 条 {bar}")
        lines.append("")
        
        # Top 热门
        lines.append("## 🔥 Top 20 热门内容")
        lines.append("")
        for i, item in enumerate(analysis["top_hot"][:20], 1):
            lines.append(f"### {i}. {item.get('title', '无标题')[:60]}")
            lines.append(f"- **来源**: {item.get('source', '未知')}")
            lines.append(f"- **类型**: {item.get('type', '未知')}")
            if item.get('url'):
                lines.append(f"- **链接**: {item['url']}")
            if item.get('content'):
                lines.append(f"- **摘要**: {item['content'][:150]}...")
            lines.append("")
        
        lines.extend([
            "---",
            "",
            f"*本报告由智能热点采集与分析系统 v3.0 自动生成*",
            f"*采集时间: {now_str}*",
            ""
        ])
        
        report_md = "\n".join(lines)
        
        # 保存文件
        report_path = OUTPUT_DIR / f"智能热点分析_{safe_query}_{timestamp}.md"
        report_path.write_text(report_md, encoding="utf-8")
        
        # JSON 数据
        json_data = {
            "query": self.query,
            "timestamp": timestamp,
            "rag_results": self.rag_results,
            "realtime_count": analysis["total_count"],
            "source_distribution": analysis["source_distribution"],
            "top_hot": [r.get("title", "") for r in analysis["top_hot"]],
            "results": self.all_results,
        }
        json_path = OUTPUT_DIR / f"智能热点数据_{safe_query}_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        return {
            "report_path": str(report_path),
            "json_path": str(json_path),
        }


# ==================== CLI 入口 ====================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="智能热点采集与分析系统 v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python smart_hotspot_analyzer.py "今日热点"
  python smart_hotspot_analyzer.py "AI视频生成" --no-rag
  python smart_hotspot_analyzer.py --all-topics
        """
    )
    
    parser.add_argument("query", nargs="?", default=None, help="搜索关键词")
    parser.add_argument("--all-topics", action="store_true", help="分析所有预设话题")
    parser.add_argument("--no-rag", action="store_true", help="禁用知识库搜索")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    
    args = parser.parse_args()
    
    if args.all_topics:
        for topic in DEFAULT_TOPICS:
            print(f"\n{'#' * 60}")
            print(f"📌 分析话题: {topic}")
            print(f"{'#' * 60}")
            
            use_rag = not args.no_rag
            analyzer = SmartHotspotAnalyzer(topic, use_rag=use_rag)
            analyzer.run()
            time.sleep(1)
    elif args.query:
        use_rag = not args.no_rag
        analyzer = SmartHotspotAnalyzer(args.query, use_rag=use_rag)
        analyzer.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
