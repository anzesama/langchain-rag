# -*- coding: utf-8 -*-
"""
Tavily 联网搜索工具

用法：
    python tavily_search.py "AI 视频生成工具"
    python tavily_search.py "AI 视频生成工具" --max-results 5
    python tavily_search.py "AI 视频生成工具" --output-file results.md
"""
import os
import sys
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================

# Tavily API Key（硬编码，和 Agnes API Key 保持一致处理方式）
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "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")

OUTPUT_DIR = Path(__file__).parent.parent / "documents" / "_tavily_search"

# ==================== 搜索函数 ====================

def tavily_search(query: str, max_results: int = 5, search_depth: str = "basic") -> dict:
    """
    调用 Tavily API 进行搜索
    
    Args:
        query: 搜索关键词
        max_results: 返回结果数（1-10）
        search_depth: "basic" 或 "advanced"
        
    Returns:
        API 返回的原始 JSON
    """
    url = "https://api.tavily.com/search"
    
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": min(max_results, 10),
        "search_depth": search_depth,
        "include_answer": True,
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if r.status_code == 401:
            print("[ERROR] API Key 无效，请检查 TAVILY_API_KEY 环境变量")
        elif r.status_code == 429:
            print("[ERROR] 请求频率超限，请稍后再试")
        else:
            print("[ERROR] HTTP {}: {}".format(r.status_code, r.text))
        return None
    except Exception as e:
        print("[ERROR] 搜索失败: {}".format(e))
        return None


def format_results(data: dict, query: str) -> str:
    """
    将搜索结果格式化为 Markdown
    
    Returns:
        Markdown 字符串
    """
    if not data:
        return "# 搜索结果：{}\n\n> 搜索失败，无数据\n".format(query)
    
    answer = data.get("answer", "")
    results = data.get("results", [])
    
    lines = []
    lines.append("# 搜索结果：{}".format(query))
    lines.append("")
    lines.append("> 搜索时间：{}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))
    
    if answer:
        lines.append("")
        lines.append("## AI 摘要")
        lines.append(answer)
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 搜索结果详情")
    lines.append("")
    
    for i, r in enumerate(results, 1):
        lines.append("### {}. [{}]({})".format(i, r.get("title", "无标题"), r.get("url", "")))
        lines.append("")
        if r.get("content"):
            lines.append(r["content"])
        lines.append("")
        lines.append("- 相关性: {:.2f}".format(r.get("score", 0)))
        lines.append("- 发布时间: {}".format(r.get("published_date", "未知")))
        lines.append("")
    
    return "\n".join(lines)


def save_results(query: str, data: dict, output_file: str = None):
    """
    保存搜索结果到文件
    
    Args:
        query: 搜索关键词
        data: API 返回数据
        output_file: 输出文件路径（可选）
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if output_file:
        filepath = Path(output_file)
    else:
        safe_query = query.replace("/", "_").replace("\\", "_")[:50]
        filepath = OUTPUT_DIR / "{}_{}.md".format(safe_query, datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    content = format_results(data, query)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("[OK] 结果已保存: {}".format(filepath))
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Tavily 联网搜索工具")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--max-results", type=int, default=5, help="返回结果数（1-10，默认5）")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="basic", help="搜索深度")
    parser.add_argument("--output-file", help="输出文件路径（默认自动生成）")
    parser.add_argument("--json", action="store_true", help="直接输出 JSON 原始数据")
    
    args = parser.parse_args()
    
    # 检查 API Key
    if not TAVILY_API_KEY:
        print("[ERROR] 未设置 TAVILY_API_KEY 环境变量")
        print("请执行: set TAVILY_API_KEY=你的Key")
        sys.exit(1)
    
    # 执行搜索
    print("[INFO] 搜索: {}".format(args.query))
    print("[INFO] 深度: {}, 最大结果: {}".format(args.depth, args.max_results))
    
    data = tavily_search(args.query, args.max_results, args.depth)
    
    if not data:
        print("[FAIL] 搜索失败")
        sys.exit(1)
    
    if args.json:
        # 直接输出 JSON
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        # 保存到文件并打印预览
        filepath = save_results(args.query, data, args.output_file)
        print("\n--- 预览 ---")
        content = format_results(data, args.query)
        print(content[:1500])
        if len(content) > 1500:
            print("\n... (更多内容已保存到文件)")


if __name__ == "__main__":
    # Fix GBK encoding issue on Windows console
    if sys.platform == "win32":
        import io
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    main()
