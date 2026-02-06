# localseek TODO

## Open

- [ ] Strip markdown frontmatter from snippets
- [ ] Add phrase search examples to README
- [ ] Write tests
- [ ] Add `localseek files <collection>` command to list indexed files
- [ ] Add `localseek cache clear` command
- [ ] Consider: graph integration with concept graphs
- [ ] Consider: MCP server for agent integration
- [ ] Consider: watch mode for auto-indexing

## Design Decisions (see ARCHITECTURE.md)

| Decision | Choice |
|----------|--------|
| Rerank candidates | 20 (configurable via `--rerank-topk`) |
| Query expansions | 2 (configurable via `--expand-count`) |
| LLM fallback | Warn and continue with BM25 only |
| Cache invalidation | Document hash based |
| Metrics | Anonymous by default (query hash, not text) |

## Questions to Explore

- How much does BM25 + reranker approach semantic search quality?
- What's the sweet spot for snippet length?
- Should we add synonyms/stemming beyond Porter?
- What's the optimal RRF k value for our corpus size?

## Done

- [x] Core FTS5 indexing
- [x] BM25 search with scoring
- [x] CLI interface (add, search, list, status, remove, get, update)
- [x] JSON output for agent integration
- [x] Multi-collection support
- [x] Tested on 716 documents across 13 collections
- [x] ARCHITECTURE.md with full design documentation
- [x] Cache invalidation strategy designed
- [x] Logging/metrics system designed
- [x] Implement `metrics.py` — anonymous logging and snapshots
- [x] Implement `optional/llm_client.py` — HTTP client for LLM server
- [x] Implement `optional/expand.py` — query expansion with cache
- [x] Implement `optional/rerank.py` — document reranking with position-aware blending
- [x] Add CLI `--expand` and `--rerank` flags
- [x] Add `localseek metrics` command with snapshots
- [x] Add pyproject.toml for pip install
- [x] RELEVANCE-PLAYBOOK.md for improvement workflow
