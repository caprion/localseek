# Relevance Improvement Playbook

A practical guide to improving search quality in localseek.

## The Improvement Loop

```
┌─────────────────────────────────────────────────────────────┐
│  1. MEASURE → 2. IDENTIFY → 3. HYPOTHESIZE → 4. TEST → 5. COMPARE  │
│       ↑                                                      │
│       └──────────────────────────────────────────────────────┘
```

### Step 1: Measure (Baseline)

Take a snapshot before making changes:

```bash
localseek metrics --snapshot "baseline before expansion"
```

Run representative queries and look at:
- **Avg top score**: Are the best results scoring well? (<3.0 is concerning)
- **Low-score queries**: Which queries are struggling?
- **Result count**: Are queries returning enough results?

### Step 2: Identify Problem Patterns

Check low-scoring queries:

```bash
localseek metrics --json | jq '.low_score_queries'
```

Common patterns:
| Symptom | Likely Cause |
|---------|--------------|
| Conceptual queries score low | Need query expansion |
| Top result isn't best match | Need reranking |
| Good doc exists but not found | Vocabulary mismatch |
| Too many irrelevant results | Need stricter min-score |

### Step 3: Hypothesize & Configure

**Hypothesis: Query expansion will help conceptual queries**
```bash
# Test with expansion
localseek search "machine learning concepts" --expand
```

**Hypothesis: Reranking will improve result order**
```bash
# Test with reranking
localseek search "how to debug" --rerank
```

**Hypothesis: Both together**
```bash
localseek search "productivity tips at work" --expand --rerank
```

### Step 4: Test Systematically

Create a test set of 10-20 queries covering:
- Exact matches (should score high: 10+)
- Partial matches (should score 3-8)
- Conceptual queries (may need expansion)
- Natural language questions (may need reranking)

```bash
# Run each query and record scores
localseek search "exact phrase from doc" --json | jq '.results[0].score'
```

### Step 5: Compare Snapshots

After testing with new settings:

```bash
localseek metrics --snapshot "after enabling expansion"
localseek metrics --compare 1,2
```

Look for:
- ↑ Avg top score improvement
- ↓ Low-score query count reduction
- ↓ Latency acceptable (expansion adds ~100-500ms)

---

## Improvement Strategies

### Strategy A: Enable Query Expansion

**When**: Conceptual or natural language queries underperform

```bash
# Enable for searches
localseek search "how to be productive" --expand

# Tune expansion count (default: 2)
localseek search "how to be productive" --expand --expand-count 3
```

**Expected**: +0.5 to +2.0 avg score improvement on conceptual queries

### Strategy B: Enable Reranking

**When**: Best results exist but aren't ranked first

```bash
# Enable reranking
localseek search "debugging techniques" --rerank

# Tune candidate pool (default: 20)
localseek search "debugging techniques" --rerank --rerank-topk 30
```

**Expected**: First result quality improves, slight latency cost

### Strategy C: Adjust BM25 Parameters

The FTS5 BM25 uses k1=1.2 and b=0.75 by default. These are baked into SQLite but the score interpretation matters:

| Score Range | Quality |
|-------------|---------|
| 15+ | Excellent match |
| 8-15 | Good match |
| 3-8 | Partial match |
| <3 | Poor/marginal |

**Action**: Adjust `--min-score` threshold to filter noise:

```bash
localseek search "query" --min-score 3.0
```

### Strategy D: Improve Content Quality

Sometimes the issue is the indexed content:

1. **Check document length**: Very short docs may score poorly
2. **Add metadata**: Titles, tags in document headers
3. **Structure content**: Use headings (they're weighted equally, but help expansion prompts)

### Strategy E: Collection-Specific Search

If some collections have higher quality:

```bash
localseek search "topic" --collection high-quality-notes
```

---

## Diagnostic Commands

### Quick health check
```bash
localseek status
localseek metrics
```

### Find problematic queries
```bash
localseek metrics --json | jq '.low_score_queries[] | select(.avg_score < 2)'
```

### Compare before/after
```bash
localseek metrics --compare 1,2 --json
```

### Test LLM availability
```bash
# If expansion/rerank fails silently, check:
curl http://localhost:8000/health
```

---

## Tuning Knobs Reference

| Flag | Default | Range | Effect |
|------|---------|-------|--------|
| `--expand` | off | on/off | Query expansion via LLM |
| `--expand-count` | 2 | 1-5 | More = broader recall, slower |
| `--rerank` | off | on/off | Semantic reranking |
| `--rerank-topk` | 20 | 5-50 | More = better selection, slower |
| `--min-score` | 0.0 | 0-20 | Higher = stricter filtering |
| `--limit` | 10 | 1-100 | Results returned |

---

## Expected Improvements

After enabling both expansion and reranking:

| Metric | Baseline | Optimized | Change |
|--------|----------|-----------|--------|
| Avg top score | 5.2 | 7.8 | +50% |
| Low-score queries | 12 | 4 | -67% |
| Avg latency | 15ms | 180ms | +12x |

**Trade-off**: Latency increases significantly with LLM calls. Use `--expand --rerank` for important queries, plain search for quick lookups.

---

## Continuous Improvement Workflow

1. **Weekly**: Review `localseek metrics` for trends
2. **After major indexing**: Take a snapshot
3. **Before config changes**: Take a baseline snapshot
4. **After config changes**: Compare with baseline
5. **Monthly**: Review low-score queries, consider content improvements
