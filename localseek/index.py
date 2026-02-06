"""
FTS5 Indexer for localseek

Handles document indexing with SQLite FTS5 for full-text search.
"""

import sqlite3
import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import re


# Default database location
DEFAULT_DB_PATH = Path.home() / ".cache" / "localseek" / "index.sqlite"


def get_db_path() -> Path:
    """Get database path, respecting XDG_CACHE_HOME"""
    cache_home = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(cache_home) / "localseek" / "index.sqlite"


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Initialize database with schema"""
    db_path = db_path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Create schema
    conn.executescript("""
        -- Collections (folders you index)
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            glob_pattern TEXT DEFAULT '**/*.md',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Documents
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            title TEXT,
            content TEXT,
            hash TEXT,
            indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(collection_id, path)
        );
        
        -- FTS5 Virtual Table
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            title,
            content,
            content='documents',
            content_rowid='id',
            tokenize='porter unicode61'
        );
        
        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, content) 
            VALUES (new.id, new.title, new.content);
        END;
        
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content) 
            VALUES ('delete', old.id, old.title, old.content);
        END;
        
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content) 
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO documents_fts(rowid, title, content) 
            VALUES (new.id, new.title, new.content);
        END;
    """)
    
    conn.commit()
    return conn


class Indexer:
    """Document indexer using SQLite FTS5"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self.conn = init_db(self.db_path)
    
    def add_collection(
        self, 
        path: str, 
        name: str, 
        glob_pattern: str = "**/*.md"
    ) -> int:
        """Add a new collection and index its documents"""
        abs_path = str(Path(path).resolve())
        
        # Check if collection exists
        existing = self.conn.execute(
            "SELECT id FROM collections WHERE name = ?", (name,)
        ).fetchone()
        
        if existing:
            # Update existing collection
            self.conn.execute(
                """UPDATE collections 
                   SET path = ?, glob_pattern = ?, updated_at = ?
                   WHERE name = ?""",
                (abs_path, glob_pattern, datetime.now().isoformat(), name)
            )
            collection_id = existing["id"]
        else:
            # Create new collection
            cursor = self.conn.execute(
                """INSERT INTO collections (name, path, glob_pattern)
                   VALUES (?, ?, ?)""",
                (name, abs_path, glob_pattern)
            )
            collection_id = cursor.lastrowid
        
        self.conn.commit()
        
        # Index documents
        indexed = self.index_collection(collection_id)
        return indexed
    
    def index_collection(self, collection_id: int) -> int:
        """Index all documents in a collection"""
        collection = self.conn.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")
        
        base_path = Path(collection["path"])
        glob_pattern = collection["glob_pattern"]
        
        # Get existing documents
        existing = {
            row["path"]: row["hash"]
            for row in self.conn.execute(
                "SELECT path, hash FROM documents WHERE collection_id = ?",
                (collection_id,)
            ).fetchall()
        }
        
        indexed_count = 0
        seen_paths = set()
        
        # Find and index files
        for file_path in base_path.glob(glob_pattern):
            if not file_path.is_file():
                continue
            
            rel_path = str(file_path.relative_to(base_path))
            seen_paths.add(rel_path)
            
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Skip {rel_path}: {e}")
                continue
            
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Skip if unchanged
            if rel_path in existing and existing[rel_path] == content_hash:
                continue
            
            # Extract title
            title = self._extract_title(content, file_path.stem)
            
            # Upsert document
            self.conn.execute(
                """INSERT INTO documents (collection_id, path, title, content, hash, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(collection_id, path) DO UPDATE SET
                       title = excluded.title,
                       content = excluded.content,
                       hash = excluded.hash,
                       indexed_at = excluded.indexed_at""",
                (collection_id, rel_path, title, content, content_hash, 
                 datetime.now().isoformat())
            )
            indexed_count += 1
        
        # Remove deleted documents
        for old_path in existing.keys() - seen_paths:
            self.conn.execute(
                "DELETE FROM documents WHERE collection_id = ? AND path = ?",
                (collection_id, old_path)
            )
        
        self.conn.commit()
        return indexed_count
    
    def _extract_title(self, content: str, fallback: str) -> str:
        """Extract title from markdown content"""
        # Try to find first H1
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # Try frontmatter title
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end]
                title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', 
                                        frontmatter, re.MULTILINE)
                if title_match:
                    return title_match.group(1).strip()
        
        # Use filename
        return fallback.replace("-", " ").replace("_", " ").title()
    
    def remove_collection(self, name: str) -> bool:
        """Remove a collection and its documents"""
        cursor = self.conn.execute(
            "DELETE FROM collections WHERE name = ?", (name,)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections with document counts"""
        rows = self.conn.execute("""
            SELECT c.*, COUNT(d.id) as doc_count
            FROM collections c
            LEFT JOIN documents d ON d.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.name
        """).fetchall()
        return [dict(row) for row in rows]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        collections = self.conn.execute(
            "SELECT COUNT(*) as count FROM collections"
        ).fetchone()["count"]
        
        documents = self.conn.execute(
            "SELECT COUNT(*) as count FROM documents"
        ).fetchone()["count"]
        
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        return {
            "collections": collections,
            "documents": documents,
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "db_path": str(self.db_path)
        }
    
    def update_all(self) -> Dict[str, int]:
        """Re-index all collections"""
        results = {}
        for collection in self.list_collections():
            results[collection["name"]] = self.index_collection(collection["id"])
        return results
    
    def close(self):
        """Close database connection"""
        self.conn.close()
