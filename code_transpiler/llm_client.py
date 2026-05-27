"""
llm_repair/llm_client.py
========================
OpenAI-compatible client for CodeLLM (DeepSeek-v3.2) hosted at cluster.

Wraps HTTP calls to: http://soketlab-node060:30000/v1/chat/completions
"""

from __future__ import annotations
import requests
import json
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM fix request."""
    success: bool
    fixed_code: Optional[str] = None
    error: Optional[str] = None
    model: str = "deepseek-v3.2"
    usage_tokens: int = 0


class CodeLLMClient:
    """Client for DeepSeek-v3.2 CodeLLM."""
    
    def __init__(self, endpoint: str = "http://soketlab-node060:30000/v1/chat/completions",
                 model: str = "deepseek-v3.2",
                 timeout: int = 30,
                 temperature: float = 0.2):
        """
        Args:
            endpoint: LLM API endpoint (OpenAI-compatible)
            model: Model name
            timeout: Request timeout in seconds
            temperature: Lower = more deterministic (good for code)
        """
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
    
    def fix_code(self, source_code: str,
                 target_lang: str,
                 compiler_error: str,
                 source_lang: str = "Unknown") -> LLMResponse:
        """
        Ask CodeLLM to fix transpiled code that failed to compile.
        
        Args:
            source_code: The transpiled code that failed
            target_lang: Target language (e.g., "C", "Java")
            compiler_error: The compiler error message
            source_lang: Original source language (for context)
        
        Returns:
            LLMResponse with fixed code or error details
        """
        prompt = self._build_fix_prompt(source_code, target_lang, compiler_error, source_lang)
        
        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": self._system_prompt(target_lang)
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": self.temperature,
                    "max_tokens": 4096,
                    "top_p": 0.95,
                },
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Extract fixed code from response
            fixed_code = data["choices"][0]["message"]["content"].strip()
            
            # Try to extract just the code block if wrapped in markdown
            if "```" in fixed_code:
                parts = fixed_code.split("```")
                if len(parts) >= 3:
                    # Code is between backticks, optionally with language specifier
                    code_block = parts[1]
                    # Remove language specifier line if present
                    lines = code_block.split("\n")
                    if lines[0].strip() in ["c", "cpp", "java", "javascript", "python", "js"]:
                        fixed_code = "\n".join(lines[1:])
                    else:
                        fixed_code = code_block
            
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            
            return LLMResponse(
                success=True,
                fixed_code=fixed_code,
                usage_tokens=tokens
            )
            
        except requests.exceptions.Timeout:
            return LLMResponse(
                success=False,
                error=f"LLM request timeout (>{self.timeout}s)"
            )
        except requests.exceptions.ConnectionError as e:
            return LLMResponse(
                success=False,
                error=f"Failed to connect to LLM endpoint: {e}"
            )
        except json.JSONDecodeError as e:
            return LLMResponse(
                success=False,
                error=f"Invalid JSON response from LLM: {e}"
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                error=f"LLM error: {str(e)[:200]}"
            )
    
    def _system_prompt(self, target_lang: str) -> str:
        """System prompt for code fixing."""
        return f"""You are an expert {target_lang} programmer. 
Your task is to fix {target_lang} code that failed to compile.

Given:
1. The {target_lang} code that failed
2. The compiler error message

You must:
1. Analyze the error
2. Fix the code
3. Return ONLY the fixed {target_lang} code (no explanations)

Return the complete fixed code in a single code block."""
    
    def _build_fix_prompt(self, source_code: str,
                         target_lang: str,
                         compiler_error: str,
                         source_lang: str) -> str:
        """Build the fix prompt."""
        return f"""Fix this {target_lang} code (transpiled from {source_lang}) that failed to compile:

```{target_lang.lower()}
{source_code}
```

Compiler error:
```
{compiler_error}
```

Provide the complete fixed code."""
