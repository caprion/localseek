"""
HTTP client for LLM server communication

Provides a simple interface to call local LLM servers (llama.cpp, Ollama, etc.)
"""

import json
from typing import List, Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import sys

from ..config import get_config


class LLMClient:
    """Client for communicating with local LLM server"""
    
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        config = get_config()
        self.base_url = (base_url or config.llm_url).rstrip("/")
        self.timeout = timeout or config.llm_timeout
        self._available: Optional[bool] = None
    
    def is_available(self) -> bool:
        """Check if the LLM server is available"""
        if self._available is not None:
            return self._available
        
        try:
            req = Request(f"{self.base_url}/health", method="GET")
            with urlopen(req, timeout=5) as response:
                self._available = response.status == 200
        except (URLError, HTTPError):
            self._available = False
        
        return self._available
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        Send a chat completion request
        
        Args:
            messages: List of {"role": "...", "content": "..."} messages
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        
        Returns:
            Generated text or None if request failed
        """
        if not self.is_available():
            return None
        
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        
        try:
            req = Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            
            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"].strip()
                
        except (URLError, HTTPError, KeyError, json.JSONDecodeError) as e:
            print(f"Warning: LLM request failed: {e}", file=sys.stderr)
            return None
    
    def complete(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Send a text completion request
        
        Args:
            prompt: The prompt to complete
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stop: Stop sequences
        
        Returns:
            Generated text or None if request failed
        """
        if not self.is_available():
            return None
        
        payload = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop
        
        try:
            req = Request(
                f"{self.base_url}/v1/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            
            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["text"].strip()
                
        except (URLError, HTTPError, KeyError, json.JSONDecodeError) as e:
            print(f"Warning: LLM request failed: {e}", file=sys.stderr)
            return None


# Singleton instance
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance"""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
