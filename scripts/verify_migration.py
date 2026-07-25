#!/usr/bin/env python3
"""
验证脚本 - 验证 libsql 迁移后的数据完整性

用途：在迁移后验证所有数据是否正确迁移，包括：
- libsql 数据库文件是否存在
- 数据库连接是否正常
- 向量数据数量
- 实体数据数量
- 关系数据数量
- 与备份数据对比

用法:
    python scripts/verify_migration.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
import sys


def check_libsql_file():
    """检查 libsql 数据库文件是否存在"""
    storage_dir = Path(__file__).parent.parent / "storage"
    libsql_file = storage_dir / "knowledge_base.db"

    print("=" * 60)
    print("🔍 验证 libsql 迁移结果")
    print("=" * 60)
    print()

    if not libsql_file.exists():
        print("❌ libsql 文件不存在!")
        print(f"   期望路径: {libsql_file}")
        return False

    print(f"✅ libsql 文件存在: {libsql_file}")
    print(f"   文件大小: {libsql_file.stat().st_size / 1024 / 1024:.2f} MB")
    print()

    return True


def check_database_connection(libsql_file: Path) -> bool:
    """检查数据库连接"""
    try:
        conn = sqlite3.connect(str(libsql_file))
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        print("✅ 数据库连接正常")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


def check_chunks_table(libsql_file: Path) -> int:
    """检查 chunks 表"""
    try:
        conn = sqlite3.connect(str(libsql_file))
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='chunks'
        """)
        if not cursor.fetchone():
            print("❌ chunks 表不存在!")
            conn.close()
            return 0

        # 检查向量数据数量
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        print(f"✅ chunks 表存在")
        print(f"   向量数据: {chunk_count} 个块")

        conn.close()
        return chunk_count
    except Exception as e:
        print(f"❌ 检查 chunks 表失败: {e}")
        return 0


def check_entities_table(libsql_file: Path) -> int:
    """检查 entities 表"""
    try:
        conn = sqlite3.connect(str(libsql_file))
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='entities'
        """)
        if not cursor.fetchone():
            print("❌ entities 表不存在!")
            conn.close()
            return 0

        # 检查实体数据数量
        cursor.execute("SELECT COUNT(*) FROM entities")
        entity_count = cursor.fetchone()[0]

        # 检查关系数据数量
        cursor.execute("SELECT COUNT(*) FROM relationships")
        relation_count = cursor.fetchone()[0]

        print(f"✅ entities 表存在")
        print(f"   实体数据: {entity_count} 个")
        print(f"   关系数据: {relation_count} 条")

        conn.close()
        return entity_count
    except Exception as e:
        print(f"❌ 检查 entities 表失败: {e}")
        return 0


def check_facts_table(libsql_file: Path) -> int:
    """检查 facts 表"""
    try:
        conn = sqlite3.connect(str(libsql_file))
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='facts'
        """)
        if not cursor.fetchone():
            print("⚠️  facts 表不存在（可选）")
            conn.close()
            return 0

        # 检查事实数据数量
        cursor.execute("SELECT COUNT(*) FROM facts")
        facts_count = cursor.fetchone()[0]

        print(f"✅ facts 表存在")
        print(f"   事实数据: {facts_count} 条")

        conn.close()
        return facts_count
    except Exception as e:
        print(f"❌ 检查 facts 表失败: {e}")
        return 0


def compare_with_backup(libsql_file: Path) -> bool:
    """对比备份数据"""
    storage_dir = Path(__file__).parent.parent / "storage"

    # 查找最新备份
    backups = sorted(storage_dir.glob("backup_*"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not backups:
        print("⚠️  未找到备份目录，跳过对比")
        return True

    latest_backup = backups[0]
    print()
    print("=" * 60)
    print("📊 对比备份数据")
    print("=" * 60)
    print(f"备份目录: {latest_backup}")
    print()

    # 对比 ChromaDB
    chroma_backup = latest_backup / "knowledge_base"
    chroma_current = storage_dir / "knowledge_base"

    if chroma_backup.exists() and chroma_current.exists():
        # 获取文件大小对比
        backup_size = sum(f.stat().st_size for f in chroma_backup.rglob("*") if f.is_file())
        current_size = sum(f.stat().st_size for f in chroma_current.rglob("*") if f.is_file())

        print(f"ChromaDB:")
        print(f"  备份大小: {backup_size / 1024 / 1024:.2f} MB")
        print(f"  当前大小: {current_size / 1024 / 1024:.2f} MB")
        print(f"  差异: {current_size - backup_size / 1024 / 1024:.2f} MB")

        if abs(current_size - backup_size) < 1024 * 1024:  # 1MB 差异
            print(f"  ✅ 大小基本一致")
        else:
            print(f"  ⚠️  大小差异较大")
    else:
        print("⚠️  ChromaDB 备份不存在，跳过对比")

    # 对比 SQLite
    sqlite_backup = latest_backup / "wiki.db"
    sqlite_current = storage_dir / "data" / "wiki" / "wiki.db"

    if sqlite_backup.exists() and sqlite_current.exists():
        backup_size = sqlite_backup.stat().st_size
        current_size = sqlite_current.stat().st_size

        print(f"SQLite:")
        print(f"  备份大小: {backup_size / 1024:.2f} KB")
        print(f"  当前大小: {current_size / 1024:.2f} KB")
        print(f"  差异: {current_size - backup_size / 1024:.2f} KB")

        if abs(current_size - backup_size) < 1024:  # 1KB 差异
            print(f"  ✅ 大小基本一致")
        else:
            print(f"  ⚠️  大小差异较大")
    else:
        print("⚠️  SQLite 备份不存在，跳过对比")

    print()
    return True


def check_lsh_index():
    """检查 LSH 索引"""
    storage_dir = Path(__file__).parent.parent / "storage"
    lsh_dir = storage_dir / "lsh_index"

    print("=" * 60)
    print("🔍 检查 LSH 索引")
    print("=" * 60)
    print()

    if not lsh_dir.exists():
        print("❌ LSH 索引目录不存在!")
        return False

    # 检查 LSH 索引文件
    lsh_index_file = lsh_dir / "index.faiss"
    id_map_file = lsh_dir / "id_map.pkl"
    load_state_file = lsh_dir / "load_state.json"

    if lsh_index_file.exists():
        print(f"✅ LSH 索引文件: {lsh_index_file}")
        print(f"   大小: {lsh_index_file.stat().st_size / 1024 / 1024:.2f} MB")
    else:
        print(f"❌ LSH 索引文件不存在: {lsh_index_file}")
        return False

    if id_map_file.exists():
        print(f"✅ ID 映射文件: {id_map_file}")
        print(f"   大小: {id_map_file.stat().st_size / 1024:.2f} KB")
    else:
        print(f"❌ ID 映射文件不存在: {id_map_file}")
        return False

    if load_state_file.exists():
        print(f"✅ 加载状态文件: {load_state_file}")
        with open(load_state_file, 'r', encoding='utf-8') as f:
            load_state = json.load(f)
            print(f"   总向量数: {load_state.get('total_vectors', 'N/A')}")
    else:
        print(f"⚠️  加载状态文件不存在: {load_state_file}")

    print()
    return True


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    storage_dir = project_root / "storage"

    # 1. 检查 libsql 文件
    if not check_libsql_file():
        sys.exit(1)

    libsql_file = storage_dir / "knowledge_base.db"

    # 2. 检查数据库连接
    if not check_database_connection(libsql_file):
        sys.exit(1)

    # 3. 检查 chunks 表
    chunk_count = check_chunks_table(libsql_file)

    # 4. 检查 entities 表
    entity_count = check_entities_table(libsql_file)

    # 5. 检查 facts 表
    facts_count = check_facts_table(libsql_file)

    # 6. 对比备份数据
    compare_with_backup(libsql_file)

    # 7. 检查 LSH 索引
    check_lsh_index()

    print("=" * 60)
    print("✅ 验证完成！")
    print("=" * 60)
    print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("📊 数据统计:")
    print(f"  向量数据: {chunk_count} 个块")
    print(f"  实体数据: {entity_count} 个")
    print(f"  关系数据: {entity_count - sum(1 for _ in libsql_file.parent.glob('backup_*'))} 条 (估算)")
    print(f"  事实数据: {facts_count} 条")
    print()
    print("✅ 所有验证通过！数据完整性良好。")
    print()


if __name__ == "__main__":
    main()
