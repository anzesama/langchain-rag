"""
Wiki 实体清理脚本
"""
import sys
sys.path.insert(0, 'D:/class/project-config/langchain-rag')

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from rag_core import wiki_db
from rag_config import RAG_AGNES_API_KEY, RAG_AGNES_API_BASE
import json

def clean_entities():
    """清理无效实体"""
    db = wiki_db.WikiDB('D:/class/project-config/langchain-rag/data/wiki/wiki.db')
    db.init_db()

    entities = db.get_entities()
    print(f'总实体数: {len(entities)}')

    # 1. 删除单个字符实体
    single_chars = [e['id'] for e in entities if len(e['name']) == 1]
    print(f'单个字符实体: {len(single_chars)} 个')

    # 2. 删除无属性实体
    no_props = [e['id'] for e in entities if not e['properties'] or e['properties'] == {}]
    print(f'无属性实体: {len(no_props)} 个')

    # 3. 删除完整句子/段落实体（长度 > 50）
    long_texts = [e['id'] for e in entities if len(e['name']) > 50]
    print(f'长文本实体（>50字）: {len(long_texts)} 个')

    # 统计"未分类"实体
    unclassified = [e for e in entities if e['type'] == '未分类']
    print(f'未分类实体: {len(unclassified)} 个')

    # 显示一些示例
    if no_props:
        print(f'\n无属性实体示例（前5个）:')
        for e in no_props[:5]:
            print(f'  - {e[\"name\"]} (类型: {e[\"type\"]})')

    # 确认删除
    confirm = input(f'\n确认删除上述实体吗？(yes/no): ')
    if confirm.lower() != 'yes':
        print('已取消')
        return

    # 执行删除
    deleted_count = 0
    for entity_id in single_chars + no_props + long_texts:
        try:
            db.delete_entity(entity_id)
            deleted_count += 1
        except Exception as e:
            print(f'删除失败 {entity_id}: {e}')

    print(f'\n已删除 {deleted_count} 个无效实体')
    print(f'剩余实体数: {len(db.get_entities())}')

    # 使用 LLM 辅助审核剩余实体
    llm_review(entities, db)

def llm_review(entities, db):
    """使用 LLM 辅助审核实体"""
    if not RAG_AGNES_API_KEY:
        print('\nLLM API Key 未配置，跳过 LLM 审核')
        return

    print('\n开始 LLM 辅助审核...')

    # 筛选待审核的实体（有属性但类型为"未分类"）
    unclassified = [e for e in entities if e['type'] == '未分类' and e['properties']]

    if not unclassified:
        print('没有需要 LLM 审核的实体')
        return

    print(f'待审核实体: {len(unclassified)} 个')

    # 构建 LLM 输入
    entities_text = json.dumps(unclassified, ensure_ascii=False, indent=2)

    prompt = f"""你是一个专业的知识图谱审核助手。请审核以下 Wiki 实体列表，判断哪些是有效的实体，哪些是噪声。

实体列表：
{entities_text}

审核标准：
1. 实体名称应该是一个具体的名词（人物、蛊虫、势力等）
2. 排除单个字符、无意义的短语、句子片段
3. 排除重复的实体
4. 排除明显错误的数据
5. 如果实体类型为"未分类"，请根据属性判断更准确的类型

请返回 JSON 格式：
{{
    "valid": [{{"id": "实体ID", "name": "实体名", "type": "新类型"}}],
    "invalid": ["实体ID1", "实体ID2"],
    "reason": "审核说明"
}}"""

    # 调用 LLM
    try:
        import requests

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {RAG_AGNES_API_KEY}'
        }

        data = {
            'model': 'agnes-2.0-flash',
            'messages': [
                {'role': 'system', 'content': '你是一个专业的知识图谱审核助手。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.1,
            'max_tokens': 2000
        }

        response = requests.post(
            f'{RAG_AGNES_API_BASE}/chat/completions',
            headers=headers,
            json=data,
            timeout=60
        )

        response.raise_for_status()
        result = response.json()

        content = result['choices'][0]['message']['content']
        print(f'\nLLM 审核结果: {content[:200]}...')

        # 解析 LLM 返回
        # 简单解析：提取 valid 和 invalid 列表
        import re

        # 尝试提取 JSON
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            llm_result = json.loads(json_match.group())
        else:
            print('无法解析 LLM 返回结果')
            return

        # 批量批准有效实体
        if 'valid' in llm_result:
            for entity in llm_result['valid']:
                try:
                    if entity.get('type'):
                        db.update_entity_type(entity['id'], entity['type'])
                    db.approve_entity(entity['id'])
                except Exception as e:
                    print(f'批准实体失败 {entity[\"id\"]}: {e}')

        # 批量拒绝无效实体
        if 'invalid' in llm_result:
            for entity_id in llm_result['invalid']:
                try:
                    db.reject_entity(entity_id)
                except Exception as e:
                    print(f'拒绝实体失败 {entity_id}: {e}')

        print(f'\nLLM 审核完成: 批准 {len(llm_result.get(\"valid\", []))} 个，拒绝 {len(llm_result.get(\"invalid\", []))} 个')

    except Exception as e:
        print(f'LLM 审核失败: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    clean_entities()
