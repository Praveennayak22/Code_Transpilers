"""
llm_repair_integration.py
==========================
Integration point for LLM repair into the main pipeline.

This module extends the PipelineRunner to optionally run the repair loop
after code generation.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from pipeline.runner import PipelineRunner, TranspileResult
from repair_engine import RepairEngine, RepairResult
from compiler_check import get_checker


@dataclass
class EnhancedTranspileResult(TranspileResult):
    """Extended result with LLM repair information."""
    
    # Repair-specific fields
    repair_attempted: bool = False
    repair_success: bool = False
    repair_attempts: int = 0
    llm_tokens_used: int = 0
    repaired_code: Optional[str] = None
    initial_compile_fail: bool = False


class RepairEnabledPipelineRunner(PipelineRunner):
    """
    Extended PipelineRunner that includes LLM repair loop.
    
    Stages:
    1. Preprocess
    2. Parse
    3. Lift
    4. Transform
    5. Generate
    6. [NEW] LLM Repair (if compilation fails and --use-llm-repair is set)
    """
    
    def __init__(self, registry, cache=None, 
                 use_llm_repair: bool = False,
                 llm_endpoint: str = "http://172.17.99.11:30000/v1/chat/completions",
                 repair_max_attempts: int = 3):
        """
        Args:
            registry: Language registry
            cache: Optional transpilation cache
            use_llm_repair: Enable LLM repair loop
            llm_endpoint: CodeLLM endpoint
            repair_max_attempts: Max repair attempts (1-3)
        """
        super().__init__(registry, cache)
        self.use_llm_repair = use_llm_repair
        
        if use_llm_repair:
            self.repair_engine = RepairEngine(
                llm_endpoint=llm_endpoint,
                max_attempts=repair_max_attempts,
                auth_token="AVTXOTWZab9v8WExZMNcGXdCFPCmon4LQPMWP6iS32w2",
                verbose=False
            )
        else:
            self.repair_engine = None
    
    def transpile(self, source_code: str,
                  source_lang: str,
                  target_lang: str) -> EnhancedTranspileResult:
        """
        Run the full pipeline with optional LLM repair.
        
        Returns EnhancedTranspileResult.
        """
        # Run standard 5-stage pipeline
        base_result = super().transpile(source_code, source_lang, target_lang)
        
        # Create extended result with repair fields
        result = EnhancedTranspileResult(
            source_lang=base_result.source_lang,
            target_lang=base_result.target_lang,
            source_code=base_result.source_code,
            transpiled_code=base_result.transpiled_code,
            transpile_success=base_result.transpile_success,
            transpile_error=base_result.transpile_error,
            transpile_stage=base_result.transpile_stage,
            transpile_time_ms=base_result.transpile_time_ms,
            cache_hit=base_result.cache_hit,
        )
        
        # If transpilation failed, don't attempt repair
        if not result.transpile_success:
            return result
        
        # If repair not enabled, return as-is
        if not self.use_llm_repair:
            return result
        
        # Try to compile the transpiled code
        try:
            checker = get_checker(target_lang)
            compile_check = checker.check(result.transpiled_code)
            
            # If it compiles, no repair needed
            if compile_check.success:
                return result
            
            # Code generated but won't compile - attempt repair
            result.initial_compile_fail = True
            
            try:
                repair_result = self.repair_engine.repair(
                    code=result.transpiled_code,
                    target_lang=target_lang,
                    source_lang=source_lang,
                    source_code=source_code  # Pass original source for regeneration on empty
                )
                
                result.repair_attempted = True
                result.repair_success = repair_result.repair_success
                result.repair_attempts = repair_result.total_attempts
                result.llm_tokens_used = repair_result.llm_tokens_used
                result.repaired_code = repair_result.final_code
                
                if repair_result.repair_success:
                    # Replace transpiled code with repaired version
                    result.transpiled_code = repair_result.final_code
                    result.transpile_success = True  # Mark as ultimately successful
                    
            except Exception as repair_error:
                # Repair loop crashed - mark as attempted but failed
                result.repair_attempted = True
                result.repair_success = False
                result.repair_attempts = 0
                result.llm_tokens_used = 0
                # Silently continue - don't crash pipeline
                
        except Exception as e:
            # Compiler check failed, but don't crash the pipeline
            result.repair_attempted = False
            result.repair_success = False
        
        return result
