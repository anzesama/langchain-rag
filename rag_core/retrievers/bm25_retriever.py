"""
BM25 Retriever for RAG System
===============================
Implements BM25 (Best Matching 25) algorithm for keyword-based retrieval.
Complements vector similarity search with lexical matching.

Reference: Robertson et al. "A Probabilistic Model of Information Retrieval" (1995)
"""

import math
import re
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# Add langchain-rag to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class BM25Tokenizer:
    """Simple tokenizer for both Chinese and English text."""
    
    def __init__(self, stop_words: Optional[List[str]] = None):
        self.stop_words = set(stop_words or [])
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms.
        
        Handles:
        - Chinese characters (each char is a token)
        - English words
        - Numbers
        """
        if not text:
            return []
        
        # Extract Chinese characters
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        
        # Extract English words
        english_words = re.findall(r'[a-zA-Z]+', text.lower())
        
        # Extract numbers
        numbers = re.findall(r'\d+', text)
        
        # Combine all tokens
        tokens = chinese_chars + english_words + numbers
        
        # Remove stop words
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 0]
        
        return tokens


class BM25Retriever:
    """
    BM25 keyword-based retriever.
    
    Works alongside vector similarity search to provide hybrid retrieval.
    Stores inverted index in memory for fast lookup.
    """
    
    # BM25 parameters (standard values)
    K1 = 1.5      # Term frequency saturation
    B = 0.75      # Length normalization factor
    
    def __init__(self, k1: float = None, b: float = None):
        """
        Args:
            k1: Term frequency parameter (default: 1.5)
            b: Length normalization parameter (default: 0.75)
        """
        self.k1 = k1 or self.K1
        self.b = b or self.B
        
        # Index structures
        self.doc_lengths = {}           # doc_id -> num_tokens
        self.avgdl = 0                  # average document length
        self.freq = defaultdict(lambda: defaultdict(int))  # term -> doc_id -> count
        self.df = defaultdict(int)       # term -> num_docs_containing_term
        self.docs = {}                   # doc_id -> doc_content
        self.tokenizer = BM25Tokenizer()
        self.indexed = False
            
    def fit(self, documents: List[Dict]):
        """
        Build BM25 index from documents.
        
        Args:
            documents: List of dicts with 'id', 'content', and optional 'metadata'
        """
        # Clear existing index
        self.freq = defaultdict(lambda: defaultdict(int))
        self.df = defaultdict(int)
        self.docs = {}
        self.doc_lengths = {}
        
        # Tokenize all documents
        doc_tokens = []
        for doc in documents:
            doc_id = doc.get('id', str(len(self.docs)))
            content = doc.get('content', '')
            
            tokens = self.tokenizer.tokenize(content)
            doc_tokens.append((doc_id, tokens))
            
            self.docs[doc_id] = content
            self.doc_lengths[doc_id] = len(tokens)
            
            # Update term frequencies
            term_counts = defaultdict(int)
            for token in tokens:
                term_counts[token] += 1
            
            for term, count in term_counts.items():
                self.freq[term][doc_id] = count
                self.df[term] += 1
        
        # Calculate average document length
        total_tokens = sum(self.doc_lengths.values())
        self.avgdl = total_tokens / max(1, len(documents))
        
        self.indexed = True
    
    def transform(self, query: str) -> List[str]:
        """Tokenize query."""
        return self.tokenizer.tokenize(query)
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        Search for top-k documents matching query.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            
        Returns:
            List of (doc_id, score) tuples sorted by score descending
        """
        if not self.indexed:
            return []
        
        query_terms = self.transform(query)
        if not query_terms:
            return []
        
        # Calculate scores for all documents
        scores = defaultdict(float)
        N = len(self.docs)  # Total number of documents
        
        for term in query_terms:
            df = self.df.get(term, 0)
            if df == 0:
                continue
            
            # IDF component
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            
            # Score each document containing this term
            for doc_id, term_freq in self.freq[term].items():
                doc_len = self.doc_lengths.get(doc_id, 0)
                
                # TF component with length normalization
                tf = term_freq * (self.k1 + 1)
                tf /= term_freq + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                
                scores[doc_id] += idf * tf
        
        # Sort by score and return top-k
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]
    
    def search_with_metadata(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        Search and return results with document metadata.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            
        Returns:
            List of dicts with 'doc_id', 'score', 'content', 'metadata'
        """
        results = self.search(query, top_k)
        
        output = []
        for doc_id, score in results:
            doc = {
                'doc_id': doc_id,
                'score': round(score, 4),
                'content': self.docs.get(doc_id, ''),
                'metadata': {}
            }
            output.append(doc)
        
        return output
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        if not self.indexed:
            return {'error': 'Index not built'}
        
        total_terms = sum(len(docs) for docs in self.freq.values())
        unique_terms = len(self.freq)
        
        return {
            'documents_indexed': len(self.docs),
            'unique_terms': unique_terms,
            'total_term_occurrences': total_terms,
            'avg_doc_length': round(self.avgdl, 1),
            'k1': self.k1,
            'b': self.b,
        }


def main():
    """Demo CLI for BM25 retriever."""
    import argparse
    
    parser = argparse.ArgumentParser(description='BM25 Retriever Demo')
    parser.add_argument('--query', type=str, required=True, help='Search query')
    parser.add_argument('--docs', type=int, default=5, help='Number of sample docs')
    
    args = parser.parse_args()
    
    # Sample documents for demo
    sample_docs = [
        {'id': '1', 'content': '人工智能是计算机科学的一个分支，致力于创建智能机器'},
        {'id': '2', 'content': '深度学习是机器学习的一个子领域，使用多层神经网络'},
        {'id': '3', 'content': '自然语言处理是人工智能的重要应用领域'},
        {'id': '4', 'content': '机器学习算法可以从数据中学习模式并进行预测'},
        {'id': '5', 'content': '计算机视觉让机器能够理解和解释视觉信息'},
    ]
    
    # Build index and search
    retriever = BM25Retriever()
    retriever.fit(sample_docs)
    
    print(f"\nBM25 Index Stats:")
    stats = retriever.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print(f"\nQuery: '{args.query}'")
    results = retriever.search_with_metadata(args.query, top_k=3)
    
    print(f"\nTop {len(results)} Results:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. [score={r['score']:.4f}] {r['content'][:50]}...")


if __name__ == '__main__':
    main()
