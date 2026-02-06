# localseek Architecture

## Overview

localseek is a local-first full-text search engine designed for personal knowledge bases. It prioritizes simplicity, zero external dependencies for core functionality, and pluggable enhancements.

## Design Principles

1. **Zero deps for core** — Only Python stdlib (sqlite3)
2. **Pluggable enhancements** — Reranker, expansion as optional
3. **Local-first** — Everything runs on your machine
4. **Learn from usage** — Log queries and results to improve over time
5. **Privacy by default** — No telemetry, no external calls unless explicitly enabled

---

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              localseek                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │    CLI      │────▶│   Search    │────▶│   Index     │                   │
│  │   cli.py    │     │  search.py  │     │  index.py   │                   │
│  └─────────────┘     └──────┬──────┘     └─────────────┘                   │
│                             │                                               │
│                    ┌────────┴────────┐                                     │
│                    ▼                 ▼                                     │
│           ┌─────────────┐    ┌─────────────┐                               │
│           │   Expand    │    │   Rerank    │     OPTIONAL                  │
│           │  expand.py  │    │  rerank.py  │     (requires LLM server)     │
│           └──────┬──────┘    └──────┬──────┘                               │
│                  │                  │                                       │
│                  └────────┬─────────┘                                       │
│                           ▼                                                 │
│                    ┌─────────────┐                                         │
│                    │ LLM Client  │                                         │
│                    │llm_client.py│                                         │
│                    └─────────────┘                                         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                           STORAGE                                           │
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  SQLite DB  │     │    Cache    │     │    Logs     │                   │
│  │  index.db   │     │  cache.db   │     │  metrics.db │                   │
│  └─────────────┘     └─────────────┘     └─────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Main Index (`index.sqlite`)

```sql
-- Collections (folders you index)
CREATE TABLE collections (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    glob_pattern TEXT DEFAULT '**/*.md',
    created_at TEXT,
    updated_at TEXT
);

-- Documents
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER REFERENCES collections(id),
    path TEXT NOT NULL,
    title TEXT,
    content TEXT,
    hash TEXT,  -- MD5 of content, for change detection
    indexed_at TEXT,
    UNIQUE(collection_id, path)
);

-- FTS5 Virtual Table (BM25 search)
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, content,
    content='documents',
    content_rowid='id',
    tokenize='porter unicode61'
);
```

---

## Cache Design

### Cache Database (`cache.sqlite`)

```sql
-- Query expansion cache
CREATE TABLE expansion_cache (
    query_hash TEXT PRIMARY KEY,  -- SHA256 of normalized query
    query TEXT NOT NULL,
    expansions TEXT NOT NULL,     -- JSON array of expanded queries
    model_version TEXT,           -- Track which model generated this
    created_at TEXT,
    hit_count INTEGER DEFAULT 0
);

-- Rerank score cache
CREATE TABLE rerank_cache (
    cache_key TEXT PRIMARY KEY,   -- SHA256(query_hash + doc_hash)
    query_hash TEXT NOT NULL,
    doc_hash TEXT NOT NULL,       -- From documents.hash
    score REAL NOT NULL,
    model_version TEXT,
    created_at TEXT
);

-- Indexes for cleanup
CREATE INDEX idx_expansion_created ON expansion_cache(created_at);
CREATE INDEX idx_rerank_doc ON rerank_cache(doc_hash);
```

### Cache Invalidation Strategy

| Event | Action |
|-------|--------|
| **Document content changes** | `documents.hash` changes → invalidate all `rerank_cache` entries with that `doc_hash` |
| **Document deleted** | Cascade delete from `rerank_cache` |
| **Model version changes** | Optionally invalidate all cache entries with old `model_version` |
| **Manual cache clear** | `localseek cache clear` command |
| **TTL expiry** | Optional: expire entries older than N days |

### Invalidation Flow

```python
def on_document_update(old_hash: str, new_hash: str):
    """Called when a document's content hash changes"""
    if old_hash != new_hash:
        # Invalidate rerank cache for this document
        cache_db.execute(
            "DELETE FROM rerank_cache WHERE doc_hash = ?", 
            (old_hash,)
        )

def on_document_delete(doc_hash: str):
    """Called when a document is deleted"""
    cache_db.execute(
        "DELETE FROM rerank_cache WHERE doc_hash = ?",
        (doc_hash,)
    )

def on_model_change(old_version: str, new_version: str):
    """Called when LLM model changes (optional)"""
    # Could invalidate all, or keep old entries as fallback
    pass
```

### Cache Configuration

```python
# Environment variables
LOCALSEEK_CACHE_ENABLED=true          # Enable/disable cache
LOCALSEEK_CACHE_TTL_DAYS=30           # Expire entries after N days (0=never)
LOCALSEEK_CACHE_MAX_SIZE_MB=100       # Max cache size before pruning
```

---

## Logging & Metrics Design

### Purpose

1. **Debug issues** — What happened during a search?
2. **Learn from patterns** — Which queries work well? Which don't?
3. **Improve over time** — Use logged data to tune parameters
4. **No PII** — Don't log actual query content by default

### Metrics Database (`metrics.sqlite`)

```sql
-- Search events
CREATE TABLE search_events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    query_hash TEXT NOT NULL,      -- SHA256, not the actual query
    query_length INTEGER,
    collection_filter TEXT,        -- NULL if searching all
    result_count INTEGER,
    top_score REAL,
    latency_ms INTEGER,
    used_expansion BOOLEAN,
    used_rerank BOOLEAN,
    cache_hit_expansion BOOLEAN,
    cache_hit_rerank INTEGER,      -- Count of cache hits
    error TEXT                     -- NULL if success
);

-- Optional: detailed query log (opt-in, contains actual queries)
CREATE TABLE query_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    query TEXT NOT NULL,           -- Actual query text
    expansions TEXT,               -- JSON array of expansions
    results TEXT,                  -- JSON array of {path, score}
    feedback INTEGER               -- User rating if provided
);

-- Aggregated metrics (for dashboards)
CREATE TABLE daily_metrics (
    date TEXT PRIMARY KEY,
    total_searches INTEGER,
    avg_latency_ms REAL,
    avg_result_count REAL,
    cache_hit_rate REAL,
    expansion_usage_rate REAL,
    rerank_usage_rate REAL
);
```

### Logging Levels

```python
# Environment variable
LOCALSEEK_LOG_LEVEL=metrics  # Options: off, errors, metrics, debug, full

# off     - No logging
# errors  - Only errors
# metrics - Anonymous metrics (default)
# debug   - Metrics + timing details
# full    - Everything including query text (opt-in)
```

### Metrics Collection

```python
class SearchMetrics:
    def __init__(self):
        self.start_time = time.time()
        self.query_hash = None
        self.used_expansion = False
        self.used_rerank = False
        self.cache_hits = {"expansion": False, "rerank": 0}
        self.result_count = 0
        self.top_score = 0.0
        self.error = None
    
    def record(self, db):
        """Record metrics to database"""
        latency_ms = int((time.time() - self.start_time) * 1000)
        db.execute("""
            INSERT INTO search_events 
            (timestamp, query_hash, result_count, top_score, latency_ms,
             used_expansion, used_rerank, cache_hit_expansion, cache_hit_rerank, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            self.query_hash,
            self.result_count,
            self.top_score,
            latency_ms,
            self.used_expansion,
            self.used_rerank,
            self.cache_hits["expansion"],
            self.cache_hits["rerank"],
            self.error
        ))
```

### Retrieval Quality Improvement Loop

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Continuous Improvement Loop                      │
└─────────────────────────────────────────────────────────────────────┘

     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
     │  Search  │────▶│   Log    │────▶│ Analyze  │────▶│   Tune   │
     │          │     │ Metrics  │     │ Patterns │     │  Params  │
     └──────────┘     └──────────┘     └──────────┘     └──────────┘
           │                                                   │
           └───────────────────────────────────────────────────┘

1. SEARCH: User runs queries
2. LOG: Record latency, scores, cache hits (anonymous by default)
3. ANALYZE: Periodic analysis of metrics
   - Which queries have low top scores? (candidates for expansion)
   - What's the cache hit rate?
   - How much does reranking improve scores?
4. TUNE: Adjust parameters
   - RRF k value
   - Rerank candidate count
   - Expansion prompt
   - Score blending weights
```

### Analysis Queries

```sql
-- Queries with low scores (might need better expansion)
SELECT query_hash, AVG(top_score) as avg_score, COUNT(*) as count
FROM search_events
WHERE used_expansion = 0
GROUP BY query_hash
HAVING avg_score < 3.0
ORDER BY count DESC;

-- Cache effectiveness
SELECT 
    date(timestamp) as day,
    AVG(CASE WHEN cache_hit_expansion THEN 1.0 ELSE 0.0 END) as expansion_hit_rate,
    AVG(cache_hit_rerank * 1.0 / NULLIF(result_count, 0)) as rerank_hit_rate
FROM search_events
GROUP BY day;

-- Rerank impact
SELECT 
    AVG(top_score) FILTER (WHERE used_rerank = 0) as avg_without_rerank,
    AVG(top_score) FILTER (WHERE used_rerank = 1) as avg_with_rerank
FROM search_events;
```

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Storage** | SQLite | Zero deps, good enough for personal use, battle-tested |
| **FTS** | FTS5 with Porter stemmer | Best built-in option, handles English well |
| **Vector search** | Deferred | Overkill for most queries; add later if needed |
| **Rerank candidates** | 20 (configurable) | Balance between recall and latency |
| **Query expansions** | 2 (configurable) | Diminishing returns beyond 2-3 |
| **Score blending** | Position-aware (75/60/40%) | Preserve exact matches while trusting reranker for long tail |
| **Cache invalidation** | Document hash based | Simple, correct, no TTL complexity |
| **Metrics** | Anonymous by default | Privacy-first; opt-in for full logging |
| **LLM fallback** | Warn and continue | Don't break search if LLM unavailable |

---

## Configuration Reference

```bash
# Core
LOCALSEEK_DB_PATH=~/.cache/localseek/index.sqlite

# LLM Integration
LOCALSEEK_LLM_URL=http://localhost:8000
LOCALSEEK_LLM_TIMEOUT=30

# Query Expansion
LOCALSEEK_EXPAND_ENABLED=true
LOCALSEEK_EXPAND_COUNT=2
LOCALSEEK_EXPAND_CACHE=true

# Reranking
LOCALSEEK_RERANK_ENABLED=true
LOCALSEEK_RERANK_TOPK=20
LOCALSEEK_RERANK_CACHE=true

# Logging
LOCALSEEK_LOG_LEVEL=metrics   # off|errors|metrics|debug|full
LOCALSEEK_METRICS_DB=~/.cache/localseek/metrics.sqlite

# Cache
LOCALSEEK_CACHE_ENABLED=true
LOCALSEEK_CACHE_DB=~/.cache/localseek/cache.sqlite
LOCALSEEK_CACHE_TTL_DAYS=30
```

---

## File Structure (Complete)

```
localseek/
├── README.md
├── ARCHITECTURE.md          # This file
├── LICENSE                  # MIT
├── TODO.md
├── pyproject.toml          # For pip install
├── .gitignore
│
├── localseek/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # Command line interface
│   ├── config.py           # Configuration management
│   ├── index.py            # FTS5 indexing
│   ├── search.py           # BM25 search + RRF fusion
│   ├── cache.py            # Cache management
│   ├── metrics.py          # Logging and metrics
│   │
│   └── optional/
│       ├── __init__.py
│       ├── llm_client.py   # HTTP client for LLM server
│       ├── expand.py       # Query expansion
│       └── rerank.py       # Document reranking
│
├── tests/
│   ├── test_index.py
│   ├── test_search.py
│   └── test_cache.py
│
└── examples/
    ├── basic_usage.py
    └── with_reranking.py
```

---

## Security & Privacy

- **No external calls** — Core functionality works offline
- **Optional LLM** — Only connects to localhost by default
- **Anonymous metrics** — Query hashes, not query text
- **No telemetry** — Nothing leaves your machine
- **Local storage** — All data in `~/.cache/localseek/`

---

## Future Considerations

1. **Vector search** — Add embeddings if FTS5 + expansion isn't enough
2. **Feedback loop** — Allow users to rate results, use for tuning
3. **MCP server** — Expose as Model Context Protocol for agent integration
4. **Watch mode** — Auto-index on file changes
5. **Web UI** — Simple search interface (optional)
