"""
统一文档导入 CLI — 一条命令完成 chunks + entities + relationships 全链路

用法:
    python scripts/doc_importer.py <path>                    # 增量导入
    python scripts/doc_importer.py <path> --overwrite        # 覆盖导入
    python scripts/doc_importer.py <path> --llm              # 启用 LLM 辅助关系提取
    python scripts/doc_importer.py <path> --steps 1,2         # 只跑 Step 1+2
    python scripts/doc_importer.py <path> --batch             # 强制使用分批模式（>10MB自动）
    python scripts/doc_importer.py <path> --resume            # 断点续传向量生成

文件 <10MB：使用 UnifiedImporter 的单次模式
文件 >10MB：自动切换到 large_file_importer（分批次向量生成 + 断点续传）
"""
import argparse
import os
import sys
from pathlib import Path

# 加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from rag_config import logger
from rag_core.unified_importer import UnifiedImporter


SUPPORTED_EXTENSIONS = {'.md', '.txt', '.pdf'}


def scan_files(path: str) -> list:
    """扫描指定路径下的所有支持文件，自动识别目录/单文件"""
    p = Path(path)
    if p.is_file():
        return [p] if p.suffix in SUPPORTED_EXTENSIONS else []
    if p.is_dir():
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(p.rglob(f'*{ext}'))
        return sorted(files)
    return []


def main():
    parser = argparse.ArgumentParser(
        description='统一文档导入 — 自动完成 chunks + entities + relationships 入 库',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/doc_importer.py documents/AAAMLP-CN/
  python scripts/doc_importer.py documents/notes.md --llm
  python scripts/doc_importer.py documents/蛊真人_精校版.txt  # >10MB自动分批
  python scripts/doc_importer.py data/ --overwrite --steps 1,2
"""
    )
    parser.add_argument('path', help='文件或目录路径')
    parser.add_argument('--llm', action='store_true', default=False,
                        help='使用 LLM API 辅助关系提取（默认关闭，用 jieba TF-IDF）')
    parser.add_argument('--overwrite', action='store_true', default=False,
                        help='覆盖已导入的文件（默认增量跳过）')
    parser.add_argument('--steps', type=str, default='1,2,3,4',
                        help='启用处理步骤 (1=chunks, 2=entities, 3=relations, 4=LLM关系精炼)')
    parser.add_argument('--batch', action='store_true', default=False,
                        help='强制使用大文件分批模式')
    parser.add_argument('--resume', action='store_true', default=False,
                        help='断点续传（仅大文件模式有效）')
    args = parser.parse_args()

    # 设置 LLM 开关
    if args.llm:
        os.environ['SKIP_LLM'] = '0'
    else:
        os.environ['SKIP_LLM'] = '1'

    target = args.path
    p = Path(target)

    # 大文件自动切换逻辑
    if p.is_file():
        file_size = p.stat().st_size
        if file_size > 10 * 1024 * 1024 or args.batch:
            print(f"📦 文件 {file_size / (1024*1024):.1f}MB，自动切换到大文件分批模式")
            from scripts.large_file_importer import generate_embeddings, split_and_insert_chunks, detect_encoding
            import sqlite3
            import subprocess
            # 直接调用 large_file_importer 脚本
            cmd = [sys.executable, str(Path(__file__).parent / 'large_file_importer.py')]
            if p.exists():
                cmd.append(str(p))
            if args.overwrite:
                # large_file_importer 默认覆盖
                pass
            if args.resume:
                cmd.append('--embed-only')
            print(f"  执行: {' '.join(cmd)}")
            subprocess.run(cmd)
            sys.exit(0)

    files = scan_files(target)
    if not files:
        print(f'No supported files found: {target}')
        sys.exit(1)

    enabled_steps = {int(s) for s in args.steps.split(',') if s.strip().isdigit()}
    importer = UnifiedImporter()

    total = {'files': 0, 'chunks': 0, 'entities': 0, 'relations': 0, 'skipped': 0}
    for i, fpath in enumerate(files):
        source_name = str(fpath.relative_to(Path(target)) if Path(target).is_dir() else fpath.name) if isinstance(fpath, Path) else str(fpath.name)
        print(f"[{i+1}/{len(files)}] {source_name}")

        # 读取
        try:
            with open(fpath, 'r', encoding='gbk', errors='ignore') as f:
                text = f.read()
        except Exception as e:
            print(f"  FAILED: {e}")
            continue

        if not text or not text.strip():
            print(f"  SKIP: no content")
            continue

        # 增量判断
        if not args.overwrite and importer._is_already_imported(source_name):
            print(f"  SKIP: already imported")
            total['skipped'] += 1
            continue

        # Step 1: chunks
        chunks = None
        if 1 in enabled_steps:
            documents = importer._split_text(text, source_name)
            chunks = importer._import_chunks(documents, source_name, overwrite=args.overwrite)

        # Step 2+3+4: entities + relations
        if 2 in enabled_steps or 3 in enabled_steps or 4 in enabled_steps:
            stats = importer._import_entities_and_relations(text, source_name)
            total['entities'] += stats.get('entities_added', 0)
            total['relations'] += stats.get('relations_added', 0)

        total['files'] += 1
        total['chunks'] += len(chunks) if chunks else 0

    print(f"\n{'='*40}")
    print(f"Complete. {total['files']} files, {total['chunks']} chunks, {total['entities']} entities, {total['relations']} relations, {total['skipped']} skipped")
    print(f"{'='*40}")


if __name__ == '__main__':
    main()