#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Encoding-safe document importer for Windows
"""
import sys
import io

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import sys
sys.path.insert(0, '.')
from rag_core.document_loader import load_document
from rag_core.llm_extractor import LLMExtractor
from rag_core.wiki_db_libsql import WikiDB
from pathlib import Path


def import_documents(documents_dir: Path):
    """Import all documents with encoding-safe output"""
    llm_extractor = LLMExtractor()
    wiki_db = WikiDB()

    print(f"Importing documents from {documents_dir}")
    print("=" * 60)

    total_entities = 0
    total_relations = 0
    total_files = 0

    for filepath in sorted(documents_dir.rglob('*')):
        if not filepath.is_file():
            continue

        if filepath.suffix.lower() not in ['.md', '.txt']:
            continue

        total_files += 1
        print(f"\n[{total_files}] Importing: {filepath.name}")

        try:
            documents = load_document(filepath)
            print(f"    Loaded {len(documents)} documents")

            for doc in documents:
                result = llm_extractor.extract_all(doc.page_content, str(filepath))

                entities = result.get('llm', []) + result.get('regex', []) + result.get('jieba', [])
                relations = result.get('relations', [])

                print(f"    Extracted: {len(entities)} entities, {len(relations)} relations")

                # Add entities
                for entity in entities:
                    wiki_db.add_entity(
                        name=entity['name'],
                        entity_type=entity['type'],
                        properties=entity.get('properties', {}),
                        aliases=entity.get('aliases', []),
                        source_chapter=str(filepath)
                    )

                # Add relations
                for relation in relations:
                    wiki_db.add_relationship(
                        source_name=relation['source'],
                        target_name=relation['target'],
                        rel_type=relation['type'],
                        properties=relation.get('properties', {}),
                        source_chapter=str(filepath)
                    )

                total_entities += len(entities)
                total_relations += len(relations)

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Import completed!")
    print(f"  Total files: {total_files}")
    print(f"  Total entities: {total_entities}")
    print(f"  Total relations: {total_relations}")
    print("=" * 60)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Import documents with encoding-safe output')
    parser.add_argument('documents_dir', type=str, help='Path to documents directory')
    args = parser.parse_args()

    import_documents(Path(args.documents_dir))
