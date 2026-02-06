"""
Query expansion module for localseek

Uses a local LLM to generate alternative phrasings of a query.
"""

import hashlib
import sys
from typing import List, Optional, Tuple

from ..config import get_config
from .llm_client import get_llm_client


EXPANSION_PROMPT = """Generate {count} alternative search queries for the given query. 
Output only the queries, one per line. No numbering, no explanation, no quotes.
Keep them concise and focused on the same intent."""


def expand_query(
    query: str,
    count: Optional[int] = None,
    cache: Optional["ExpansionCache"] = None,
) -> Tuple[List[str], bool]:
    """
    Expand a query into multiple alternative phrasings
    
    Args:
        query: Original search query
        count: Number of expansions to generate (default from config)
        cache: Optional cache instance
    
    Returns:
        Tuple of (list of queries including original, cache_hit)
        First item is always the original query
    """
    config = get_config()
    count = count or config.expand_count
    
    # Check cache first
    query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
    if cache:
        cached = cache.get(query_hash)
        if cached:
            return [query] + cached, True
    
    # Call LLM
    client = get_llm_client()
    if not client.is_available():
        print("Warning: LLM server not available, skipping query expansion", 
              file=sys.stderr)
        return [query], False
    
    response = client.chat(
        messages=[
            {"role": "system", "content": EXPANSION_PROMPT.format(count=count)},
            {"role": "user", "content": f"Query: {query}"},
        ],
        max_tokens=100,
        temperature=0.7,
    )
    
    if not response:
        return [query], False
    
    # Parse expansions
    expansions = []
    for line in response.strip().split("\n"):
        line = line.strip()
        # Remove common prefixes like "1.", "- ", etc.
        if line and len(line) > 2:
            if line[0].isdigit() and line[1] in ".):":
                line = line[2:].strip()
            elif line[0] in "-•*":
                line = line[1:].strip()
            if line and line.lower() != query.lower():
                expansions.append(line)
    
    # Limit to requested count
    expansions = expansions[:count]
    
    # Cache the result
    if cache and expansions:
        cache.set(query_hash, query, expansions)
    
    return [query] + expansions, False


class ExpansionCache:
    """Cache for query expansions"""
    
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
            CREATE TABLE IF NOT EXISTS expansion_cache (
                query_hash TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                expansions TEXT NOT NULL,
                model_version TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_expansion_created 
            ON expansion_cache(created_at);
        """)
        self.conn.commit()
    
    def get(self, query_hash: str) -> Optional[List[str]]:
        """Get cached expansions"""
        import json
        
        row = self.conn.execute(
            "SELECT expansions FROM expansion_cache WHERE query_hash = ?",
            (query_hash,)
        ).fetchone()
        
        if row:
            # Update hit count
            self.conn.execute(
                "UPDATE expansion_cache SET hit_count = hit_count + 1 WHERE query_hash = ?",
                (query_hash,)
            )
            self.conn.commit()
            return json.loads(row["expansions"])
        
        return None
    
    def set(self, query_hash: str, query: str, expansions: List[str]):
        """Cache expansions"""
        import json
        from datetime import datetime
        
        self.conn.execute(
            """INSERT OR REPLACE INTO expansion_cache 
               (query_hash, query, expansions, created_at)
               VALUES (?, ?, ?, ?)""",
            (query_hash, query, json.dumps(expansions), datetime.now().isoformat())
        )
        self.conn.commit()
    
    def clear(self):
        """Clear all cached expansions"""
        self.conn.execute("DELETE FROM expansion_cache")
        self.conn.commit()
    
    def close(self):
        self.conn.close()
