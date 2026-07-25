#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 Wiki CLI 修复
"""

import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_get_pending_review():
    """测试 get_pending_review 方法"""
    print("=" * 60)
    print("测试 1: get_pending_review 方法")
    print("=" * 60)

    try:
        from rag_core.wiki_db import WikiDB

        # 创建实例
        wiki_db = WikiDB(db_path='storage/knowledge_base.db')
        wiki_db.init_db()

        # 获取待审核实体
        candidates = wiki_db.get_pending_review(limit=5)

        print(f"\n[OK] 获取到 {len(candidates)} 个待审核实体\n")

        if candidates:
            print("前 3 个实体:")
            for i, candidate in enumerate(candidates[:3], 1):
                print(f"\n{i}. {candidate['name']} ({candidate['type']})")
                if candidate.get('source_chapter'):
                    print(f"   来源: {candidate['source_chapter']}")
                if candidate.get('properties'):
                    print(f"   属性: {candidate['properties']}")

        wiki_db.close()
        return True

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_wiki_cli_syntax():
    """测试 Wiki CLI 语法"""
    print("\n" + "=" * 60)
    print("测试 2: Wiki CLI 语法检查")
    print("=" * 60)

    try:
        import py_compile
        py_compile.compile('scripts/wiki_cli.py', doraise=True)
        print("\n[OK] Wiki CLI 语法检查通过")
        return True
    except Exception as e:
        print(f"\n[ERROR] 语法检查失败: {e}")
        return False


def main():
    """主测试函数"""
    print("\nWiki CLI 修复测试\n")

    results = []

    # 测试 1: get_pending_review 方法
    results.append(("get_pending_review 方法", test_get_pending_review()))

    # 测试 2: Wiki CLI 语法
    results.append(("Wiki CLI 语法", test_wiki_cli_syntax()))

    # 显示结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("[OK] 所有测试通过")
        return 0
    else:
        print("[ERROR] 部分测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
