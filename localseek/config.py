"""
Configuration management for localseek

Handles environment variables and defaults.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


def get_cache_dir() -> Path:
    """Get cache directory, respecting XDG_CACHE_HOME"""
    cache_home = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(cache_home) / "localseek"


@dataclass
class Config:
    """localseek configuration"""
    
    # Core paths
    db_path: Path
    cache_db_path: Path
    metrics_db_path: Path
    
    # LLM integration
    llm_url: str
    llm_timeout: int
    llm_model: str
    
    # Query expansion
    expand_enabled: bool
    expand_count: int
    expand_cache: bool
    
    # Reranking
    rerank_enabled: bool
    rerank_topk: int
    rerank_cache: bool
    
    # Logging
    log_level: str  # off, errors, metrics, debug, full
    
    # Cache
    cache_enabled: bool
    cache_ttl_days: int
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        cache_dir = get_cache_dir()
        
        return cls(
            # Core paths
            db_path=Path(os.environ.get(
                "LOCALSEEK_DB_PATH", 
                str(cache_dir / "index.sqlite")
            )),
            cache_db_path=Path(os.environ.get(
                "LOCALSEEK_CACHE_DB",
                str(cache_dir / "cache.sqlite")
            )),
            metrics_db_path=Path(os.environ.get(
                "LOCALSEEK_METRICS_DB",
                str(cache_dir / "metrics.sqlite")
            )),
            
            # LLM integration (Ollama)
            llm_url=os.environ.get("LOCALSEEK_LLM_URL", "http://localhost:11434"),
            llm_timeout=int(os.environ.get("LOCALSEEK_LLM_TIMEOUT", "60")),
            llm_model=os.environ.get("LOCALSEEK_LLM_MODEL", "qwen2.5:1.5b"),
            
            # Query expansion
            expand_enabled=os.environ.get("LOCALSEEK_EXPAND_ENABLED", "true").lower() == "true",
            expand_count=int(os.environ.get("LOCALSEEK_EXPAND_COUNT", "2")),
            expand_cache=os.environ.get("LOCALSEEK_EXPAND_CACHE", "true").lower() == "true",
            
            # Reranking
            rerank_enabled=os.environ.get("LOCALSEEK_RERANK_ENABLED", "true").lower() == "true",
            rerank_topk=int(os.environ.get("LOCALSEEK_RERANK_TOPK", "20")),
            rerank_cache=os.environ.get("LOCALSEEK_RERANK_CACHE", "true").lower() == "true",
            
            # Logging
            log_level=os.environ.get("LOCALSEEK_LOG_LEVEL", "metrics"),
            
            # Cache
            cache_enabled=os.environ.get("LOCALSEEK_CACHE_ENABLED", "true").lower() == "true",
            cache_ttl_days=int(os.environ.get("LOCALSEEK_CACHE_TTL_DAYS", "30")),
        )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance"""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
