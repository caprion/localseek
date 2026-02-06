"""
Search functionality for localseek

Handles querying the FTS5 index with BM25 ranking.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
import re

from .index import get_db_path, init_db


class SearchResult:
    """A single search result"""
    
    def __init__(
        self,
        path: str,
        title: str,
        snippet: str,
        score: float,
        collection: str,
        full_path: str
    ):
        self.path = path
        self.title = title
        self.snippet = snippet
        self.score = score
        self.collection = collection
        self.full_path = full_path
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "collection": self.collection,
            "full_path": self.full_path
        }
    
    def __repr__(self):
        return f"SearchResult({self.collection}/{self.path}, score={self.score:.2f})"


class Searcher:
    """Full-text search using FTS5 BM25"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self.conn = init_db(self.db_path)
    
    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.0,
        snippet_length: int = 150
    ) -> List[SearchResult]:
        """
        Search documents using FTS5 BM25
        
        Args:
            query: Search query (supports FTS5 syntax)
            collection: Restrict to specific collection
            limit: Maximum results to return
            min_score: Minimum BM25 score threshold
            snippet_length: Length of content snippet
        
        Returns:
            List of SearchResult objects sorted by relevance
        """
        # Clean and prepare query
        fts_query = self._prepare_query(query)
        
        if not fts_query.strip():
            return []
        
        # Build SQL
        sql = """
            SELECT 
                d.id,
                d.path,
                d.title,
                d.content,
                c.name as collection,
                c.path as collection_path,
                bm25(documents_fts) as score
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            JOIN collections c ON c.id = d.collection_id
            WHERE documents_fts MATCH ?
        """
        params: List[Any] = [fts_query]
        
        if collection:
            sql += " AND c.name = ?"
            params.append(collection)
        
        if min_score > 0:
            # BM25 returns negative scores, more negative = better match
            sql += " AND bm25(documents_fts) <= ?"
            params.append(-min_score)
        
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return []
            raise
        
        results = []
        for row in rows:
            # Generate snippet with query highlighting
            snippet = self._generate_snippet(
                row["content"], 
                query, 
                snippet_length
            )
            
            # Normalize score (BM25 returns negative, flip it)
            normalized_score = abs(row["score"])
            
            full_path = str(Path(row["collection_path"]) / row["path"])
            
            results.append(SearchResult(
                path=row["path"],
                title=row["title"],
                snippet=snippet,
                score=normalized_score,
                collection=row["collection"],
                full_path=full_path
            ))
        
        return results
    
    def _prepare_query(self, query: str) -> str:
        """
        Prepare query for FTS5
        
        Handles:
        - Simple queries: "decision making" → decision making
        - Phrase queries: '"exact phrase"' → "exact phrase"
        - OR queries: "cats OR dogs" → cats OR dogs
        - Prefix: "think*" → think*
        """
        # If already contains FTS5 operators, use as-is
        if any(op in query for op in ['"', 'OR', 'AND', 'NOT', '*', 'NEAR']):
            return query
        
        # Simple query: just return cleaned tokens
        # FTS5 will AND them together by default
        return query.strip()
    
    def _generate_snippet(
        self, 
        content: str, 
        query: str, 
        max_length: int
    ) -> str:
        """Generate a snippet with query terms highlighted"""
        # Get query terms (simple tokenization)
        terms = [t.lower().strip('*"') for t in query.split() 
                 if t.lower() not in ('and', 'or', 'not', 'near')]
        
        if not terms:
            return content[:max_length] + "..." if len(content) > max_length else content
        
        # Find best position (first occurrence of any term)
        content_lower = content.lower()
        best_pos = len(content)
        
        for term in terms:
            pos = content_lower.find(term)
            if 0 <= pos < best_pos:
                best_pos = pos
        
        # Extract snippet around best position
        start = max(0, best_pos - max_length // 3)
        end = min(len(content), start + max_length)
        
        # Adjust start to word boundary
        if start > 0:
            space_pos = content.rfind(' ', 0, start + 20)
            if space_pos > start - 20:
                start = space_pos + 1
        
        snippet = content[start:end]
        
        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        # Clean up whitespace
        snippet = ' '.join(snippet.split())
        
        return snippet
    
    def get_document(self, path: str, collection: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a document by path"""
        sql = """
            SELECT d.*, c.name as collection, c.path as collection_path
            FROM documents d
            JOIN collections c ON c.id = d.collection_id
            WHERE d.path = ?
        """
        params: List[Any] = [path]
        
        if collection:
            sql += " AND c.name = ?"
            params.append(collection)
        
        row = self.conn.execute(sql, params).fetchone()
        
        if row:
            return dict(row)
        return None
    
    def close(self):
        """Close database connection"""
        self.conn.close()
