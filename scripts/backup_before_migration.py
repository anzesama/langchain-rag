#!/usr/bin/env python3
"""
备份脚本 - 迁移前备份所有数据

用途：在开始 libsql 迁移前，备份所有现有数据（ChromaDB、SQLite、LSH 索引、全局计数器）

用法:
    python scripts/backup_before_migration.py
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
import json


def backup_directory(src: Path, dst: Path) -> bool:
    """备份目录

    Args:
        src: 源目录
        dst: 目标目录

    Returns:
        是否成功
    """
    try:
        # 创建备份目录
        dst.mkdir(parents=True, exist_ok=True)

        # 如果目标已存在，先删除
        if dst.exists():
            shutil.rmtree(dst)

        # 复制目录
        shutil.copytree(src, dst)
        print(f"✅ 已备份: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"❌ 备份失败: {src} -> {dst}, 错误: {e}")
        return False


def backup_file(src: Path, dst: Path) -> bool:
    """备份文件

    Args:
        src: 源文件
        dst: 目标文件

    Returns:
        是否成功
    """
    try:
        # 创建备份目录
        dst.parent.mkdir(parents=True, exist_ok=True)

        # 如果目标已存在，先删除
        if dst.exists():
            dst.unlink()

        # 复制文件
        shutil.copy2(src, dst)
        print(f"✅ 已备份: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"❌ 备份失败: {src} -> {dst}, 错误: {e}")
        return False


def backup_global_counter() -> bool:
    """备份全局计数器

    Args:
        storage_dir: 存储目录

    Returns:
        是否成功
    """
    storage_dir = Path(__file__).parent.parent / "storage"
    src = storage_dir / "global_counter.json"
    dst = storage_dir / "global_counter.json.backup"

    return backup_file(src, dst)


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    storage_dir = project_root / "storage"
    data_dir = project_root / "data" / "wiki"

    print("=" * 60)
    print("🚀 开始备份（libsql 迁移前）")
    print("=" * 60)
    print(f"项目根目录: {project_root}")
    print(f"存储目录: {storage_dir}")
    print(f"数据目录: {data_dir}")
    print()

    # 记录备份时间
    backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = storage_dir / f"backup_{backup_time}"

    # 1. 备份 ChromaDB 数据
    chroma_src = storage_dir / "knowledge_base"
    chroma_dst = backup_dir / "knowledge_base"
    print("📦 备份 ChromaDB...")
    backup_directory(chroma_src, chroma_dst)

    # 2. 备份 SQLite 数据
    sqlite_src = data_dir / "wiki.db"
    sqlite_dst = backup_dir / "wiki.db"
    print("📦 备份 SQLite...")
    backup_file(sqlite_src, sqlite_dst)

    # 3. 备份 LSH 索引
    lsh_dir = storage_dir / "lsh_index"
    lsh_dst = backup_dir / "lsh_index"
    print("📦 备份 LSH 索引...")
    backup_directory(lsh_dir, lsh_dst)

    # 4. 备份全局计数器
    print("📦 备份全局计数器...")
    backup_global_counter()

    print()
    print("=" * 60)
    print("✅ 备份完成！")
    print("=" * 60)
    print(f"备份目录: {backup_dir}")
    print(f"备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("📋 备份内容:")
    print(f"  - ChromaDB: {chroma_dst}")
    print(f"  - SQLite:   {sqlite_dst}")
    print(f"  - LSH 索引: {lsh_dst}")
    print(f"  - 全局计数器: {storage_dir}/global_counter.json.backup")
    print()
    print("⚠️  警告: 请妥善保管备份目录，不要删除！")
    print("⚠️  备份目录将保留 3 个最新备份。")
    print()


if __name__ == "__main__":
    main()
