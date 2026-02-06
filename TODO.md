# localseek TODO

## In Progress

- [ ] Implement `cache.py` — cache management with invalidation
- [ ] Implement `metrics.py` — anonymous logging and metrics
- [ ] Implement `optional/llm_client.py` — HTTP client for LLM server
- [ ] Implement `optional/expand.py` — query expansion
- [ ] Implement `optional/rerank.py` — document reranking

## Open

- [ ] Strip markdown frontmatter from snippets
- [ ] Add phrase search examples to README
- [ ] Add pyproject.toml for pip install
- [ ] Write tests
- [ ] Add `localseek files <collection>` command to list indexed files
- [ ] Add `localseek metrics` command to show search analytics
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
