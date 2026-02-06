"""
CLI interface for localseek

Usage:
    python -m localseek add <path> --name <name>
    python -m localseek search <query>
    python -m localseek list
    python -m localseek status
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .index import Indexer
from .search import Searcher


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
    """Search documents"""
    searcher = Searcher()
    try:
        results = searcher.search(
            query=args.query,
            collection=args.collection,
            limit=args.limit,
            min_score=args.min_score
        )
        
        if args.json:
            output = {
                "query": args.query,
                "count": len(results),
                "results": [r.to_dict() for r in results]
            }
            print(json.dumps(output, indent=2))
        else:
            if not results:
                print("No results found.")
                return 0
            
            for i, r in enumerate(results, 1):
                # Header
                print(f"\n{r.collection}/{r.path}")
                print(f"  Title: {r.title}")
                print(f"  Score: {r.score:.3f}")
                print(f"  {r.snippet}")
        
        return 0
    finally:
        searcher.close()


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
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
