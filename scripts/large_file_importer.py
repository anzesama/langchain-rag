"""v2: Large file import with batched embedding generation + resume support.

Problem: 18,747 chunks * embedding = 20-30 min CPU time. Direct approach times out.
Solution:
  1. Split & insert chunks FIRST (no embeddings yet) -- fast
  2. Generate embeddings in small batches (500/batch), write to DB immediately
  3. Save resume checkpoint after each batch (survives crashes)
  4. Track progress via checkpoint file

Usage:
    python scripts/import_large_file_v2.py                          # full import
    python scripts/import_large_file_v2.py --embed-only             # resume embedding generation
    python scripts/import_large_file_v2.py --embed-only --force     # restart embedding from batch 0
    python scripts/import_large_file_v2.py --dry-run                # check status without action
"""

import sys
import json
import pathlib
import sqlite3
import time
import hashlib
import struct
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, '.')

from rag_config import logger
from rag_core.embedding_service import get_embeddings

# ============================================================
# Config
# ============================================================
DB_PATH = pathlib.Path("storage/knowledge_base.db")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBED_BATCH = 500          # embedding 批次大小
CHECKPOINT_FILE = pathlib.Path("storage/_import_checkpoint_v2.json")


# ============================================================
# Step 1: Split & Insert (fast, no embeddings)
# ============================================================
def detect_encoding(file_path: pathlib.Path) -> str:
    """智能检测文件编码"""
    encodings = ['utf-8', 'gbk', 'gb18030', 'utf-16']
    with open(file_path, 'rb') as f:
        bom = f.read(4)
    if bom.startswith(b'\xff\xfe'): return 'utf-16-le'
    if bom.startswith(b'\xfe\xff'): return 'utf-16-be'
    if bom.startswith(b'\xef\xbb\xbf'): return 'utf-8-sig'
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(4096)
            return enc
        except Exception:
            continue
    return 'utf-8'


def split_and_insert_chunks(file_path: pathlib.Path, source_name: str, encoding: str) -> int:
    """Split file into chunks and insert into DB (without embeddings).

    Returns total chunks inserted.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # Read entire file
    with open(file_path, 'r', encoding=encoding) as f:
        text = f.read()

    # Split
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    documents = splitter.create_documents([text], [{'source': source_name}])
    total = len(documents)
    print(f"  分割完成: {total:,} 个 chunk")

    # Insert into DB (vector = empty blob)
    conn = sqlite3.connect(str(DB_PATH))
    count = 0
    try:
        import hashlib
        for i, doc in enumerate(documents):
            chunk_id = f"doc_{hashlib.md5((str(i) + source_name).encode()).hexdigest()[:12]}"
            metadata_json = json.dumps(doc.metadata, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO chunks (chunk_id, text_content, vector, metadata, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk_id, doc.page_content, b'', metadata_json, source_name)
            )
            count += 1
            if count % 2000 == 0:
                conn.commit()
                print(f"  插入: {count}/{total} ({100*count//total}%)")
        conn.commit()
    finally:
        conn.close()

    print(f"  入库完成: {count} 条")
    return count


# ============================================================
# Step 2: Embedding generation (slow, batched, resumable)
# ============================================================
def load_chunk_batch(source_name: Optional[str], offset: int, limit: int) -> List[dict]:
    """Load chunks that need vectors from DB."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if source_name:
        c.execute(
            """SELECT chunk_id, text_content FROM chunks
               WHERE (vector IS NULL OR vector = '' OR length(vector) = 0)
               AND source LIKE ?
               LIMIT ? OFFSET ?""",
            (f'%{source_name}%', limit, offset)
        )
    else:
        c.execute(
            """SELECT chunk_id, text_content FROM chunks
               WHERE vector IS NULL OR vector = '' OR length(vector) = 0
               LIMIT ? OFFSET ?""",
            (limit, offset)
        )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def check_remaining(source_name: Optional[str] = None) -> int:
    """Count how many chunks still need vectors."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    if source_name:
        c.execute(
            "SELECT COUNT(*) FROM chunks WHERE (vector IS NULL OR vector = '' OR length(vector) = 0) "
            "AND source LIKE ?",
            (f'%{source_name}%',)
        )
    else:
        c.execute("SELECT COUNT(*) FROM chunks WHERE vector IS NULL OR vector = '' OR length(vector) = 0")
    remaining = c.fetchone()[0]
    conn.close()
    return remaining


def pack_vectors_to_blobs(vectors: List[List[float]]) -> List[bytes]:
    """Convert vectors to byte blobs (big-endian doubles)."""
    blobs = []
    for vec in vectors:
        dim = len(vec)
        blobs.append(struct.pack(f'>{dim}d', *vec))
    return blobs


def save_checkpoint(batch_idx: int, total: int):
    """Save resume point."""
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'current_batch': batch_idx,
            'total_batches': total,
            'updated_at': datetime.now().isoformat()
        }, f, indent=2)


def generate_embeddings(source_name: Optional[str] = None, force_restart: bool = False):
    """Generate embeddings for chunks missing vectors.

    Args:
        source_name: filter to a specific source
        force_restart: ignore existing checkpoint
    """
    # Count remaining
    remaining = check_remaining(source_name)
    if remaining == 0:
        print("  All vectors exist, nothing to do.")
        return

    # Load checkpoint
    start_batch = 0
    if CHECKPOINT_FILE.exists() and not force_restart:
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                cp = json.load(f)
            start_batch = cp.get('current_batch', 0)
            print(f"  Resuming from batch {start_batch}")
        except Exception:
            print("  Checkpoint corrupted, starting fresh")

    total_batches = (remaining + EMBED_BATCH - 1) // EMBED_BATCH

    print(f"\n[Embedding] 待处理: {remaining} chunks")
    print(f"  批次大小: {EMBED_BATCH}, 总批次: {total_batches}, 起始: {start_batch}")

    t0 = time.time()

    for batch_idx in range(start_batch, total_batches):
        batch_start = datetime.now()
        offset = batch_idx * EMBED_BATCH
        rows = load_chunk_batch(source_name, offset, EMBED_BATCH)
        if not rows:
            break

        texts = [r['text_content'] for r in rows]
        chunk_ids = [r['chunk_id'] for r in rows]

        # Generate vectors
        try:
            embeddings = get_embeddings(texts)
        except Exception as e:
            print(f"  FATAL: batch {batch_idx+1} embedding failed: {e}")
            save_checkpoint(batch_idx, total_batches)
            raise

        # Pack into blobs
        blobs = pack_vectors_to_blobs(embeddings[:len(texts)])

        # Write to DB
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for chunk_id, blob in zip(chunk_ids, blobs):
                conn.execute("UPDATE chunks SET vector = ? WHERE chunk_id = ?", (blob, chunk_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  FATAL: batch {batch_idx+1} DB write failed: {e}")
            save_checkpoint(batch_idx, total_batches)
            raise
        finally:
            conn.close()

        elapsed = (datetime.now() - batch_start).total_seconds()
        eta_sec = (total_batches - batch_idx - 1) * elapsed
        eta_min = eta_sec / 60
        print(f"  [{batch_idx+1}/{total_batches}] {len(chunk_ids)} chunks | {elapsed:.0f}s | ETA {eta_min:.0f}min")

        save_checkpoint(batch_idx + 1, total_batches)

    dt = time.time() - t0
    rem = check_remaining(source_name)
    print(f"\nDone in {dt:.0f}s ({dt/60:.1f}min), {rem} remaining.")


# ============================================================
# CLI Argument Parsing
# ============================================================
def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Large File Import v2.0")
    parser.add_argument('file', nargs='?', default='documents/蛊真人_精校版.txt',
                       help='File to import')
    parser.add_argument('--source', type=str, default=None,
                       help='Source name (default: file basename)')
    parser.add_argument('--embed-only', action='store_true',
                       help='Only generate embeddings (skip chunk insertion)')
    parser.add_argument('--force', action='store_true',
                       help='Reset checkpoint and start fresh')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show DB status without action')
    return parser.parse_args()


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    args = parse_args()
    fp = pathlib.Path(args.file) if args.file else None
    source_name = args.source or (fp.name if fp else None)

    print(f"\n{'='*70}")
    print("Large File Import v2.0")
    print(f"{'='*70}")

    # Show DB status
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chunks")
    total_all = c.fetchone()[0]
    if source_name:
        c.execute("SELECT COUNT(*) FROM chunks WHERE source LIKE ?", (f'%{source_name}%',))
        total_src = c.fetchone()[0]
    else:
        total_src = 0
    conn.close()

    print(f"Total chunks in DB: {total_all}")
    if source_name:
        print(f"  from '{source_name}': {total_src}")
    print(f"  Missing vectors: {check_remaining(source_name)}")
    print()

    if args.dry_run:
        sys.exit(0)

    # --embed-only mode
    if args.embed_only:
        if args.force and CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        if not source_name:
            print("ERROR: --embed-only requires a source name or file argument")
            sys.exit(1)
        generate_embeddings(source_name, force_restart=args.force)
        print("\nDone.")
        sys.exit(0)

    # Full import mode
    if not fp or not fp.exists():
        print(f"ERROR: file not found: {args.file}")
        sys.exit(1)

    # Delete old
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("DELETE FROM chunks WHERE source LIKE ?", (f'%{source_name}%',))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"Deleted {deleted} old chunks for '{source_name}'")

    encoding = detect_encoding(fp)
    print(f"Detected encoding: {encoding}")

    n = split_and_insert_chunks(fp, source_name, encoding)
    print()

    generate_embeddings(source_name)
    print("\nDone.")