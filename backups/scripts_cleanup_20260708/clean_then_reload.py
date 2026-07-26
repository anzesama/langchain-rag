"""Delete guzhenren chunks from knowledge_base, then reload cleanly"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from rag_core.vector_store import VectorStoreManager

vs = VectorStoreManager(Path('D:/class/project-config/langchain-rag/storage/knowledge_base'))

# Delete all existing data
print("Deleting all existing data...")
vs.delete_collection()
print("Done.")

# Now check
vs2 = VectorStoreManager(Path('D:/class/project-config/langchain-rag/storage/knowledge_base'))
print(f"After delete: {vs2.get_stats()}")
