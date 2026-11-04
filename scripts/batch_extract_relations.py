"""批量关系抽取 CLI（薄封装）

⚠️ 所有逻辑都在 rag_core/relation_extractor.py —— 本文件只做参数解析与打印。
   历史上此处曾有两份重复逻辑（其一被误置在 finally: 中，导致 LLM 跑两遍），已收敛。

用法:
    python scripts/batch_extract_relations.py --source README.md
    python scripts/batch_extract_relations.py --all
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.relation_extractor import extract_all_sources, extract_relations_for_source


def main():
    parser = argparse.ArgumentParser(description="批量关系抽取")
    parser.add_argument("--source", type=str, help="指定来源文件（chunks.source）")
    parser.add_argument("--all", action="store_true", help="处理所有来源")
    parser.add_argument("--limit", type=int, help="限制处理的来源数量")
    parser.add_argument("--domain", type=str, default=None, help="领域类型（默认读 DOMAIN_TYPE）")

    args = parser.parse_args()

    if not args.source and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.source:
        results = {args.source: extract_relations_for_source(args.source, args.domain)}
    else:
        results = extract_all_sources(args.domain, args.limit)

    print("\n" + "=" * 60)
    print("批量关系抽取汇总")
    print("=" * 60)
    for source, res in results.items():
        line = (
            f"{source}: 实体 {res.get('entities_count', 0)}"
            f" / 抽取 {res.get('relations_extracted', 0)}"
            f" / 入库 {res.get('relations_imported', 0)}"
        )
        if res.get("skipped"):
            line += " / 已跳过(SKIP_LLM=1)"
        if res.get("error"):
            line += f" / 错误: {res['error']}"
        print(line)
    print("=" * 60)


if __name__ == "__main__":
    main()
