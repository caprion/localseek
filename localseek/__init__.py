"""
localseek - Local-first full-text search engine
"""

__version__ = "0.1.0"

from .index import Indexer
from .search import Searcher

__all__ = ["Indexer", "Searcher"]
