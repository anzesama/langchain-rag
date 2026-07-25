"""
Wiki 实体清理脚本（简化版）
"""
import sys
sys.path.insert(0, 'D:/class/project-config/langchain-rag')

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from rag_core import wiki_db

def clean_entities():
    """清理无效实体"""
    db = wiki_db.WikiDB('D:/class/project-config/langchain-rag/data/wiki/wiki.db')
    db.init_db()

    entities = db.get_entities()
    print(f'Total entities: {len(entities)}')

    # 1. Delete single character entities
    single_chars = [e['id'] for e in entities if len(e['name']) == 1]
    print(f'Single char entities: {len(single_chars)}')

    # 2. Delete entities without properties
    no_props = [e['id'] for e in entities if not e['properties'] or e['properties'] == {}]
    print(f'Entities without properties: {len(no_props)}')

    # 3. Delete long text entities (>50 chars)
    long_texts = [e['id'] for e in entities if len(e['name']) > 50]
    print(f'Long text entities (>50 chars): {len(long_texts)}')

    # Confirm delete
    confirm = input(f'\nConfirm delete? (yes/no): ')
    if confirm.lower() != 'yes':
        print('Cancelled')
        return

    # Execute delete
    deleted_count = 0
    for entity_id in single_chars + no_props + long_texts:
        try:
            db.delete_entity(entity_id)
            deleted_count += 1
        except Exception as e:
            print(f'Delete failed {entity_id}: {e}')

    print(f'Deleted {deleted_count} entities')
    print(f'Remaining: {len(db.get_entities())}')

if __name__ == '__main__':
    clean_entities()
