"""
repair_engine.py
================
LLM-powered repair loop that attempts to fix failed compilations.

Flow:
1. Try to compile code
2. If fails → extract error → send to LLM → get fixed code
3. Retry compilation (max 3 times)
4. Return result with repair_attempts tracking
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json

from llm_client import CodeLLMClient, LLMResponse
from compiler_check import get_checker, CompileResult


@dataclass
class RepairAttempt:
    """Single repair attempt record."""
    attempt_number: int
    generated_code: str
    compiler_error: str
    llm_response: LLMResponse
    fixed_code: Optional[str]
    compile_result: Optional[CompileResult] = None
    success: bool = False


@dataclass
class RepairResult:
    """Result of repair loop."""
    original_code: str
    target_lang: str
    source_lang: str
    
    # Results
    final_code: Optional[str] = None
    repair_success: bool = False
    initial_compile_fail: bool = True
    
    # Tracking
    repair_attempts: list[RepairAttempt] = field(default_factory=list)
    total_attempts: int = 0
    llm_tokens_used: int = 0
    repair_time_ms: float = 0.0


class RepairEngine:
    """Orchestrates LLM-based code repair."""
    
    def __init__(self, 
                 llm_endpoint: str = "http://soketlab-node060:30000/v1/chat/completions",
                 max_attempts: int = 3,
                 verbose: bool = False):
        """
        Args:
            llm_endpoint: CodeLLM API endpoint
            max_attempts: Maximum repair attempts (1-3 recommended)
            verbose: Print debug info
        """
        self.llm_client = CodeLLMClient(endpoint=llm_endpoint)
        self.max_attempts = max_attempts
        self.verbose = verbose
    
    def repair(self,
               code: str,
               target_lang: str,
               source_lang: str = "Unknown") -> RepairResult:
        """
        Attempt to repair code using LLM.
        
        Args:
            code: The transpiled code to potentially repair
            target_lang: Target language (e.g., "C", "Java")
            source_lang: Original source language
        
        Returns:
            RepairResult with final_code and repair_success
        """
        import time
        start_time = time.monotonic()
        
        result = RepairResult(
            original_code=code,
            target_lang=target_lang,
            source_lang=source_lang
        )
        
        # Check if initial code compiles
        checker = get_checker(target_lang)
        initial_check = checker.check(code)
        
        if initial_check.success:
            # Code already compiles!
            result.final_code = code
            result.repair_success = True
            result.initial_compile_fail = False
            result.repair_time_ms = (time.monotonic() - start_time) * 1000
            return result
        
        # Code failed to compile - try repairs
        current_code = code
        
        for attempt_num in range(1, self.max_attempts + 1):
            if self.verbose:
                print(f"  Repair attempt {attempt_num}/{self.max_attempts}...")
            
            # Get LLM fix
            llm_response = self.llm_client.fix_code(
                current_code,
                target_lang,
                initial_check.error_message or "Compilation failed",
                source_lang
            )
            
            if not llm_response.success:
                if self.verbose:
                    print(f"    LLM failed: {llm_response.error}")
                break
            
            fixed_code = llm_response.fixed_code
            
            # Try to compile the fixed code
            compile_check = checker.check(fixed_code)
            
            attempt = RepairAttempt(
                attempt_number=attempt_num,
                generated_code=current_code,
                compiler_error=initial_check.error_message or "Unknown error",
                llm_response=llm_response,
                fixed_code=fixed_code,
                compile_result=compile_check,
                success=compile_check.success
            )
            result.repair_attempts.append(attempt)
            result.llm_tokens_used += llm_response.usage_tokens
            
            if compile_check.success:
                # SUCCESS!
                result.final_code = fixed_code
                result.repair_success = True
                if self.verbose:
                    print(f"    ✅ Fixed on attempt {attempt_num}")
                break
            else:
                # Still broken, update error for next attempt
                initial_check = compile_check
                current_code = fixed_code
                if self.verbose:
                    print(f"    ❌ Still broken: {compile_check.error_message[:100]}")
        
        result.final_code = result.final_code or current_code
        result.total_attempts = len(result.repair_attempts)
        result.repair_time_ms = (time.monotonic() - start_time) * 1000
        
        return result
    
    def to_dict(self, repair_result: RepairResult) -> dict:
        """Convert RepairResult to JSON-serializable dict."""
        return {
            "repair_success": repair_result.repair_success,
            "initial_compile_fail": repair_result.initial_compile_fail,
            "total_attempts": repair_result.total_attempts,
            "llm_tokens_used": repair_result.llm_tokens_used,
            "repair_time_ms": repair_result.repair_time_ms,
            "final_code": repair_result.final_code,
            "attempts": [
                {
                    "attempt_number": a.attempt_number,
                    "success": a.success,
                    "compiler_error": a.compiler_error[:200] if a.compiler_error else None,
                    "llm_error": a.llm_response.error,
                    "llm_tokens": a.llm_response.usage_tokens,
                }
                for a in repair_result.repair_attempts
            ]
        }
