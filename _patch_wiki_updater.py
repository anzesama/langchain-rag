#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Append LLM methods to WikiUpdater with correct indentation."""
import os

PATCH_CONTENT = """
    def scan_new_entities_llm(self, text: str, source_chapter: str = None) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        try:
            from rag_core.llm_extractor import LLMExtractor
            extractor = LLMExtractor()
            extraction_result = extractor.extract_all(text, source_chapter)
            new_entities = []
            for entity in extraction_result["llm"]:
                try:
                    self.wiki_db.add_entity(
                        name=entity["name"],
                        entity_type=entity["type"],
                        properties={"description": entity.get("description", "")},
                        source_chapter=source_chapter
                    )
                    new_entities.append({
                        "name": entity["name"],
                        "type": entity["type"],
                        "confidence": 1,
                        "source_chapter": source_chapter,
                        "method": "llm"
                    })
                except Exception as e:
                    logger.error("LLM entity add failed: " + str(e))
            logger.info("LLM scanned " + str(len(new_entities)) + " new entities")
            self._write_to_pending(extraction_result["regex"], source_chapter=source_chapter, method="regex")
            self._write_to_pending(extraction_result["jieba"], source_chapter=source_chapter, method="jieba")
            return new_entities
        except Exception as e:
            logger.warning("LLM extract failed: " + str(e))
            return self.scan_new_entities(text, source_chapter, min_confidence=2)

    def scan_new_relations_llm(self, text: str, source_chapter: str = None) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        try:
            from rag_core.llm_extractor import LLMExtractor
            extractor = LLMExtractor()
            extraction_result = extractor.extract_all(text, source_chapter)
            new_relations = []
            for rel in extraction_result["llm"]:
                try:
                    self.wiki_db.add_relationship(
                        source_name=rel["source"],
                        target_name=rel["target"],
                        rel_type=rel["type"],
                        properties={"description": rel.get("description", "")},
                        source_chapter=source_chapter
                    )
                    new_relations.append({
                        "source": rel["source"],
                        "target": rel["target"],
                        "rel_type": rel["type"],
                        "confidence": 1,
                        "source_chapter": source_chapter,
                        "method": "llm"
                    })
                except Exception as e:
                    logger.error("LLM relation add failed: " + str(e))
            logger.info("LLM scanned " + str(len(new_relations)) + " new relations")
            self._write_pending_relations(extraction_result["regex"], source_chapter=source_chapter, method="regex")
            self._write_pending_relations(extraction_result["jieba"], source_chapter=source_chapter, method="jieba")
            return new_relations
        except Exception as e:
            logger.warning("LLM relation extract failed: " + str(e))
            return self.scan_new_relations(text, source_chapter)

    def _write_to_pending(self, entities: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
        if not entities:
            return 0
        count = 0
        for entity in entities:
            name = entity.get("name", "")
            entity_type = entity.get("type", "unknown")
            description = entity.get("description", "")
            confidence = entity.get("confidence", 0)
            try:
                self.wiki_db.add_to_pending(
                    entity_name=name,
                    relation_type=entity_type,
                    properties={"description": description, "method": method, "source_chapter": source_chapter},
                    confidence=confidence
                )
                count += 1
            except Exception as e:
                logger.error("Pending entity write failed: " + str(e))
        return count

    def _write_pending_relations(self, relations: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
        if not relations:
            return 0
        count = 0
        for rel in relations:
            source_name = rel.get("source", "")
            target_name = rel.get("target", "")
            rel_type = rel.get("type", "related")
            description = rel.get("description", "")
            confidence = rel.get("confidence", 0)
            try:
                key = source_name + "--" + rel_type + "--" + target_name
                self.wiki_db.add_to_pending(
                    entity_name=key,
                    relation_type=key,
                    properties={"description": description, "method": method, "source_chapter": source_chapter, "source": source_name, "target": target_name, "rel_type": rel_type},
                    confidence=confidence
                )
                count += 1
            except Exception as e:
                logger.error("Pending relation write failed: " + str(e))
        return count
"""

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wiki_path = os.path.join(base_dir, "rag_core", "wiki_updater.py")

    with open(wiki_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Append patch at end (class ends at EOF, so this keeps methods in class)
    content = content + "\n" + PATCH_CONTENT.rstrip("\n")

    with open(wiki_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("Appended patch to", wiki_path)

if __name__ == "__main__":
    main()