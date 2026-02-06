"""
Summarization module for localseek

Uses LLM to generate a summary of search results.
"""

from typing import List, Dict, Any, Optional
from .llm_client import get_llm_client


SUMMARIZE_PROMPT = """You are a research assistant. Given search results for a query, provide a concise summary.

Query: {query}

Search Results:
{results}

Instructions:
- Synthesize the key insights from these documents
- Be concise (2-4 sentences)
- Mention specific document titles when relevant
- If results seem unrelated to the query, say so

Summary:"""


def summarize_results(
    query: str,
    results: List[Dict[str, Any]],
    max_results: int = 5,
) -> Optional[str]:
    """
    Generate a summary of search results using LLM
    
    Args:
        query: The original search query
        results: List of search result dicts with title, snippet, path, score
        max_results: Maximum number of results to include in summary
    
    Returns:
        Summary string or None if LLM unavailable
    """
    client = get_llm_client()
    
    if not client.is_available():
        return None
    
    # Format results for the prompt
    results_text = ""
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title", "Untitled")
        snippet = r.get("snippet", "")[:300]  # Limit snippet length
        score = r.get("score", 0)
        results_text += f"\n{i}. **{title}** (score: {score:.2f})\n   {snippet}\n"
    
    if not results_text.strip():
        return "No results to summarize."
    
    prompt = SUMMARIZE_PROMPT.format(query=query, results=results_text)
    
    # Use chat for better instruction following
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    summary = client.chat(messages, max_tokens=200, temperature=0.3)
    
    return summary


def summarize_with_context(
    query: str,
    results: List[Dict[str, Any]],
    expanded_queries: Optional[List[str]] = None,
    web_results: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Generate a rich summary combining local and web results
    
    Args:
        query: The original search query
        results: Local search results
        expanded_queries: Query expansions used (if any)
        web_results: Web search results (if any)
    
    Returns:
        Summary string or None if LLM unavailable
    """
    client = get_llm_client()
    
    if not client.is_available():
        return None
    
    # Build context
    context_parts = []
    
    if expanded_queries and len(expanded_queries) > 1:
        context_parts.append(f"Search expanded to: {', '.join(expanded_queries)}")
    
    # Local results
    if results:
        local_text = "\n**Local Documents:**\n"
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "Untitled")
            snippet = r.get("snippet", "")[:200]
            local_text += f"{i}. {title}\n   {snippet}\n"
        context_parts.append(local_text)
    
    # Web results (if available)
    if web_results:
        web_text = "\n**Web Results:**\n"
        for i, r in enumerate(web_results[:3], 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")[:200]
            url = r.get("url", "")
            web_text += f"{i}. {title}\n   {snippet}\n   Source: {url}\n"
        context_parts.append(web_text)
    
    if not context_parts:
        return "No results to summarize."
    
    full_context = "\n".join(context_parts)
    
    prompt = f"""Query: {query}

{full_context}

Provide a 2-4 sentence summary synthesizing the key insights. Mention document titles or sources when relevant."""

    messages = [{"role": "user", "content": prompt}]
    
    return client.chat(messages, max_tokens=250, temperature=0.3)
