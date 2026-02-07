"""
Simple web UI for localseek

A minimal web interface for searching local documents.
Uses Python's built-in http.server - no external dependencies.

Usage:
    python -m localseek.web [--port 8080]
"""

import json
import os
import subprocess
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from ..search import Searcher
from ..index import Indexer


# HTML template with embedded CSS and JS
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>localseek</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
        * { box-sizing: border-box; }
        body {
            font-family: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #faf6f0;
            color: #3d2b1f;
        }
        h1 { 
            font-family: 'Libre Baskerville', Georgia, serif;
            color: #3d2b1f;
            font-weight: 400;
            margin-bottom: 5px;
        }
        .subtitle {
            color: #8b7560;
            margin-top: 0;
            margin-bottom: 20px;
        }
        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input[type="text"] {
            flex: 1;
            padding: 12px 16px;
            font-size: 16px;
            border: 2px solid #ede4d5;
            border-radius: 8px;
            outline: none;
            background: #ffffff;
            color: #3d2b1f;
        }
        input[type="text"]:focus {
            border-color: #c4a67d;
        }
        button {
            padding: 12px 24px;
            font-size: 16px;
            background: #1a5c4c;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        button:hover {
            background: #2d7a64;
        }
        .options {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .options label {
            display: flex;
            align-items: center;
            gap: 5px;
            color: #6b5443;
        }
        .results {
            background: white;
            border-radius: 8px;
            border: 1px solid #ede4d5;
            box-shadow: 0 1px 3px rgba(61,43,31,0.06);
        }
        .result {
            padding: 15px 20px;
            border-bottom: 1px solid #ede4d5;
        }
        .result:last-child {
            border-bottom: none;
        }
        .result-title {
            font-size: 18px;
            margin: 0 0 5px 0;
        }
        .result-title a {
            color: #c2452d;
            text-decoration: none;
        }
        .result-title a:hover {
            text-decoration: underline;
        }
        .result-meta {
            font-size: 13px;
            color: #8b7560;
            margin-bottom: 5px;
        }
        .result-snippet {
            font-size: 14px;
            color: #6b5443;
            line-height: 1.5;
        }
        .score {
            background: #ede4d5;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
            color: #6b5443;
        }
        .no-results {
            padding: 40px;
            text-align: center;
            color: #8b7560;
        }
        .loading {
            padding: 40px;
            text-align: center;
            color: #8b7560;
        }
        .summary {
            background: #ffffff;
            border: 1px solid #ede4d5;
            border-left: 3px solid #1a5c4c;
            border-radius: 8px;
            padding: 15px 20px;
            margin-bottom: 20px;
        }
        .summary h3 {
            margin: 0 0 10px 0;
            color: #1a5c4c;
            font-family: 'Libre Baskerville', Georgia, serif;
            font-weight: 400;
        }
        .web-results {
            margin-top: 20px;
        }
        .web-results h3 {
            color: #3d2b1f;
            font-family: 'Libre Baskerville', Georgia, serif;
            font-weight: 400;
            margin-bottom: 10px;
        }
        .web-result {
            padding: 10px 15px;
            background: #fff;
            border-radius: 6px;
            margin-bottom: 8px;
            border: 1px solid #ede4d5;
            box-shadow: 0 1px 2px rgba(61,43,31,0.04);
        }
        .web-result a {
            color: #c2452d;
            text-decoration: none;
        }
        .web-result a:hover {
            text-decoration: underline;
        }
        .stats {
            font-size: 13px;
            color: #8b7560;
            margin-bottom: 15px;
        }
        .search-container {
            position: relative;
            flex: 1;
        }
        .autocomplete {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 2px solid #ede4d5;
            border-top: none;
            border-radius: 0 0 8px 8px;
            max-height: 300px;
            overflow-y: auto;
            z-index: 100;
            display: none;
        }
        .autocomplete.show {
            display: block;
        }
        .autocomplete-item {
            padding: 10px 16px;
            cursor: pointer;
            border-bottom: 1px solid #ede4d5;
        }
        .autocomplete-item:last-child {
            border-bottom: none;
        }
        .autocomplete-item:hover, .autocomplete-item.selected {
            background: rgba(194,69,45,0.06);
        }
        .autocomplete-item .title {
            font-weight: 500;
            color: #3d2b1f;
        }
        .autocomplete-item .collection {
            font-size: 12px;
            color: #8b7560;
        }
    </style>
</head>
<body>
    <h1>localseek</h1>
    <p class="subtitle">Search your local documents</p>
    
    <div class="search-box">
        <div class="search-container">
            <input type="text" id="query" placeholder="Enter search query..." autocomplete="off" autofocus>
            <div id="autocomplete" class="autocomplete"></div>
        </div>
        <button onclick="search()">Search</button>
    </div>
    
    <div class="options">
        <label><input type="checkbox" id="expand"> Expand query</label>
        <label><input type="checkbox" id="rerank"> Rerank results</label>
        <label><input type="checkbox" id="fetch"> Include web</label>
        <label><input type="checkbox" id="summarize"> Summarize</label>
    </div>
    
    <div id="stats" class="stats"></div>
    <div id="summary"></div>
    <div id="results" class="results"></div>
    <div id="web-results" class="web-results"></div>
    
    <script>
        const queryInput = document.getElementById('query');
        const autocompleteDiv = document.getElementById('autocomplete');
        let autocompleteTimeout = null;
        let selectedIndex = -1;
        
        queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                hideAutocomplete();
                search();
            }
        });
        
        queryInput.addEventListener('input', () => {
            clearTimeout(autocompleteTimeout);
            autocompleteTimeout = setTimeout(fetchAutocomplete, 150);
        });
        
        queryInput.addEventListener('keydown', (e) => {
            const items = autocompleteDiv.querySelectorAll('.autocomplete-item');
            if (items.length === 0) return;
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                updateSelection(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, -1);
                updateSelection(items);
            } else if (e.key === 'Escape') {
                hideAutocomplete();
            }
        });
        
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-container')) {
                hideAutocomplete();
            }
        });
        
        function updateSelection(items) {
            items.forEach((item, i) => {
                item.classList.toggle('selected', i === selectedIndex);
            });
            if (selectedIndex >= 0) {
                queryInput.value = items[selectedIndex].dataset.title;
            }
        }
        
        function hideAutocomplete() {
            autocompleteDiv.classList.remove('show');
            selectedIndex = -1;
        }
        
        async function fetchAutocomplete() {
            const prefix = queryInput.value.trim();
            if (prefix.length < 2) {
                hideAutocomplete();
                return;
            }
            
            try {
                const response = await fetch('/api/autocomplete?prefix=' + encodeURIComponent(prefix));
                const data = await response.json();
                
                if (data.suggestions && data.suggestions.length > 0) {
                    autocompleteDiv.innerHTML = data.suggestions.map(s => `
                        <div class="autocomplete-item" data-title="${escapeHtml(s.title)}">
                            <div class="title">${escapeHtml(s.title)}</div>
                            <div class="collection">${escapeHtml(s.collection)}</div>
                        </div>
                    `).join('');
                    
                    autocompleteDiv.querySelectorAll('.autocomplete-item').forEach(item => {
                        item.addEventListener('click', () => {
                            queryInput.value = item.dataset.title;
                            hideAutocomplete();
                            search();
                        });
                    });
                    
                    autocompleteDiv.classList.add('show');
                    selectedIndex = -1;
                } else {
                    hideAutocomplete();
                }
            } catch (err) {
                hideAutocomplete();
            }
        }
        
        async function search() {
            const query = queryInput.value.trim();
            if (!query) return;
            
            const resultsDiv = document.getElementById('results');
            const summaryDiv = document.getElementById('summary');
            const webResultsDiv = document.getElementById('web-results');
            const statsDiv = document.getElementById('stats');
            
            resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
            summaryDiv.innerHTML = '';
            webResultsDiv.innerHTML = '';
            statsDiv.innerHTML = '';
            
            const params = new URLSearchParams({
                q: query,
                expand: document.getElementById('expand').checked,
                rerank: document.getElementById('rerank').checked,
                fetch: document.getElementById('fetch').checked,
                summarize: document.getElementById('summarize').checked
            });
            
            try {
                const startTime = Date.now();
                const response = await fetch('/api/search?' + params);
                const data = await response.json();
                const elapsed = Date.now() - startTime;
                
                // Stats
                statsDiv.innerHTML = `Found ${data.count} results in ${elapsed}ms`;
                if (data.expanded_queries && data.expanded_queries.length > 1) {
                    statsDiv.innerHTML += ` | Expanded to: ${data.expanded_queries.join(', ')}`;
                }
                
                // Summary
                if (data.summary) {
                    summaryDiv.innerHTML = `
                        <div class="summary">
                            <h3>Summary</h3>
                            <p>${data.summary}</p>
                        </div>
                    `;
                }
                
                // Local results
                if (data.results && data.results.length > 0) {
                    resultsDiv.innerHTML = data.results.map(r => `
                        <div class="result">
                            <h3 class="result-title">
                                <a href="#" class="file-link" data-path="${encodeURIComponent(r.full_path)}">${escapeHtml(r.title)}</a>
                            </h3>
                            <div class="result-meta">
                                <span class="score">${r.blended_score ? r.blended_score.toFixed(3) : r.score.toFixed(3)}</span>
                                ${r.collection}/${r.path}
                            </div>
                            <div class="result-snippet">${escapeHtml(r.snippet)}</div>
                        </div>
                    `).join('');
                    
                    // Attach click handlers to file links
                    document.querySelectorAll('.file-link').forEach(link => {
                        link.addEventListener('click', (e) => {
                            e.preventDefault();
                            openFile(decodeURIComponent(link.dataset.path));
                        });
                    });
                } else {
                    resultsDiv.innerHTML = '<div class="no-results">No results found</div>';
                }
                
                // Web results
                if (data.web_results && data.web_results.length > 0) {
                    webResultsDiv.innerHTML = `
                        <h3>Web Results</h3>
                        ${data.web_results.map(r => `
                            <div class="web-result">
                                <a href="${r.url}" target="_blank">${escapeHtml(r.title)}</a>
                            </div>
                        `).join('')}
                    `;
                }
                
            } catch (err) {
                resultsDiv.innerHTML = `<div class="no-results">Error: ${err.message}</div>`;
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        }
        
        async function openFile(path) {
            try {
                const response = await fetch('/api/open?path=' + encodeURIComponent(path));
                const data = await response.json();
                if (!data.success) {
                    alert('Failed to open file: ' + (data.error || 'Unknown error'));
                }
            } catch (err) {
                alert('Failed to open file: ' + err.message);
            }
        }
    </script>
</body>
</html>
"""


class LocalseekHandler(BaseHTTPRequestHandler):
    """HTTP request handler for localseek web UI"""
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/" or parsed.path == "":
            self._serve_html()
        elif parsed.path == "/api/search":
            self._handle_search(parsed.query)
        elif parsed.path == "/api/status":
            self._handle_status()
        elif parsed.path == "/api/open":
            self._handle_open(parsed.query)
        elif parsed.path == "/api/autocomplete":
            self._handle_autocomplete(parsed.query)
        else:
            self._send_404()
    
    def _serve_html(self):
        """Serve the main HTML page"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
    
    def _handle_search(self, query_string: str):
        """Handle search API request"""
        params = urllib.parse.parse_qs(query_string)
        
        query = params.get("q", [""])[0]
        if not query:
            self._send_json({"error": "Missing query parameter"}, 400)
            return
        
        use_expand = params.get("expand", ["false"])[0].lower() == "true"
        use_rerank = params.get("rerank", ["false"])[0].lower() == "true"
        use_fetch = params.get("fetch", ["false"])[0].lower() == "true"
        use_summarize = params.get("summarize", ["false"])[0].lower() == "true"
        limit = int(params.get("limit", ["10"])[0])
        
        try:
            result = self._do_search(
                query, 
                limit=limit,
                use_expand=use_expand,
                use_rerank=use_rerank,
                use_fetch=use_fetch,
                use_summarize=use_summarize,
            )
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def _do_search(
        self,
        query: str,
        limit: int = 10,
        use_expand: bool = False,
        use_rerank: bool = False,
        use_fetch: bool = False,
        use_summarize: bool = False,
    ) -> dict:
        """Perform search and return results dict"""
        searcher = Searcher()
        
        try:
            queries = [query]
            
            # Expand query if requested
            if use_expand:
                try:
                    from ..optional.expand import expand_query, ExpansionCache
                    cache = ExpansionCache()
                    queries, _ = expand_query(query, count=2, cache=cache)
                except ImportError:
                    pass
            
            # Search with all queries
            all_results = []
            for q in queries:
                results = searcher.search(q, limit=limit * 2 if use_rerank else limit)
                all_results.extend(results)
            
            # Dedupe
            seen = set()
            unique_results = []
            for r in all_results:
                key = f"{r.collection}:{r.path}"
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)
            results = unique_results[:limit * 2 if use_rerank else limit]
            
            # Rerank if requested
            if use_rerank and results:
                try:
                    from ..optional.rerank import rerank_results, RerankCache
                    cache = RerankCache()
                    result_dicts = [r.to_dict() for r in results]
                    reranked, _ = rerank_results(query, result_dicts, topk=20, cache=cache)
                    if reranked:
                        results = reranked[:limit]
                except ImportError:
                    results = results[:limit]
            else:
                results = results[:limit]
            
            # Fetch web results if requested
            web_results = []
            if use_fetch:
                try:
                    from ..optional.web_search import fetch_web_results
                    web_results = fetch_web_results(query, max_results=3)
                except ImportError:
                    pass
            
            # Summarize if requested
            summary = None
            if use_summarize:
                try:
                    from ..optional.summarize import summarize_with_context
                    result_dicts = []
                    for r in results:
                        if hasattr(r, 'to_dict'):
                            result_dicts.append(r.to_dict())
                        elif hasattr(r, 'blended_score'):
                            result_dicts.append({
                                "title": r.title,
                                "snippet": r.snippet,
                                "score": r.blended_score,
                            })
                        else:
                            result_dicts.append(r)
                    
                    summary = summarize_with_context(
                        query,
                        result_dicts,
                        expanded_queries=queries if len(queries) > 1 else None,
                        web_results=web_results if web_results else None,
                    )
                except ImportError:
                    pass
            
            # Format results for JSON
            formatted_results = []
            for r in results:
                if hasattr(r, 'blended_score'):
                    formatted_results.append({
                        "path": r.path,
                        "title": r.title,
                        "snippet": r.snippet,
                        "score": r.original_score,
                        "blended_score": r.blended_score,
                        "collection": r.collection,
                        "full_path": r.full_path,
                    })
                else:
                    formatted_results.append(r.to_dict())
            
            return {
                "query": query,
                "expanded_queries": queries if len(queries) > 1 else None,
                "count": len(results),
                "summary": summary,
                "results": formatted_results,
                "web_results": web_results if web_results else None,
            }
            
        finally:
            searcher.close()
    
    def _handle_status(self):
        """Handle status API request"""
        indexer = Indexer()
        try:
            collections = indexer.list_collections()
            total_docs = sum(c.get("doc_count", 0) for c in collections)
            self._send_json({
                "status": "ok",
                "collections": len(collections),
                "documents": total_docs,
            })
        finally:
            indexer.close()
    
    def _handle_open(self, query_string: str):
        """Handle open file API request"""
        params = urllib.parse.parse_qs(query_string)
        file_path = params.get("path", [""])[0]
        
        if not file_path:
            self._send_json({"success": False, "error": "Missing path parameter"}, 400)
            return
        
        # Verify file exists
        path = Path(file_path)
        if not path.exists():
            self._send_json({"success": False, "error": "File not found"}, 404)
            return
        
        try:
            # Use VS Code for text-based files
            text_extensions = {'.md', '.txt', '.rst', '.json', '.yaml', '.yml', '.py', '.js', '.ts', '.html', '.css'}
            use_vscode = path.suffix.lower() in text_extensions
            
            if use_vscode:
                # Try VS Code first
                try:
                    subprocess.run(["code", file_path], check=True, shell=(sys.platform == "win32"))
                    self._send_json({"success": True, "path": file_path, "editor": "vscode"})
                    return
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass  # Fall back to default
            
            # Open with default application
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", file_path], check=True)
            else:
                subprocess.run(["xdg-open", file_path], check=True)
            
            self._send_json({"success": True, "path": file_path})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)
    
    def _handle_autocomplete(self, query_string: str):
        """Handle autocomplete API request"""
        params = urllib.parse.parse_qs(query_string)
        prefix = params.get("prefix", [""])[0]
        limit = int(params.get("limit", ["8"])[0])
        
        if not prefix or len(prefix) < 2:
            self._send_json({"suggestions": []})
            return
        
        try:
            searcher = Searcher()
            try:
                suggestions = searcher.autocomplete(prefix, limit=limit)
                self._send_json({"suggestions": suggestions})
            finally:
                searcher.close()
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def _send_json(self, data: dict, status: int = 200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))
    
    def _send_404(self):
        """Send 404 response"""
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Not Found")


def run_server(port: int = 8080, host: str = "127.0.0.1"):
    """Run the web server"""
    server = HTTPServer((host, port), LocalseekHandler)
    print(f"localseek web UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


def main():
    """CLI entry point for web server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="localseek web UI")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
