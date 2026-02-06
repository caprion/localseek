"""
Reranking module for localseek

Uses a local LLM to re-score search results for relevance.
"""

import hashlib
import sys
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..config import get_config
from .llm_client import get_llm_client


RERANK_PROMPT = """Rate the relevance of each document to the query on a scale of 0-10.
0 = completely irrelevant
5 = somewhat relevant
10 = highly relevant

Output only numbers, one per line, in the same order as the documents."""


@dataclass
class RerankResult:
    """A reranked search result"""
    path: str
    title: str
    snippet: str
    original_score: float
    rerank_score: float
    blended_score: float
    collection: str
    full_path: str
    original_rank: int


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    topk: Optional[int] = None,
    cache: Optional["RerankCache"] = None,
) -> Tuple[List[RerankResult], int]:
    """
    Rerank search results using LLM
    
    Args:
        query: The search query
        results: List of search result dicts with path, title, snippet, score, etc.
        topk: Number of candidates to rerank (default from config)
        cache: Optional cache instance
    
    Returns:
        Tuple of (reranked results, cache_hit_count)
    """
    config = get_config()
    topk = topk or config.rerank_topk
    
    # Limit candidates
    candidates = results[:topk]
    if not candidates:
        return [], 0
    
    # Get query hash for caching
    query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
    
    # Check cache for each document
    cache_hits = 0
    scores = {}
    uncached_indices = []
    
    for i, doc in enumerate(candidates):
        doc_hash = doc.get("hash", hashlib.md5(doc.get("snippet", "").encode()).hexdigest())
        
        if cache:
            cached_score = cache.get(query_hash, doc_hash)
            if cached_score is not None:
                scores[i] = cached_score
                cache_hits += 1
                continue
        
        uncached_indices.append(i)
    
    # Get LLM scores for uncached documents
    if uncached_indices:
        llm_scores = _get_llm_scores(query, [candidates[i] for i in uncached_indices])
        
        if llm_scores:
            for idx, score in zip(uncached_indices, llm_scores):
                scores[idx] = score
                
                # Cache the score
                if cache:
                    doc = candidates[idx]
                    doc_hash = doc.get("hash", hashlib.md5(doc.get("snippet", "").encode()).hexdigest())
                    cache.set(query_hash, doc_hash, score)
        else:
            # LLM failed, use original scores
            for idx in uncached_indices:
                scores[idx] = 5.0  # Neutral score
    
    # Blend scores using position-aware weighting
    reranked = []
    for i, doc in enumerate(candidates):
        original_rank = i + 1
        original_score = doc.get("score", 0.0)
        rerank_score = scores.get(i, 5.0) / 10.0  # Normalize to 0-1
        
        # Position-aware blending
        if original_rank <= 3:
            # Trust BM25 more for top results
            weight_bm25 = 0.75
        elif original_rank <= 10:
            weight_bm25 = 0.60
        else:
            # Trust reranker more for lower results
            weight_bm25 = 0.40
        
        # Normalize original score (assuming max ~15 for BM25)
        norm_original = min(original_score / 15.0, 1.0)
        blended = (weight_bm25 * norm_original) + ((1 - weight_bm25) * rerank_score)
        
        reranked.append(RerankResult(
            path=doc.get("path", ""),
            title=doc.get("title", ""),
            snippet=doc.get("snippet", ""),
            original_score=original_score,
            rerank_score=scores.get(i, 5.0),
            blended_score=blended,
            collection=doc.get("collection", ""),
            full_path=doc.get("full_path", ""),
            original_rank=original_rank,
        ))
    
    # Sort by blended score
    reranked.sort(key=lambda x: x.blended_score, reverse=True)
    
    return reranked, cache_hits


def _get_llm_scores(query: str, docs: List[Dict[str, Any]]) -> Optional[List[float]]:
    """Get relevance scores from LLM"""
    client = get_llm_client()
    if not client.is_available():
        print("Warning: LLM server not available, skipping reranking", 
              file=sys.stderr)
        return None
    
    # Build document list
    doc_list = ""
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Untitled")
        snippet = doc.get("snippet", "")[:200]  # Limit snippet length
        doc_list += f"\n[{i}] {title}\n{snippet}\n"
    
    response = client.chat(
        messages=[
            {"role": "system", "content": RERANK_PROMPT},
            {"role": "user", "content": f"Query: {query}\n\nDocuments:{doc_list}"},
        ],
        max_tokens=50,
        temperature=0.0,  # Deterministic for consistency
    )
    
    if not response:
        return None
    
    # Parse scores
    scores = []
    for line in response.strip().split("\n"):
        line = line.strip()
        # Extract number from line
        try:
            # Handle formats like "1. 8" or "[1] 8" or just "8"
            parts = line.replace("[", "").replace("]", "").replace(".", " ").split()
            for part in reversed(parts):
                score = float(part)
                if 0 <= score <= 10:
                    scores.append(score)
                    break
        except (ValueError, IndexError):
            continue
    
    # If we got fewer scores than documents, pad with neutral
    while len(scores) < len(docs):
        scores.append(5.0)
    
    return scores[:len(docs)]


class RerankCache:
    """Cache for rerank scores"""
    
    def __init__(self, db_path: Optional[str] = None):
        import sqlite3
        from pathlib import Path
        
        config = get_config()
        self.db_path = Path(db_path) if db_path else config.cache_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS rerank_cache (
                cache_key TEXT PRIMARY KEY,
                query_hash TEXT NOT NULL,
                doc_hash TEXT NOT NULL,
                score REAL NOT NULL,
                model_version TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_rerank_doc 
            ON rerank_cache(doc_hash);
            CREATE INDEX IF NOT EXISTS idx_rerank_query 
            ON rerank_cache(query_hash);
        """)
        self.conn.commit()
    
    def _make_key(self, query_hash: str, doc_hash: str) -> str:
        return hashlib.sha256(f"{query_hash}:{doc_hash}".encode()).hexdigest()
    
    def get(self, query_hash: str, doc_hash: str) -> Optional[float]:
        """Get cached rerank score"""
        cache_key = self._make_key(query_hash, doc_hash)
        
        row = self.conn.execute(
            "SELECT score FROM rerank_cache WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()
        
        return row["score"] if row else None
    
    def set(self, query_hash: str, doc_hash: str, score: float):
        """Cache rerank score"""
        from datetime import datetime
        
        cache_key = self._make_key(query_hash, doc_hash)
        
        self.conn.execute(
            """INSERT OR REPLACE INTO rerank_cache 
               (cache_key, query_hash, doc_hash, score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (cache_key, query_hash, doc_hash, score, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def invalidate_doc(self, doc_hash: str):
        """Invalidate all cache entries for a document"""
        self.conn.execute(
            "DELETE FROM rerank_cache WHERE doc_hash = ?",
            (doc_hash,)
        )
        self.conn.commit()
    
    def clear(self):
        """Clear all cached scores"""
        self.conn.execute("DELETE FROM rerank_cache")
        self.conn.commit()
    
    def close(self):
        self.conn.close()
