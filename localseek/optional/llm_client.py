"""
HTTP client for LLM server communication

Provides a simple interface to call local LLM servers (Ollama, llama.cpp, etc.)
Defaults to Ollama API format (http://localhost:11434)
"""

import json
from typing import List, Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import sys

from ..config import get_config


class LLMClient:
    """Client for communicating with Ollama or compatible LLM server"""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        model: Optional[str] = None,
    ):
        config = get_config()
        self.base_url = (base_url or config.llm_url).rstrip("/")
        self.timeout = timeout or config.llm_timeout
        self.model = model or config.llm_model
        self._available: Optional[bool] = None
    
    def is_available(self) -> bool:
        """Check if the LLM server is available"""
        if self._available is not None:
            return self._available
        
        try:
            # Ollama returns "Ollama is running" at root
            req = Request(f"{self.base_url}/", method="GET")
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
        Send a chat completion request (Ollama format)
        
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
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        
        try:
            req = Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            
            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["message"]["content"].strip()
                
        except (URLError, HTTPError, KeyError, json.JSONDecodeError) as e:
            print(f"Warning: LLM chat request failed: {e}", file=sys.stderr)
            return None
    
    def complete(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Send a text completion request (Ollama format)
        
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
        
        options = {
            "num_predict": max_tokens,
            "temperature": temperature,
        }
        if stop:
            options["stop"] = stop
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        
        try:
            req = Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            
            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["response"].strip()
                
        except (URLError, HTTPError, KeyError, json.JSONDecodeError) as e:
            print(f"Warning: LLM completion request failed: {e}", file=sys.stderr)
            return None


# Singleton instance
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance"""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
