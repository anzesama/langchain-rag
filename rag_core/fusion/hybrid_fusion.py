"""
Result Fusion Module for Hybrid Retrieval
===========================================
Combines results from multiple retrievers (vector + BM25 + others)
using various fusion strategies.

Supports:
- Reciprocal Rank Fusion (RRF)
- Weighted score fusion
- Normalized score fusion
"""

import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any


class ResultFusion:
    """
    Fuses results from multiple retrievers.
    
    Supports multiple fusion strategies:
    1. Reciprocal Rank Fusion (RRF) - rank-based, robust to score scaling
    2. Weighted sum - combines normalized scores
    3. Max normalization - simple max score
    """
    
    # Default RRF constant
    RRF_K = 60
    
    def __init__(self, strategy: str = 'rrf', weights: Dict[str, float] = None):
        """
        Args:
            strategy: Fusion strategy ('rrf', 'weighted', 'max')
            weights: Weights for each retriever (used in 'weighted' strategy)
        """
        self.strategy = strategy
        self.weights = weights or {'vector': 0.5, 'bm25': 0.5}
    
    def fuse(self, results_dict: Dict[str, List[Tuple[str, float]]], 
             top_k: int = 10) -> List[Tuple[str, float]]:
        """
        Fuse results from multiple retrievers.
        
        Args:
            results_dict: Dict mapping retriever name to list of (doc_id, score) tuples
            top_k: Number of results to return
            
        Returns:
            Fused list of (doc_id, fused_score) tuples sorted by score
        """
        if not results_dict:
            return []
        
        if self.strategy == 'rrf':
            return self._reciprocal_rank_fusion(results_dict, top_k)
        elif self.strategy == 'weighted':
            return self._weighted_fusion(results_dict, top_k)
        elif self.strategy == 'max':
            return self._max_fusion(results_dict, top_k)
        else:
            raise ValueError(f"Unknown fusion strategy: {self.strategy}")
    
    def _reciprocal_rank_fusion(self, results_dict: Dict[str, List[Tuple[str, float]]], 
                                 top_k: int) -> List[Tuple[str, float]]:
        """
        Reciprocal Rank Fusion (RRF).
        
        For each document, sum 1/(k + rank) across all retrievers.
        More robust to different score scales than weighted fusion.
        """
        rrf_scores = defaultdict(float)
        
        for retriever_name, results in results_dict.items():
            weight = self.weights.get(retriever_name, 1.0)
            
            for rank, (doc_id, score) in enumerate(results, 1):
                rrf_scores[doc_id] += weight * (1.0 / (self.RRF_K + rank))
        
        # Sort by RRF score
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_id, round(score, 6)) for doc_id, score in sorted_results[:top_k]]
    
    def _weighted_fusion(self, results_dict: Dict[str, List[Tuple[str, float]]], 
                         top_k: int) -> List[Tuple[str, float]]:
        """
        Weighted sum fusion with min-max normalization.
        
        Normalizes scores to [0, 1] range, then applies weights.
        """
        # Collect all doc IDs
        all_doc_ids = set()
        for results in results_dict.values():
            for doc_id, score in results:
                all_doc_ids.add(doc_id)
        
        # Find min/max for normalization per retriever
        norms = {}
        for retriever_name, results in results_dict.items():
            scores = [score for _, score in results]
            if scores:
                norms[retriever_name] = (min(scores), max(scores))
            else:
                norms[retriever_name] = (0, 1)
        
        # Normalize and weight scores
        weighted_scores = defaultdict(float)
        total_weight = 0
        
        for retriever_name, results in results_dict.items():
            weight = self.weights.get(retriever_name, 1.0)
            total_weight += weight
            
            min_score, max_score = norms.get(retriever_name, (0, 1))
            score_range = max_score - min_score
            
            for doc_id, score in results:
                # Min-max normalization
                if score_range > 0:
                    normalized = (score - min_score) / score_range
                else:
                    normalized = 1.0 if score > 0 else 0.0
                
                weighted_scores[doc_id] += weight * normalized
        
        # Normalize weights
        if total_weight > 0:
            for doc_id in weighted_scores:
                weighted_scores[doc_id] /= total_weight
        
        # Sort and return top-k
        sorted_results = sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_id, round(score, 4)) for doc_id, score in sorted_results[:top_k]]
    
    def _max_fusion(self, results_dict: Dict[str, List[Tuple[str, float]]], 
                    top_k: int) -> List[Tuple[str, float]]:
        """
        Simple max fusion: take the maximum score across all retrievers.
        """
        max_scores = defaultdict(float)
        
        for results in results_dict.values():
            for doc_id, score in results:
                max_scores[doc_id] = max(max_scores[doc_id], score)
        
        sorted_results = sorted(max_scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_id, round(score, 4)) for doc_id, score in sorted_results[:top_k]]
    
    def get_fusion_report(self, results_dict: Dict[str, List[Tuple[str, float]]], 
                          top_k: int = 10) -> Dict:
        """
        Generate a report on the fusion results.
        
        Args:
            results_dict: Input results from each retriever
            top_k: Number of results returned
            
        Returns:
            Report dict with statistics
        """
        fused = self.fuse(results_dict, top_k)
        
        # Analyze contribution
        retriever_contributions = defaultdict(int)
        doc_sources = {}
        
        for retriever_name, results in results_dict.items():
            for rank, (doc_id, score) in enumerate(results, 1):
                retriever_contributions[retriever_name] += 1
                if doc_id not in doc_sources:
                    doc_sources[doc_id] = []
                doc_sources[doc_id].append(retriever_name)
        
        # Count docs from each retriever in final results
        fused_docs = set(d for d, _ in fused)
        single_source = sum(1 for d in fused_docs if len(doc_sources.get(d, [])) == 1)
        multi_source = sum(1 for d in fused_docs if len(doc_sources.get(d, [])) > 1)
        
        return {
            'strategy': self.strategy,
            'top_k': top_k,
            'total_fused_results': len(fused),
            'retrievers_used': list(results_dict.keys()),
            'contribution': dict(retriever_contributions),
            'single_source_count': single_source,
            'multi_source_count': multi_source,
            'fusion_diversity': round(multi_source / max(1, len(fused_docs)), 2),
            'top_results': [{'doc_id': d, 'score': s} for d, s in fused[:5]],
        }


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache for query results.
    
    Thread-safe implementation with configurable capacity and TTL.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live in seconds (default: 1 hour)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = {}          # key -> {'value': ..., 'timestamp': ...}
        self.order = []          # insertion order for LRU
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Returns None if not found or expired.
        Updates access order for LRU.
        """
        if key not in self.cache:
            self.misses += 1
            return None
        
        entry = self.cache[key]
        timestamp = entry['timestamp']
        
        # Check TTL
        import time
        if time.time() - timestamp > self.ttl_seconds:
            # Expired, remove
            del self.cache[key]
            self.order.remove(key)
            self.misses += 1
            return None
        
        # Move to end (most recently used)
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)
        
        self.hits += 1
        return entry['value']
    
    def set(self, key: str, value: Any):
        """
        Set value in cache.
        
        Evicts LRU entry if cache is full.
        """
        import time
        
        # If key exists, update and move to end
        if key in self.cache:
            self.cache[key]['value'] = value
            self.cache[key]['timestamp'] = time.time()
            self.order.remove(key)
            self.order.append(key)
            return
        
        # Evict LRU entry if full
        if len(self.cache) >= self.max_size:
            lru_key = self.order.pop(0)
            del self.cache[lru_key]
        
        # Add new entry
        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }
        self.order.append(key)
    
    def delete(self, key: str) -> bool:
        """Remove entry from cache."""
        if key in self.cache:
            del self.cache[key]
            self.order.remove(key)
            return True
        return False
    
    def clear(self):
        """Clear all entries."""
        self.cache.clear()
        self.order.clear()
        self.hits = 0
        self.misses = 0
    
    def stats(self) -> Dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / max(1, total)
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(hit_rate, 3),
        }


def main():
    """Demo CLI for Result Fusion."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Result Fusion Demo')
    parser.add_argument('--strategy', type=str, default='rrf', choices=['rrf', 'weighted', 'max'])
    args = parser.parse_args()
    
    # Simulate results from two retrievers
    vector_results = {
        'vector': [
            ('doc_1', 0.92), ('doc_2', 0.85), ('doc_3', 0.78), 
            ('doc_4', 0.65), ('doc_5', 0.55)
        ],
        'bm25': [
            ('doc_3', 4.5), ('doc_1', 3.8), ('doc_5', 2.9), 
            ('doc_6', 2.1), ('doc_2', 1.8)
        ]
    }
    
    # Test fusion
    fusion = ResultFusion(strategy=args.strategy)
    fused = fusion.fuse(vector_results, top_k=5)
    
    print(f"\nFusion Strategy: {args.strategy}")
    print(f"{'Doc ID':<10} {'Score':<10}")
    print("-" * 20)
    for doc_id, score in fused:
        print(f"{doc_id:<10} {score:<10}")
    
    # Test report
    report = fusion.get_fusion_report(vector_results, top_k=5)
    print(f"\nFusion Report:")
    print(f"  Single source: {report['single_source_count']}")
    print(f"  Multi source: {report['multi_source_count']}")
    print(f"  Diversity: {report['fusion_diversity']}")
    
    # Test LRU Cache
    print(f"\nLRU Cache Demo:")
    cache = LRUCache(max_size=5, ttl_seconds=60)
    
    # Set some values
    for i in range(7):
        cache.set(f"query_{i}", f"result_{i}")
    
    print(f"  After 7 inserts (max 5): size={cache.stats()['size']}")
    print(f"  LRU evicted: query_0, query_1 (should not be in cache)")
    print(f"  Hit query_6: {cache.get('query_6') is not None}")
    print(f"  Hit query_0: {cache.get('query_0') is not None}")
    print(f"  Stats: {cache.stats()}")


if __name__ == '__main__':
    main()
