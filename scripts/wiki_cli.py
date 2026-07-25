"""
Wiki CLI 工具 - 用于管理 Wiki 数据库

功能：
- 查看实体列表
- 查看关系列表
- 添加实体
- 添加关系
- 审核候选实体
- 导出/导入数据
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_db import get_wiki_db
from rag_core.wiki_router import get_wiki_router
from rag_core.wiki_updater import WikiUpdater


def cmd_list_entities(args):
    """列出所有实体"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    entities = wiki_db.get_all_entities()

    print(f"\n总实体数: {len(entities)}\n")

    # 按类型分组
    by_type = {}
    for entity in entities:
        entity_type = entity['type']
        if entity_type not in by_type:
            by_type[entity_type] = []
        by_type[entity_type].append(entity)

    # 显示统计
    for entity_type, entity_list in sorted(by_type.items()):
        print(f"\n【{entity_type}】({len(entity_list)} 个)")
        print("-" * 60)
        for entity in entity_list:
            print(f"  {entity['name']}")
            if entity['aliases']:
                print(f"    别名: {', '.join(entity['aliases'])}")
            if entity['source_chapter']:
                print(f"    来源: {entity['source_chapter']}")

    wiki_db.close()


def cmd_list_relations(args):
    """列出所有关系"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    stats = wiki_db.get_stats()

    print(f"\n总关系数: {stats['total_relationships']}\n")

    # 按类型分组
    by_type = {}
    relations = []
    for entity_id in wiki_db.get_all_entities():
        entity_id = entity_id['id']
        rels = wiki_db.get_relations(entity_id)
        relations.extend(rels)

    for rel in relations:
        rel_type = rel['rel_type']
        if rel_type not in by_type:
            by_type[rel_type] = []
        by_type[rel_type].append(rel)

    # 显示统计
    for rel_type, rel_list in sorted(by_type.items()):
        print(f"\n【{rel_type}】({len(rel_list)} 个)")
        print("-" * 60)
        for rel in rel_list:
            print(f"  {rel['source']} -{rel['rel_type']}-> {rel['target']}")

    wiki_db.close()


def cmd_add_entity(args):
    """添加实体"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    entity_type = args.type
    properties = {}

    # 解析属性
    if args.properties:
        for prop in args.properties:
            if '=' in prop:
                key, value = prop.split('=', 1)
                properties[key.strip()] = value.strip()

    # 添加实体
    success = wiki_db.add_entity(
        name=args.name,
        entity_type=entity_type,
        properties=properties if properties else None
    )

    if success:
        print(f"\n[OK] 实体已添加: {args.name}")
    else:
        print(f"\n[ERROR] 实体添加失败: {args.name}")

    wiki_db.close()


def cmd_add_relationship(args):
    """添加关系"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    success = wiki_db.add_relationship(
        source_name=args.source,
        target_name=args.target,
        rel_type=args.rel_type
    )

    if success:
        print(f"\n[OK] 关系已添加: {args.source} -{args.rel_type}-> {args.target}")
    else:
        print(f"\n[ERROR] 关系添加失败")

    wiki_db.close()


def cmd_review(args):
    """审核候选实体"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 从数据库获取待审核实体
    candidates = wiki_db.get_pending_review(limit=100)

    if not candidates:
        print("\n[INFO] 没有待审核的实体\n")
        wiki_db.close()
        return

    print(f"\n待审核实体: {len(candidates)} 个\n")
    print("=" * 60)

    for i, candidate in enumerate(candidates, 1):
        print(f"\n{i}. {candidate['name']} ({candidate['type']})")
        if candidate.get('source_chapter'):
            print(f"   来源: {candidate['source_chapter']}")
        if candidate.get('properties'):
            print(f"   属性: {candidate['properties']}")

    print("\n" + "=" * 60)
    print("\n使用以下命令批准/拒绝:")
    print(f"  python wiki_cli.py approve 1 2 3")
    wiki_db.close()


def cmd_approve(args):
    """批准实体/待审核项"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 如果指定了 review_id，直接批准
    if hasattr(args, 'review_id') and args.review_id:
        success = wiki_db.approve_review(args.review_id, reviewed_by="cli")
        if success:
            print(f"\n[OK] 待审核项已批准: {args.review_id}")
        else:
            print(f"\n[ERROR] 批准失败: {args.review_id}")
        wiki_db.close()
        return

    # 否则使用旧逻辑（索引方式）
    updater = WikiUpdater()

    # 从数据库获取待审核实体
    candidates = wiki_db.get_pending_review(limit=100)

    # 审核批准（按索引批准）
    if len(candidates) < len(args.indices):
        print(f"\n[ERROR] 待审核实体数量不足: 需要 {len(args.indices)} 个, 只有 {len(candidates)} 个")
        wiki_db.close()
        return

    approved = [candidates[i]['name'] for i in args.indices]
    rejected = []

    stats = updater.review_candidates(candidates, approved=approved, rejected=rejected)

    print(f"\n[OK] 审核完成")
    print(f"  批准: {stats['approved']}")
    print(f"  拒绝: {stats['rejected']}")
    print(f"  跳过: {stats['skipped']}")

    wiki_db.close()


def cmd_correct(args):
    """修正实体属性"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 解析属性
    properties = {}
    if args.property:
        for prop in args.property:
            if '=' in prop:
                key, value = prop.split('=', 1)
                properties[key.strip()] = value.strip()

    # 执行修正
    success = wiki_db.correct_entity_property(
        entity_name=args.name,
        property_name=args.property_name,
        new_value=properties.get(args.property_name) if properties else None,
        change_reason=args.reason,
        changed_by="cli"
    )

    if success:
        print(f"\n[OK] 实体属性已修正: {args.name}.{args.property_name}")
        if args.reason:
            print(f"  原因: {args.reason}")
    else:
        print(f"\n[ERROR] 修正失败: {args.name}")

    wiki_db.close()


def cmd_history(args):
    """查看实体历史版本"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    history = wiki_db.get_entity_history(args.name, limit=args.limit)

    if not history:
        print(f"\n[INFO] 未找到历史记录: {args.name}")
        wiki_db.close()
        return

    print(f"\n【{args.name}】历史版本 (共 {len(history)} 个)")
    print("=" * 60)

    # 将 reversed 结果转换回列表
    reversed_history = list(reversed(history))
    for i, h in enumerate(reversed_history, 1):
        print(f"\n版本 {i} (ID: {h['id']})")
        print(f"  时间: {h['created_at']}")
        if h['changed_by']:
            print(f"  操作人: {h['changed_by']}")
        if h['change_reason']:
            print(f"  原因: {h['change_reason']}")
        if h['old_properties']:
            print(f"  旧属性: {h['old_properties']}")
        if h['new_properties']:
            print(f"  新属性: {h['new_properties']}")
        if h['is_correction']:
            print(f"  类型: 修正")

    wiki_db.close()


def cmd_rollback(args):
    """回滚实体到指定版本"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    success = wiki_db.rollback_entity_version(args.name, args.version_id)

    if success:
        print(f"\n[OK] 实体已回滚: {args.name} (版本 {args.version_id})")
    else:
        print(f"\n[ERROR] 回滚失败: {args.name} (版本 {args.version_id})")

    wiki_db.close()


def cmd_review_pending(args):
    """查看待审核项（增强版）"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 获取待审核项
    reviews = wiki_db.get_pending_reviews(
        review_status='pending',
        limit=args.limit,
        entity_type=args.entity_type
    )

    if not reviews:
        print("\n[INFO] 没有待审核的项\n")
        wiki_db.close()
        return

    print(f"\n待审核项: {len(reviews)} 个\n")
    print("=" * 70)

    for i, review in enumerate(reviews, 1):
        print(f"\n{i}. [ID: {review['id']}] {review['entity_name']} ({review['entity_type']})")
        if review.get('relation_type'):
            print(f"   关系类型: {review['relation_type']}")
        if review.get('source_text'):
            print(f"   原文: {review['source_text'][:50]}...")
        if review.get('source_chapter'):
            print(f"   来源: {review['source_chapter']}")
        if review.get('confidence'):
            print(f"   置信度: {review['confidence']}")
        if review.get('properties'):
            print(f"   属性: {review['properties']}")

    print("\n" + "=" * 70)
    print("\n使用以下命令批准/拒绝:")
    print(f"  python wiki_cli.py approve --review-id {reviews[0]['id']}")
    print(f"  python wiki_cli.py reject --review-id {reviews[0]['id']} --reason "
          f"'拒绝原因'")

    wiki_db.close()


def cmd_reject(args):
    """拒绝待审核项"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    if not hasattr(args, 'review_id') or not args.review_id:
        print("\n[ERROR] 请指定 --review-id 参数")
        wiki_db.close()
        return

    success = wiki_db.reject_review(
        review_id=args.review_id,
        reject_reason=args.reason,
        reviewed_by="cli"
    )

    if success:
        print(f"\n[OK] 待审核项已拒绝: {args.review_id}")
        if args.reason:
            print(f"  原因: {args.reason}")
    else:
        print(f"\n[ERROR] 拒绝失败: {args.review_id}")

    wiki_db.close()


def cmd_reason(args):
    """触发推理引擎"""
    updater = WikiUpdater()

    # 属性推导模式
    if args.apply_properties:
        from rag_core.wiki_reasoner import WikiReasoner
        reasoner = WikiReasoner()

        if args.entity:
            # 为指定实体推导属性
            print(f"\n=== 为实体 {args.entity} 推导属性 ===")
            derived = reasoner.derive_entity_properties(args.entity)

            if not derived:
                print(f"[INFO] 没有为 {args.entity} 推导出属性")
            else:
                print(f"\n推导出 {len(derived)} 个属性:")
                for item in derived:
                    print(f"  - 规则: {item['rule_name']}")
                    print(f"    置信度: {item['confidence']}")
                    print(f"    推导属性: {item['inferred_properties']}")
                    print(f"    原因: {item['reason']}")

                # 应用属性
                print(f"\n=== 应用推导属性 ===")
                applied = reasoner.apply_derived_properties(args.entity)
                print(f"应用了 {applied} 个属性")

                # 验证结果
                entity = updater.wiki_db.get_entity(args.entity)
                if entity:
                    props = entity['properties']
                    print(f"\n{args.entity} 最终属性数: {len(props)}")
                    print(f"新增属性: {len([k for k in props.keys() if k in ['能力', '掌握境界', '流派特点', '流派优势']])}")
        else:
            # 为所有实体应用推导属性
            print(f"\n=== 为所有实体应用推导属性 ===")
            stats = reasoner.apply_all_derived_properties()
            print(f"\n统计:")
            print(f"  总实体数: {stats['total_entities']}")
            print(f"  有推导的实体数: {stats['entities_with_derivations']}")
            print(f"  应用的属性总数: {stats['total_properties_applied']}")

    elif args.save:
        # 保存推导结果到待审核队列（关系推导）
        saved_count = updater.save_deductions()
        print(f"\n[OK] 已保存 {saved_count} 条推导结果到待审核队列")
    else:
        # 仅显示推理摘要（关系推导）
        summary = updater.trigger_reasoning()

        print(f"\n[INFO] 推理引擎执行完成")
        print("=" * 70)
        print(f"总推导数: {summary['total_deductions']}")
        print("\n规则执行摘要:")
        for rule_name, rule_data in summary['rules'].items():
            print(f"  - {rule_name}")
            print(f"    推导数: {rule_data['count']}")
            print(f"    平均置信度: {rule_data['average_confidence']:.2f}")
        print("=" * 70)

        if args.show_results:
            print("\n详细推导结果:")
            from rag_core.wiki_reasoner import WikiReasoner
            reasoner = WikiReasoner()
            deduced = reasoner.analyze_all_entities()

            for i, item in enumerate(deduced, 1):
                print(f"\n{i}. [{item['rule_name']}]")
                print(f"   实体: {item['source_entity']}")
                print(f"   推导关系: {item['deduced_rel_type']}")
                print(f"   置信度: {item['confidence']:.2f}")
                print(f"   原因: {item['deduced_properties']['reason']}")
                print(f"   来源关系数: {item['source_relations']}")


def cmd_export(args):
    """导出数据"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    if args.entities:
        entities = wiki_db.get_all_entities()
        output = {"entities": entities}

    elif args.relationships:
        stats = wiki_db.get_stats()
        output = {"statistics": stats}

    else:
        entities = wiki_db.get_all_entities()
        output = {"entities": entities}

    # 保存到文件
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        import json
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 数据已导出到: {output_file}")
    print(f"  记录数: {len(output.get('entities', []))}")

    wiki_db.close()


def cmd_import(args):
    """导入数据"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    input_file = Path(args.input)

    if not input_file.exists():
        print(f"\n[ERROR] 文件不存在: {input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        import json
        data = json.load(f)

    added = 0
    for entity in data.get('entities', []):
        try:
            wiki_db.add_entity(
                name=entity['name'],
                entity_type=entity['type'],
                properties=entity.get('properties'),
                source_chapter=entity.get('source_chapter')
            )
            added += 1
        except Exception as e:
            print(f"  [ERROR] 添加实体失败 {entity['name']}: {e}")

    print(f"\n[OK] 导入完成")
    print(f"  添加实体: {added}")

    wiki_db.close()


def cmd_search(args):
    """搜索实体"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    entities = wiki_db.get_entities_by_type(args.type)

    print(f"\n【{args.type}】共 {len(entities)} 个\n")
    print("-" * 60)

    for entity in entities:
        print(f"  {entity['name']}")
        if entity['aliases']:
            print(f"    别名: {', '.join(entity['aliases'])}")

    wiki_db.close()


def cmd_stats(args):
    """显示统计信息"""
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    stats = wiki_db.get_stats()

    print("\n" + "=" * 60)
    print("Wiki 数据库统计")
    print("=" * 60)
    print(f"\n总实体数: {stats['total_entities']}")
    print(f"总关系数: {stats['total_relationships']}")

    print("\n实体类型分布:")
    for entity_type, count in sorted(stats['entities'].items()):
        print(f"  {entity_type}: {count}")

    print("\n关系类型分布:")
    for rel_type, count in sorted(stats['relationships'].items()):
        print(f"  {rel_type}: {count}")

    wiki_db.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Wiki CLI 工具 - 管理 Wiki 数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有实体
  python wiki_cli.py list entities

  # 添加实体
  python wiki_cli.py add entity --name="方源" --type="人物" --properties="资质=甲等9成"

  # 添加关系
  python wiki_cli.py add relationship --source="方源" --target="力道" --rel_type="主修"

  # 显示统计
  python wiki_cli.py stats

  # 导出数据
  python wiki_cli.py export --entities --output=data/wiki/export.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # list
    parser_list = subparsers.add_parser('list', help='列出数据')
    parser_list.add_argument('target', choices=['entities', 'relations'], help='列出类型')

    # add entity
    parser_add = subparsers.add_parser('add', help='添加数据')
    parser_add_entity = parser_add.add_subparsers(dest='kind')

    # entity 子命令
    parser_entity = parser_add_entity.add_parser('entity')
    parser_entity.add_argument('--name', required=True, help='实体名称')
    parser_entity.add_argument('--type', required=True, help='实体类型')
    parser_entity.add_argument('--properties', nargs='*', help='属性键值对（如：资质=甲等9成）')

    # relationship 子命令
    parser_relationship = parser_add_entity.add_parser('relationship')
    parser_relationship.add_argument('--source', required=True, help='源实体')
    parser_relationship.add_argument('--target', required=True, help='目标实体')
    parser_relationship.add_argument('--rel-type', required=True, help='关系类型')

    # review
    parser_review = subparsers.add_parser('review', help='审核候选')

    # approve
    parser_approve = subparsers.add_parser('approve', help='批准实体')
    parser_approve.add_argument('indices', type=int, nargs='*', help='批准的索引（旧方式）')
    parser_approve.add_argument('--review-id', type=int, help='待审核项ID（新方式）')

    # export
    parser_export = subparsers.add_parser('export', help='导出数据')
    parser_export.add_argument('--entities', action='store_true', help='导出实体')
    parser_export.add_argument('--relationships', action='store_true', help='导出关系')
    parser_export.add_argument('--output', default='wiki_export.json', help='输出文件')

    # import
    parser_import = subparsers.add_parser('import', help='导入数据')
    parser_import.add_argument('--input', required=True, help='输入文件')

    # search
    parser_search = subparsers.add_parser('search', help='搜索实体')
    parser_search.add_argument('--type', required=True, help='实体类型')

    # stats
    subparsers.add_parser('stats', help='显示统计')

    # correct
    parser_correct = subparsers.add_parser('correct', help='修正实体属性')
    parser_correct.add_argument('name', help='实体名称')
    parser_correct.add_argument('property_name', help='属性名')
    parser_correct.add_argument('--property', nargs='*', help='属性键值对（如：资质=甲等9成）')
    parser_correct.add_argument('--reason', help='修正原因')

    # history
    parser_history = subparsers.add_parser('history', help='查看历史版本')
    parser_history.add_argument('name', help='实体名称')
    parser_history.add_argument('--limit', type=int, default=10, help='最大数量')

    # rollback
    parser_rollback = subparsers.add_parser('rollback', help='回滚版本')
    parser_rollback.add_argument('name', help='实体名称')
    parser_rollback.add_argument('version_id', type=int, help='历史版本ID')

    # review-pending
    parser_review_pending = subparsers.add_parser('review-pending', help='查看待审核项（增强版）')
    parser_review_pending.add_argument('--limit', type=int, default=20, help='最大数量')
    parser_review_pending.add_argument('--entity-type', help='实体类型过滤')

    # reject
    parser_reject = subparsers.add_parser('reject', help='拒绝待审核项')
    parser_reject.add_argument('--review-id', type=int, required=True, help='待审核项ID')
    parser_reject.add_argument('--reason', help='拒绝原因')

    # reason
    parser_reason = subparsers.add_parser('reason', help='触发推理引擎')
    parser_reason.add_argument('--save', action='store_true', help='保存推导结果到待审核队列')
    parser_reason.add_argument('--show-results', action='store_true', help='显示详细推导结果')
    parser_reason.add_argument('--apply-properties', action='store_true', help='应用推导的属性到实体')
    parser_reason.add_argument('--entity', type=str, help='指定实体名称（仅用于属性推导）')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行命令
    command_map = {
        'list': cmd_list_entities,
        'list_relations': cmd_list_relations,
        'add_entity': cmd_add_entity,
        'add_relationship': cmd_add_relationship,
        'review': cmd_review,
        'approve': cmd_approve,
        'correct': cmd_correct,
        'history': cmd_history,
        'rollback': cmd_rollback,
        'review-pending': cmd_review_pending,
        'reject': cmd_reject,
        'review_pending': cmd_review_pending,
        'reason': cmd_reason,
        'export': cmd_export,
        'import': cmd_import,
        'search': cmd_search,
        'stats': cmd_stats,
    }

    # 直接使用命令名
    command = args.command

    if command in command_map:
        command_map[command](args)
    else:
        print(f"[ERROR] 未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
