"""
CLI interface for localseek

Usage:
    python -m localseek add <path> --name <name>
    python -m localseek search <query>
    python -m localseek search <query> --expand --rerank
    python -m localseek metrics
    python -m localseek metrics --snapshot "description"
    python -m localseek list
    python -m localseek status
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

from .index import Indexer
from .search import Searcher
from .metrics import get_metrics_db, SearchMetrics


def cmd_add(args):
    """Add a collection"""
    indexer = Indexer()
    try:
        path = Path(args.path).resolve()
        if not path.exists():
            print(f"Error: Path does not exist: {path}", file=sys.stderr)
            return 1
        
        name = args.name or path.name
        glob_pattern = args.glob or "**/*.md"
        
        print(f"Indexing {path} as '{name}'...")
        count = indexer.add_collection(str(path), name, glob_pattern)
        print(f"Indexed {count} documents")
        return 0
    finally:
        indexer.close()


def cmd_search(args):
    """Search documents with optional LLM enhancement"""
    searcher = Searcher()
    metrics_db = get_metrics_db()
    metrics = SearchMetrics.start(args.query, args.collection)
    
    try:
        # Track enhancement options
        use_expand = getattr(args, 'expand', False)
        use_rerank = getattr(args, 'rerank', False)
        cache_hit_expansion = False
        cache_hit_rerank = 0
        
        # Get base results (possibly with expansion)
        queries = [args.query]
        
        if use_expand:
            try:
                from .optional.expand import expand_query, ExpansionCache
                cache = ExpansionCache() if args.cache else None
                queries, cache_hit_expansion = expand_query(
                    args.query, 
                    count=args.expand_count,
                    cache=cache
                )
                if len(queries) > 1:
                    print(f"Expanded to {len(queries)} queries: {queries}", file=sys.stderr)
            except ImportError:
                print("Warning: Expansion module not available", file=sys.stderr)
        
        # Search with all queries and merge (RRF)
        all_results = []
        for q in queries:
            results = searcher.search(
                query=q,
                collection=args.collection,
                limit=args.limit * 2 if use_rerank else args.limit,
                min_score=args.min_score
            )
            all_results.extend(results)
        
        # Dedupe and RRF merge if multiple queries
        if len(queries) > 1:
            results = _rrf_merge(all_results, queries, args.limit * 2 if use_rerank else args.limit)
        else:
            results = all_results[:args.limit * 2 if use_rerank else args.limit]
        
        # Rerank if requested
        if use_rerank and results:
            try:
                from .optional.rerank import rerank_results, RerankCache
                cache = RerankCache() if args.cache else None
                
                # Convert to dicts for reranker
                result_dicts = [r.to_dict() for r in results]
                reranked, cache_hit_rerank = rerank_results(
                    args.query,
                    result_dicts,
                    topk=args.rerank_topk,
                    cache=cache
                )
                
                # Use reranked results
                if reranked:
                    results = reranked[:args.limit]
                    
            except ImportError:
                print("Warning: Rerank module not available", file=sys.stderr)
        else:
            results = results[:args.limit]
        
        # Fetch web results if requested
        use_fetch = getattr(args, 'fetch', False)
        web_results = []
        if use_fetch:
            try:
                from .optional.web_search import fetch_web_results
                fetch_count = getattr(args, 'fetch_count', 3)
                web_results = fetch_web_results(args.query, max_results=fetch_count)
                if web_results:
                    print(f"Fetched {len(web_results)} web results", file=sys.stderr)
            except ImportError:
                print("Warning: Web search module not available", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Web search failed: {e}", file=sys.stderr)
        
        # Record metrics
        metrics.finish(
            results=results,
            used_expansion=use_expand,
            used_rerank=use_rerank,
            cache_hit_expansion=cache_hit_expansion,
            cache_hit_rerank=cache_hit_rerank,
        )
        metrics_db.record(metrics)
        
        # Prepare summary if requested
        use_summarize = getattr(args, 'summarize', False)
        summary = None
        if use_summarize:
            try:
                from .optional.summarize import summarize_with_context
                
                # Convert results to dicts for summarizer
                result_dicts = []
                for r in results:
                    if hasattr(r, 'to_dict'):
                        result_dicts.append(r.to_dict())
                    elif hasattr(r, 'blended_score'):
                        result_dicts.append({
                            "title": r.title,
                            "snippet": r.snippet,
                            "score": r.blended_score,
                            "path": r.path,
                        })
                    else:
                        result_dicts.append(r)
                
                summary = summarize_with_context(
                    args.query, 
                    result_dicts,
                    expanded_queries=queries if use_expand and len(queries) > 1 else None,
                    web_results=web_results if web_results else None,
                )
                    
            except ImportError:
                print("Warning: Summarize module not available", file=sys.stderr)
        
        # Output
        if args.json:
            if use_rerank and results and hasattr(results[0], 'blended_score'):
                output = {
                    "query": args.query,
                    "expanded_queries": queries if use_expand else None,
                    "count": len(results),
                    "used_expansion": use_expand,
                    "used_rerank": use_rerank,
                    "summary": summary,
                    "results": [{
                        "path": r.path,
                        "title": r.title,
                        "snippet": r.snippet,
                        "original_score": r.original_score,
                        "rerank_score": r.rerank_score,
                        "blended_score": r.blended_score,
                        "collection": r.collection,
                    } for r in results],
                    "web_results": web_results if web_results else None,
                }
            else:
                output = {
                    "query": args.query,
                    "expanded_queries": queries if use_expand else None,
                    "count": len(results),
                    "summary": summary,
                    "results": [r.to_dict() if hasattr(r, 'to_dict') else r for r in results],
                    "web_results": web_results if web_results else None,
                }
            print(json.dumps(output, indent=2))
        else:
            if not results and not web_results:
                print("No results found.")
                return 0
            
            # Local results
            if results:
                print("\n=== Local Documents ===")
                for i, r in enumerate(results, 1):
                    if hasattr(r, 'blended_score'):  # Reranked result
                        print(f"\n{r.collection}/{r.path}")
                        print(f"  Title: {r.title}")
                        print(f"  Score: {r.blended_score:.3f} (BM25: {r.original_score:.2f}, Rerank: {r.rerank_score:.1f})")
                        print(f"  {r.snippet}")
                    else:
                        print(f"\n{r.collection}/{r.path}")
                        print(f"  Title: {r.title}")
                        print(f"  Score: {r.score:.3f}")
                        print(f"  {r.snippet}")
            
            # Web results
            if web_results:
                print("\n=== Web Results ===")
                for i, r in enumerate(web_results, 1):
                    print(f"\n[{i}] {r.get('title', 'Untitled')}")
                    print(f"    {r.get('url', '')}")
                    if r.get('snippet'):
                        print(f"    {r.get('snippet', '')[:150]}...")
            
            # Print summary at the end for text output
            if summary:
                print("\n" + "=" * 60)
                print("SUMMARY")
                print("=" * 60)
                print(summary)
            elif use_summarize:
                print("\n(LLM not available for summarization)")
        
        return 0
    except Exception as e:
        metrics.error = str(e)
        metrics_db.record(metrics)
        raise
    finally:
        searcher.close()


def _rrf_merge(results: List, queries: List[str], limit: int) -> List:
    """Merge results from multiple queries using Reciprocal Rank Fusion"""
    from collections import defaultdict
    
    # RRF with k=60
    k = 60
    scores = defaultdict(float)
    result_map = {}
    
    # Group by query and assign ranks
    for i, r in enumerate(results):
        key = f"{r.collection}:{r.path}" if hasattr(r, 'collection') else r.get('path', str(i))
        rank = (i % (len(results) // len(queries) + 1)) + 1  # Approximate rank
        scores[key] += 1.0 / (k + rank)
        if key not in result_map:
            result_map[key] = r
    
    # Sort by RRF score
    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    return [result_map[k] for k in sorted_keys[:limit]]


def cmd_list(args):
    """List collections"""
    indexer = Indexer()
    try:
        collections = indexer.list_collections()
        
        if args.json:
            print(json.dumps(collections, indent=2))
        else:
            if not collections:
                print("No collections. Use 'localseek add <path>' to add one.")
                return 0
            
            print(f"{'Name':<20} {'Documents':<10} {'Path'}")
            print("-" * 70)
            for c in collections:
                print(f"{c['name']:<20} {c['doc_count']:<10} {c['path']}")
        
        return 0
    finally:
        indexer.close()


def cmd_status(args):
    """Show index status"""
    indexer = Indexer()
    try:
        stats = indexer.get_stats()
        collections = indexer.list_collections()
        
        if args.json:
            stats["collections_detail"] = collections
            print(json.dumps(stats, indent=2))
        else:
            print(f"Database: {stats['db_path']}")
            print(f"Size: {stats['db_size_mb']} MB")
            print(f"Collections: {stats['collections']}")
            print(f"Documents: {stats['documents']}")
            
            if collections:
                print("\nCollections:")
                for c in collections:
                    print(f"  {c['name']}: {c['doc_count']} docs ({c['path']})")
        
        return 0
    finally:
        indexer.close()


def cmd_update(args):
    """Re-index all collections"""
    indexer = Indexer()
    try:
        print("Updating all collections...")
        results = indexer.update_all()
        
        for name, count in results.items():
            print(f"  {name}: {count} documents updated")
        
        return 0
    finally:
        indexer.close()


def cmd_remove(args):
    """Remove a collection"""
    indexer = Indexer()
    try:
        if indexer.remove_collection(args.name):
            print(f"Removed collection: {args.name}")
            return 0
        else:
            print(f"Collection not found: {args.name}", file=sys.stderr)
            return 1
    finally:
        indexer.close()


def cmd_get(args):
    """Get a document"""
    searcher = Searcher()
    try:
        doc = searcher.get_document(args.path, args.collection)
        
        if not doc:
            print(f"Document not found: {args.path}", file=sys.stderr)
            return 1
        
        if args.json:
            print(json.dumps(doc, indent=2, default=str))
        else:
            print(f"Title: {doc['title']}")
            print(f"Path: {doc['path']}")
            print(f"Collection: {doc['collection']}")
            print("-" * 40)
            
            content = doc['content']
            if args.full:
                print(content)
            else:
                # First 500 chars
                print(content[:500] + "..." if len(content) > 500 else content)
        
        return 0
    finally:
        searcher.close()


def cmd_metrics(args):
    """Show metrics and optionally save a snapshot"""
    metrics_db = get_metrics_db()
    
    try:
        # Save snapshot if requested
        if args.snapshot:
            snapshot_id = metrics_db.save_snapshot(args.snapshot)
            print(f"Saved snapshot #{snapshot_id}: {args.snapshot}")
        
        # Get current stats
        stats = metrics_db.get_stats()
        low_score = metrics_db.get_low_score_queries(threshold=3.0, limit=5)
        snapshots = metrics_db.get_snapshots(limit=5)
        
        if args.json:
            output = {
                "current": stats,
                "low_score_queries": low_score,
                "recent_snapshots": snapshots,
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            print("=== Current Metrics ===")
            print(f"Total searches: {stats.get('total_searches', 0)}")
            print(f"Avg latency: {stats.get('avg_latency_ms', 0):.1f} ms")
            print(f"Avg top score: {stats.get('avg_top_score', 0):.2f}")
            print(f"Avg result count: {stats.get('avg_result_count', 0):.1f}")
            print(f"Expansion usage: {stats.get('expansion_usage_rate', 0):.1f}%")
            print(f"Rerank usage: {stats.get('rerank_usage_rate', 0):.1f}%")
            print(f"Cache hit rate: {stats.get('expansion_cache_hit_rate', 0):.1f}%")
            print(f"Errors: {stats.get('error_count', 0)}")
            
            if low_score:
                print(f"\n=== Low-Score Queries (need improvement) ===")
                for q in low_score:
                    print(f"  {q['query_hash'][:8]}... avg_score={q['avg_score']:.2f} count={q['count']}")
            
            if snapshots:
                print(f"\n=== Recent Snapshots ===")
                for s in snapshots:
                    note = s.get('note', '-')[:30] if s.get('note') else '-'
                    print(f"  #{s['id']} {s['timestamp'][:10]} avg_score={s.get('avg_top_score', 0):.2f} note={note}")
        
        # Compare if requested
        if args.compare:
            ids = args.compare.split(',')
            if len(ids) == 2:
                comparison = metrics_db.compare_snapshots(int(ids[0]), int(ids[1]))
                print(f"\n=== Comparison ===")
                if "error" in comparison:
                    print(f"Error: {comparison['error']}")
                else:
                    changes = comparison.get("changes", {})
                    print(f"From: #{comparison['from']['id']} ({comparison['from']['note']})")
                    print(f"To: #{comparison['to']['id']} ({comparison['to']['note']})")
                    
                    score_change = changes.get('avg_top_score', 0)
                    indicator = "↑" if score_change > 0 else "↓" if score_change < 0 else "="
                    print(f"  Avg score: {indicator} {score_change:+.3f}")
                    
                    latency_change = changes.get('avg_latency_ms', 0)
                    indicator = "↑" if latency_change > 0 else "↓" if latency_change < 0 else "="
                    print(f"  Latency: {indicator} {latency_change:+.1f} ms")
                    
                    low_change = changes.get('low_score_queries', 0)
                    indicator = "↑" if low_change > 0 else "↓" if low_change < 0 else "="
                    print(f"  Low-score queries: {indicator} {low_change:+d}")
        
        return 0
    finally:
        metrics_db.close()


def cmd_serve(args):
    """Start the web UI server."""
    try:
        from .web import run_server
    except ImportError as e:
        print(f"Error: Web module not available: {e}", file=sys.stderr)
        return 1
    
    print(f"Starting localseek web UI on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    
    try:
        run_server(port=args.port, host=args.host)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="localseek",
        description="Local-first full-text search for your documents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # add
    add_parser = subparsers.add_parser("add", help="Add a collection")
    add_parser.add_argument("path", help="Path to folder")
    add_parser.add_argument("-n", "--name", help="Collection name (default: folder name)")
    add_parser.add_argument("-g", "--glob", help="Glob pattern (default: **/*.md)")
    add_parser.set_defaults(func=cmd_add)
    
    # search
    search_parser = subparsers.add_parser("search", help="Search documents")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("-c", "--collection", help="Restrict to collection")
    search_parser.add_argument("-n", "--limit", type=int, default=10, help="Max results")
    search_parser.add_argument("--min-score", type=float, default=0.0, help="Min score")
    search_parser.add_argument("--json", action="store_true", help="JSON output")
    search_parser.add_argument("--expand", action="store_true", help="Use LLM query expansion")
    search_parser.add_argument("--rerank", action="store_true", help="Use LLM reranking")
    search_parser.add_argument("--expand-count", type=int, default=2, help="Number of query expansions (default: 2)")
    search_parser.add_argument("--rerank-topk", type=int, default=20, help="Candidates to rerank (default: 20)")
    search_parser.add_argument("--cache", action="store_true", default=True, help="Use cache (default: true)")
    search_parser.add_argument("--no-cache", action="store_false", dest="cache", help="Disable cache")
    search_parser.add_argument("--summarize", action="store_true", help="Generate LLM summary of results")
    search_parser.add_argument("--fetch", action="store_true", help="Include web search results")
    search_parser.add_argument("--fetch-count", type=int, default=3, help="Number of web results (default: 3)")
    search_parser.set_defaults(func=cmd_search)
    
    # list
    list_parser = subparsers.add_parser("list", help="List collections")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    list_parser.set_defaults(func=cmd_list)
    
    # status
    status_parser = subparsers.add_parser("status", help="Index status")
    status_parser.add_argument("--json", action="store_true", help="JSON output")
    status_parser.set_defaults(func=cmd_status)
    
    # update
    update_parser = subparsers.add_parser("update", help="Re-index all collections")
    update_parser.set_defaults(func=cmd_update)
    
    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove a collection")
    remove_parser.add_argument("name", help="Collection name")
    remove_parser.set_defaults(func=cmd_remove)
    
    # get
    get_parser = subparsers.add_parser("get", help="Get a document")
    get_parser.add_argument("path", help="Document path")
    get_parser.add_argument("-c", "--collection", help="Collection name")
    get_parser.add_argument("--full", action="store_true", help="Show full content")
    get_parser.add_argument("--json", action="store_true", help="JSON output")
    get_parser.set_defaults(func=cmd_get)
    
    # metrics
    metrics_parser = subparsers.add_parser("metrics", help="View search metrics and snapshots")
    metrics_parser.add_argument("--snapshot", metavar="NOTE", help="Save a snapshot with note")
    metrics_parser.add_argument("--compare", metavar="ID1,ID2", help="Compare two snapshots (e.g., --compare 1,2)")
    metrics_parser.add_argument("--json", action="store_true", help="JSON output")
    metrics_parser.set_defaults(func=cmd_metrics)
    
    # serve
    serve_parser = subparsers.add_parser("serve", help="Start web UI server")
    serve_parser.add_argument("--port", type=int, default=8080, help="Port number (default: 8080)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    serve_parser.set_defaults(func=cmd_serve)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
