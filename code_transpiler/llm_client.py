"""
llm_repair/llm_client.py
========================
OpenAI-compatible client for Qwen/Qwen3-Coder-30B-A3B-Instruct hosted at 172.17.99.11:30000.

Wraps HTTP calls to: http://172.17.99.11:30000/v1/chat/completions
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
    model: str = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    usage_tokens: int = 0


class CodeLLMClient:
    """Client for Qwen/Qwen3-Coder-30B-A3B-Instruct at 172.17.99.11:30000."""
    
    def __init__(self, endpoint: str = "http://172.17.99.11:30000/v1/chat/completions",
                 model: str = "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                 timeout: int = 30,
                 temperature: float = 0.1,
                 auth_token: str = "AVTXOTWZab9v8WExZMNcGXdCFPCmon4LQPMWP6iS32w2"):
        """
        Args:
            endpoint: LLM API endpoint (OpenAI-compatible)
            model: Model name
            timeout: Request timeout in seconds
            temperature: Lower = more deterministic (good for code)
            auth_token: Bearer token for authorization
        """
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.auth_token = auth_token
    
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
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.auth_token}"
                },
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
            message = data["choices"][0]["message"]
            fixed_code = message.get("content") or message.get("reasoning_content")
            
            if not fixed_code:
                return LLMResponse(
                    success=False,
                    error="LLM returned empty response"
                )
            
            fixed_code = fixed_code.strip()
            
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
        """System prompt for code fixing - optimized for Kimi K2.5 and broken code repair."""
        return f"""You are an expert {target_lang} programmer specializing in code repair and debugging.

Your task: Fix {target_lang} code that failed to compile.

Instructions:
1. Read the compiler error carefully
2. Identify root cause (syntax, type, missing imports, scope issues, etc.)
3. Fix ONLY the parts causing the error
4. Preserve all non-problematic code  
5. Return ONLY compilable {target_lang} code with no explanations

Priority: Make code compile first, then ensure correctness.
Format: Complete fixed {target_lang} code in a code block."""
    
    def regenerate_code(self, source_code: str,
                        target_lang: str,
                        source_lang: str = "Unknown") -> LLMResponse:
        """
        Regenerate target language code from source code.
        
        Used when transpilation produces EMPTY output.
        Asks LLM to translate source code to target language.
        
        Args:
            source_code: Original source code
            target_lang: Target language (e.g., "Java")
            source_lang: Source language (e.g., "Python")
        
        Returns:
            LLMResponse with generated code
        """
        system_prompt = f"""You are an expert {target_lang} programmer specializing in code translation.

Your task: Translate {source_lang} code to {target_lang}.

Instructions:
1. Understand the logic and functionality of the source code
2. Translate it to {target_lang} using appropriate idioms and libraries
3. Ensure the output is complete and compilable
4. Match the structure and behavior of the original code
5. Return ONLY compilable {target_lang} code with no explanations

Format: Complete {target_lang} code in a code block."""
        
        user_prompt = f"""Translate this {source_lang} code to {target_lang}:

```{source_lang.lower()}
{source_code[:2000]}
```

Generate complete, compilable {target_lang} code."""
        
        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.auth_token}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": 4096,
                    "top_p": 0.95,
                },
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Extract generated code from response
            message = data["choices"][0]["message"]
            generated_code = message.get("content") or message.get("reasoning_content")
            
            if not generated_code:
                return LLMResponse(
                    success=False,
                    error="LLM returned empty response"
                )
            
            generated_code = generated_code.strip()
            
            # Try to extract just the code block if wrapped in markdown
            if "```" in generated_code:
                parts = generated_code.split("```")
                if len(parts) >= 3:
                    code_block = parts[1]
                    lines = code_block.split("\n")
                    if lines[0].strip() in ["c", "cpp", "java", "javascript", "python", "js"]:
                        generated_code = "\n".join(lines[1:])
                    else:
                        generated_code = code_block
            
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            
            return LLMResponse(
                success=True,
                fixed_code=generated_code,
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
    
    def _build_fix_prompt(self, source_code: str,
                         target_lang: str,
                         compiler_error: str,
                         source_lang: str) -> str:
        """Build the fix prompt - for broken code repair (60% of dataset)."""
        return f"""[Broken {target_lang} Code - Transpiled from {source_lang}]

Code:
```{target_lang.lower()}
{source_code}
```

Compiler Error:
{compiler_error}

Task: Fix this code to be compilable.
Return only the corrected {target_lang} code, nothing else."""
