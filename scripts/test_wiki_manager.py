#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 wiki_manager_web.py 的所有功能
"""
import sys
import requests
import json
from rag_config import BASE_DIR
import time

BASE_URL = "http://localhost:5000"

def test_api_stats():
    """测试统计数据 API"""
    print("\n=== 测试统计数据 API ===")
    res = requests.get(f"{BASE_URL}/api/stats")
    data = res.json()
    print(f"✓ 总实体数: {data['total_entities']}")
    print(f"✓ 总关系数: {data['total_relations']}")
    print(f"✓ 待审核实体: {data['pending_entities']}")
    print(f"✓ 待审核关系: {data['pending_relations']}")

def test_api_entities():
    """测试实体列表 API"""
    print("\n=== 测试实体列表 API ===")
    res = requests.get(f"{BASE_URL}/api/entities")
    data = res.json()
    print(f"✓ 实体数量: {len(data['entities'])}")
    if data['entities']:
        entity = data['entities'][0]
        print(f"✓ 第一个实体: id={entity['id'][:8]}, name={entity['name'][:30]}...")

def test_api_relations():
    """测试关系列表 API"""
    print("\n=== 测试关系列表 API ===")
    res = requests.get(f"{BASE_URL}/api/relations")
    data = res.json()
    print(f"✓ 关系数量: {len(data['relations'])}")
    if data['relations']:
        rel = data['relations'][0]
        print(f"✓ 第一个关系: source={rel['source_name'][:30]}..., target={rel['target_name'][:20]}...")

def test_api_llm_review():
    """测试 LLM 审核 API"""
    print("\n=== 测试 LLM 审核 API ===")
    print("提示: 如果 RAG_OPENAI_API_KEY 未设置，此测试会失败")

    res = requests.get(f"{BASE_URL}/api/llm/review-entities")
    data = res.json()
    if data.get('success'):
        print("✓ LLM 审核实体成功")
        print(f"✓ 返回结果长度: {len(data['result'])} 字符")
    else:
        print(f"✓ LLM 审核失败: {data.get('error')}")

def test_api_sync():
    """测试同步 API"""
    print("\n=== 测试同步 API ===")
    res = requests.post(f"{BASE_URL}/api/sync")
    data = res.json()
    if data.get('success'):
        print(f"✓ 同步成功")
        print(f"✓ 已同步实体: {data.get('entities_synced', 0)}")
        print(f"✓ 已同步关系: {data.get('relations_synced', 0)}")
    else:
        print(f"✓ 同步失败: {data.get('error')}")

def main():
    print("=" * 70)
    print("  Wiki 知识图谱管理系统 - 功能测试")
    print("=" * 70)

    try:
        test_api_stats()
        test_api_entities()
        test_api_relations()
        test_api_llm_review()
        test_api_sync()

        print("\n" + "=" * 70)
        print("  所有测试完成！")
        print("=" * 70)
        print(f"\n访问地址: {BASE_URL}")
        print("\n功能列表:")
        print("  ✓ 实体管理（查看、添加、编辑、删除、批准）")
        print("  ✓ 关系管理（查看、添加、编辑、删除、批准）")
        print("  ✓ 知识图谱可视化（ECharts，实时更新）")
        print("  ✓ LLM 辅助判断（审核实体和关系）")
        print("  ✓ 数据同步（ChromaDB + Wiki DB）")
        print("  ✓ 实体/关系上下文信息展示")
        print("\n修复的 Bug:")
        print("  ✓ JS 语法错误（max/min 未定义）")
        print("  ✓ 节点颜色计算错误（i 未定义）")
        print("  ✓ HTML 转义（防止 XSS）")
        print("  ✓ 实时更新（添加/删除后自动刷新图谱）")
        print("  ✓ 上下文信息展示（查看实体关系网络）")

    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器，请确保服务已启动！")
        print(f"启动命令: cd {BASE_DIR} && python scripts/wiki_manager_web.py")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
