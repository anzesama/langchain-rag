#!/usr/bin/env python3
"""
回滚脚本 - 从 libsql 迁移回滚到 ChromaDB 和 SQLite

用途：在 libsql 迁移后发现问题，快速回滚到迁移前的状态

用法:
    python scripts/rollback_libsql.py
"""

import os
import shutil
from pathlib import Path
from datetime import datetime


def restore_directory(src: Path, dst: Path) -> bool:
    """恢复目录

    Args:
        src: 源目录（备份目录）
        dst: 目标目录（当前目录）

    Returns:
        是否成功
    """
    try:
        # 如果目标已存在，先删除
        if dst.exists():
            shutil.rmtree(dst)

        # 从备份恢复
        shutil.copytree(src, dst)
        print(f"✅ 已恢复: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"❌ 恢复失败: {src} -> {dst}, 错误: {e}")
        return False


def restore_file(src: Path, dst: Path) -> bool:
    """恢复文件

    Args:
        src: 源文件（备份文件）
        dst: 目标文件（当前文件）

    Returns:
        是否成功
    """
    try:
        # 如果目标已存在，先删除
        if dst.exists():
            dst.unlink()

        # 从备份恢复
        shutil.copy2(src, dst)
        print(f"✅ 已恢复: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"❌ 恢复失败: {src} -> {dst}, 错误: {e}")
        return False


def cleanup_backup(backup_dir: Path, keep_count: int = 3) -> bool:
    """清理旧备份，只保留最新的 keep_count 个

    Args:
        backup_dir: 备份目录
        keep_count: 保留数量

    Returns:
        是否成功
    """
    try:
        if not backup_dir.exists():
            print(f"⚠️  备份目录不存在: {backup_dir}")
            return True

        # 获取所有备份目录
        backups = sorted(backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)

        # 删除旧的备份
        for old_backup in backups[keep_count:]:
            print(f"🗑️  删除旧备份: {old_backup}")
            shutil.rmtree(old_backup)

        print(f"✅ 已清理旧备份（保留 {keep_count} 个最新）")
        return True
    except Exception as e:
        print(f"❌ 清理备份失败: {e}")
        return False


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    storage_dir = project_root / "storage"
    data_dir = project_root / "data" / "wiki"

    print("=" * 60)
    print("🔄 开始回滚（libsql -> ChromaDB + SQLite）")
    print("=" * 60)
    print()

    # 查找最新的备份目录
    backups = sorted(storage_dir.glob("backup_*"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not backups:
        print("❌ 未找到备份目录！")
        print()
        print("请先运行备份脚本:")
        print("  python scripts/backup_before_migration.py")
        return

    latest_backup = backups[0]
    print(f"📦 找到最新备份: {latest_backup}")
    print()

    # 1. 恢复 ChromaDB
    chroma_src = latest_backup / "knowledge_base"
    chroma_dst = storage_dir / "knowledge_base"
    print("📦 恢复 ChromaDB...")
    restore_directory(chroma_src, chroma_dst)

    # 2. 恢复 SQLite
    sqlite_src = latest_backup / "wiki.db"
    sqlite_dst = data_dir / "wiki.db"
    print("📦 恢复 SQLite...")
    restore_file(sqlite_src, sqlite_dst)

    # 3. 恢复 LSH 索引
    lsh_src = latest_backup / "lsh_index"
    lsh_dst = storage_dir / "lsh_index"
    print("📦 恢复 LSH 索引...")
    restore_directory(lsh_src, lsh_dst)

    # 4. 恢复全局计数器
    global_counter_src = storage_dir / "global_counter.json.backup"
    global_counter_dst = storage_dir / "global_counter.json"
    print("📦 恢复全局计数器...")
    restore_file(global_counter_src, global_counter_dst)

    print()
    print("=" * 60)
    print("✅ 回滚完成！")
    print("=" * 60)
    print(f"备份目录: {latest_backup}")
    print(f"备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("📋 已恢复:")
    print(f"  - ChromaDB: {chroma_dst}")
    print(f"  - SQLite:   {sqlite_dst}")
    print(f"  - LSH 索引: {lsh_dst}")
    print(f"  - 全局计数器: {global_counter_dst}")
    print()
    print("⚠️  警告: 请手动验证数据完整性！")
    print("⚠️  建议运行验证脚本:")
    print("    python scripts/verify_migration.py")
    print()


if __name__ == "__main__":
    # 确认操作
    print("⚠️  警告: 此操作将覆盖当前数据！")
    confirm = input("确定要继续吗？(yes/no): ")

    if confirm.lower() not in ["yes", "y"]:
        print("❌ 已取消回滚操作")
        return

    main()
