# localseek

A lightweight, local-first full-text search engine for your documents. Zero external dependencies beyond Python's standard library.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

## Features

- **SQLite FTS5** — Fast, battle-tested full-text search with BM25 ranking
- **Zero dependencies** — Uses Python's built-in sqlite3
- **Collection-based** — Index multiple folders separately
- **CLI-first** — Simple command-line interface
- **Agent-friendly** — JSON output for LLM integrations
- **Pluggable** — Optional reranker and query expansion modules
- **Privacy-first** — Everything runs locally, no external calls

## Quick Start

```bash
# Index a folder
python -m localseek add ./notes --name notes

# Search
python -m localseek search "decision making"

# JSON output (for agents)
python -m localseek search "mental models" --json

# List collections
python -m localseek list

# Status
python -m localseek status
```

## Installation

```bash
# Clone the repo
git clone https://github.com/caprion/localseek.git
cd localseek

# No dependencies needed for core functionality!
pip install -e .

# Optional: with LLM integration support
pip install -e ".[llm]"
```

## Usage

### Indexing

```bash
# Add a collection (default: **/*.md files)
localseek add ~/Documents/notes --name notes

# Custom glob pattern
localseek add ~/code/docs --name docs --glob "**/*.{md,txt,rst}"

# Re-index all collections
localseek update
```

### Searching

```bash
# Basic search
localseek search "machine learning"

# Limit results
localseek search "python async" --limit 5

# Search specific collection
localseek search "API design" --collection docs

# JSON output for scripting/agents
localseek search "authentication" --json
```

### With LLM Enhancement (Optional)

```bash
# Query expansion (generates alternative phrasings)
localseek search "how to think better" --expand

# Reranking (LLM scores relevance)
localseek search "best practices" --rerank

# Full pipeline
localseek search "design patterns" --expand --rerank

# Requires a local LLM server (e.g., llama.cpp, Ollama)
export LOCALSEEK_LLM_URL=http://localhost:8000
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     localseek                           │
├─────────────────────────────────────────────────────────┤
│  CLI (cli.py)                                           │
│    ↓                                                    │
│  Search Engine (search.py)                              │
│    ↓                                                    │
│  Indexer (index.py)                                     │
│    ↓                                                    │
│  SQLite + FTS5                                          │
├─────────────────────────────────────────────────────────┤
│  Optional Modules:                                      │
│  - Query Expansion (expand.py)                          │
│  - Reranker (rerank.py)                                 │
└─────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

## Why not vectors?

Vectors are overrated for most local search use cases:

| Use Case | FTS5 | Vectors |
|----------|------|---------|
| Keyword search | ✅ Perfect | ❌ Overkill |
| Known terminology | ✅ Works | ❌ No benefit |
| Semantic similarity | ⚠️ Needs expansion | ✅ Good |
| Resource usage | ~30MB | ~500MB+ |

Start with FTS5 + optional query expansion. Add vectors only if you hit a wall.

## Benchmarks

Tested on a personal knowledge base:

| Metric | Value |
|--------|-------|
| Documents indexed | 716 |
| Collections | 13 |
| Database size | 32 MB |
| Index time | <2 seconds |
| Search latency | <100ms |
| Memory usage | ~15 MB |

## Configuration

Environment variables:

```bash
# Core
LOCALSEEK_DB_PATH=~/.cache/localseek/index.sqlite

# LLM Integration (optional)
LOCALSEEK_LLM_URL=http://localhost:8000
LOCALSEEK_EXPAND_COUNT=2        # Number of query expansions
LOCALSEEK_RERANK_TOPK=20        # Candidates for reranking

# Logging
LOCALSEEK_LOG_LEVEL=metrics     # off|errors|metrics|debug|full
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Related Projects

- [QMD](https://github.com/tobi/qmd) — Full-featured search with embeddings
- [ripgrep](https://github.com/BurntSushi/ripgrep) — Fast grep alternative
- [fzf](https://github.com/junegunn/fzf) — Fuzzy finder

## License

MIT
