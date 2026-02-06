"""
Metrics and logging for localseek

Provides anonymous metrics collection for improving search quality.
"""

import sqlite3
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from .config import get_config


@dataclass
class SearchMetrics:
    """Metrics for a single search operation"""
    
    query_hash: str = ""
    query_length: int = 0
    collection_filter: Optional[str] = None
    result_count: int = 0
    top_score: float = 0.0
    used_expansion: bool = False
    used_rerank: bool = False
    cache_hit_expansion: bool = False
    cache_hit_rerank: int = 0
    error: Optional[str] = None
    
    _start_time: float = field(default_factory=time.time)
    
    @classmethod
    def start(cls, query: str, collection: Optional[str] = None) -> "SearchMetrics":
        """Start tracking a new search"""
        return cls(
            query_hash=hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16],
            query_length=len(query),
            collection_filter=collection,
            _start_time=time.time(),
        )
    
    def finish(
        self,
        results: List[Any],
        used_expansion: bool = False,
        used_rerank: bool = False,
        cache_hit_expansion: bool = False,
        cache_hit_rerank: int = 0,
    ):
        """Finish tracking with results"""
        self.result_count = len(results)
        if results:
            # Handle both SearchResult (score) and RerankResult (blended_score)
            first = results[0]
            self.top_score = getattr(first, "blended_score", getattr(first, "score", 0.0))
        else:
            self.top_score = 0.0
        self.used_expansion = used_expansion
        self.used_rerank = used_rerank
        self.cache_hit_expansion = cache_hit_expansion
        self.cache_hit_rerank = cache_hit_rerank
    
    @property
    def latency_ms(self) -> int:
        return int((time.time() - self._start_time) * 1000)


class MetricsDB:
    """Database for storing search metrics"""
    
    def __init__(self, db_path: Optional[Path] = None):
        config = get_config()
        self.db_path = db_path or config.metrics_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_level = config.log_level
        
        if self.log_level == "off":
            self.conn = None
        else:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            self._init_schema()
    
    def _init_schema(self):
        if not self.conn:
            return
            
        self.conn.executescript("""
            -- Search events (anonymous)
            CREATE TABLE IF NOT EXISTS search_events (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                query_hash TEXT NOT NULL,
                query_length INTEGER,
                collection_filter TEXT,
                result_count INTEGER,
                top_score REAL,
                latency_ms INTEGER,
                used_expansion BOOLEAN,
                used_rerank BOOLEAN,
                cache_hit_expansion BOOLEAN,
                cache_hit_rerank INTEGER,
                error TEXT
            );
            
            -- Optional: detailed query log (opt-in with log_level=full)
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                expansions TEXT,
                results TEXT,
                feedback INTEGER
            );
            
            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_events_timestamp 
            ON search_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_hash 
            ON search_events(query_hash);
        """)
        self.conn.commit()
    
    def record(self, metrics: SearchMetrics):
        """Record search metrics"""
        if not self.conn or self.log_level == "off":
            return
        
        if self.log_level == "errors" and not metrics.error:
            return
        
        self.conn.execute("""
            INSERT INTO search_events 
            (timestamp, query_hash, query_length, collection_filter,
             result_count, top_score, latency_ms,
             used_expansion, used_rerank, cache_hit_expansion, cache_hit_rerank, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            metrics.query_hash,
            metrics.query_length,
            metrics.collection_filter,
            metrics.result_count,
            metrics.top_score,
            metrics.latency_ms,
            metrics.used_expansion,
            metrics.used_rerank,
            metrics.cache_hit_expansion,
            metrics.cache_hit_rerank,
            metrics.error,
        ))
        self.conn.commit()
    
    def record_query(
        self, 
        query: str, 
        expansions: Optional[List[str]] = None,
        results: Optional[List[Dict]] = None,
        feedback: Optional[int] = None
    ):
        """Record detailed query log (only if log_level=full)"""
        if not self.conn or self.log_level != "full":
            return
        
        import json
        
        self.conn.execute("""
            INSERT INTO query_log (timestamp, query, expansions, results, feedback)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            query,
            json.dumps(expansions) if expansions else None,
            json.dumps(results) if results else None,
            feedback,
        ))
        self.conn.commit()
    
    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get aggregated metrics"""
        if not self.conn:
            return {"logging": "disabled"}
        
        from_date = datetime.now().isoformat()[:10]  # Simplified
        
        row = self.conn.execute("""
            SELECT 
                COUNT(*) as total_searches,
                AVG(latency_ms) as avg_latency_ms,
                AVG(result_count) as avg_result_count,
                AVG(top_score) as avg_top_score,
                SUM(CASE WHEN used_expansion THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as expansion_rate,
                SUM(CASE WHEN used_rerank THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as rerank_rate,
                SUM(CASE WHEN cache_hit_expansion THEN 1 ELSE 0 END) * 100.0 / 
                    NULLIF(SUM(CASE WHEN used_expansion THEN 1 ELSE 0 END), 0) as expansion_cache_rate,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM search_events
        """).fetchone()
        
        return {
            "total_searches": row["total_searches"],
            "avg_latency_ms": round(row["avg_latency_ms"] or 0, 1),
            "avg_result_count": round(row["avg_result_count"] or 0, 1),
            "avg_top_score": round(row["avg_top_score"] or 0, 2),
            "expansion_usage_rate": round(row["expansion_rate"] or 0, 1),
            "rerank_usage_rate": round(row["rerank_rate"] or 0, 1),
            "expansion_cache_hit_rate": round(row["expansion_cache_rate"] or 0, 1),
            "error_count": row["error_count"],
        }
    
    def get_low_score_queries(self, threshold: float = 3.0, limit: int = 10) -> List[Dict]:
        """Get queries with low top scores (candidates for improvement)"""
        if not self.conn:
            return []
        
        rows = self.conn.execute("""
            SELECT query_hash, 
                   AVG(top_score) as avg_score, 
                   COUNT(*) as count,
                   AVG(latency_ms) as avg_latency
            FROM search_events
            WHERE top_score > 0
            GROUP BY query_hash
            HAVING avg_score < ?
            ORDER BY count DESC
            LIMIT ?
        """, (threshold, limit)).fetchall()
        
        return [dict(row) for row in rows]
    
    def save_snapshot(self, note: Optional[str] = None) -> int:
        """Save a metrics snapshot for tracking improvements over time"""
        if not self.conn:
            return -1
        
        # Ensure snapshots table exists
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                note TEXT,
                total_searches INTEGER,
                avg_latency_ms REAL,
                avg_result_count REAL,
                avg_top_score REAL,
                expansion_usage_rate REAL,
                rerank_usage_rate REAL,
                cache_hit_rate REAL,
                error_count INTEGER,
                config_expand_count INTEGER,
                config_rerank_topk INTEGER,
                low_score_query_count INTEGER
            )
        """)
        
        stats = self.get_stats()
        low_score = self.get_low_score_queries()
        config = get_config()
        
        cursor = self.conn.execute("""
            INSERT INTO metrics_snapshots 
            (timestamp, note, total_searches, avg_latency_ms, avg_result_count,
             avg_top_score, expansion_usage_rate, rerank_usage_rate, cache_hit_rate,
             error_count, config_expand_count, config_rerank_topk, low_score_query_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            note,
            stats.get("total_searches", 0),
            stats.get("avg_latency_ms", 0),
            stats.get("avg_result_count", 0),
            stats.get("avg_top_score", 0),
            stats.get("expansion_usage_rate", 0),
            stats.get("rerank_usage_rate", 0),
            stats.get("expansion_cache_hit_rate", 0),
            stats.get("error_count", 0),
            config.expand_count,
            config.rerank_topk,
            len(low_score),
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_snapshots(self, limit: int = 10) -> List[Dict]:
        """Get recent snapshots for comparison"""
        if not self.conn:
            return []
        
        try:
            rows = self.conn.execute("""
                SELECT * FROM metrics_snapshots
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []  # Table doesn't exist yet
    
    def compare_snapshots(self, snapshot_id_1: int, snapshot_id_2: int) -> Dict[str, Any]:
        """Compare two snapshots to see improvements"""
        if not self.conn:
            return {}
        
        try:
            s1 = self.conn.execute(
                "SELECT * FROM metrics_snapshots WHERE id = ?", (snapshot_id_1,)
            ).fetchone()
            s2 = self.conn.execute(
                "SELECT * FROM metrics_snapshots WHERE id = ?", (snapshot_id_2,)
            ).fetchone()
            
            if not s1 or not s2:
                return {"error": "Snapshot not found"}
            
            return {
                "from": {"id": s1["id"], "timestamp": s1["timestamp"], "note": s1["note"]},
                "to": {"id": s2["id"], "timestamp": s2["timestamp"], "note": s2["note"]},
                "changes": {
                    "avg_top_score": round((s2["avg_top_score"] or 0) - (s1["avg_top_score"] or 0), 3),
                    "avg_latency_ms": round((s2["avg_latency_ms"] or 0) - (s1["avg_latency_ms"] or 0), 1),
                    "low_score_queries": (s2["low_score_query_count"] or 0) - (s1["low_score_query_count"] or 0),
                    "expansion_usage": round((s2["expansion_usage_rate"] or 0) - (s1["expansion_usage_rate"] or 0), 1),
                    "rerank_usage": round((s2["rerank_usage_rate"] or 0) - (s1["rerank_usage_rate"] or 0), 1),
                }
            }
        except sqlite3.OperationalError:
            return {"error": "Snapshots table not found"}
    
    def close(self):
        if self.conn:
            self.conn.close()


# Singleton instance
_metrics_db: Optional[MetricsDB] = None


def get_metrics_db() -> MetricsDB:
    """Get or create the global metrics database"""
    global _metrics_db
    if _metrics_db is None:
        _metrics_db = MetricsDB()
    return _metrics_db
