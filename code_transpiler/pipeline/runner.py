"""
pipeline/runner.py
==================
PipelineRunner — orchestrates all 5 stages for a single transpilation job.

Input:  source_code (str) + source_lang (str) + target_lang (str)
Output: TranspileResult

Stage flow:
    1. Preprocessing  — clean the source code
    2. Parsing        — source code → syntax tree
    3. Lifting        — syntax tree → Canonical IR
    4. Transforms     — apply target-specific passes
    5. Code Gen       — Canonical IR → target source code
"""

from __future__ import annotations
import time
import hashlib
import traceback
from dataclasses import dataclass, field
from typing import Optional

from pipeline.registry import LanguageRegistry
from transforms.engine import run_transforms


@dataclass
class TranspileResult:
    """Result of a single transpilation job."""
    source_lang: str
    target_lang: str
    source_code: str
    transpiled_code: Optional[str] = None
    transpile_success: bool = False
    transpile_error: Optional[str] = None
    transpile_stage: Optional[str] = None   # which stage failed
    transpile_time_ms: int = 0
    cache_hit: bool = False


class PipelineRunner:
    """
    Runs the 5-stage transpilation pipeline.

    One PipelineRunner instance is reused per SLURM task (it's stateless
    per call — the registry and its components are shared safely).
    """

    def __init__(self, registry: LanguageRegistry, cache=None):
        self.registry = registry
        self.cache = cache  # Optional cache instance

    def transpile(self, source_code: str,
                  source_lang: str,
                  target_lang: str) -> TranspileResult:
        """
        Run the full 5-stage pipeline.

        Args:
            source_code: The source code string.
            source_lang: Source language name (e.g. 'Python').
            target_lang: Target language name (e.g. 'Java').

        Returns:
            TranspileResult with the transpiled code or error info.
        """
        start = time.monotonic()
        result = TranspileResult(
            source_lang=source_lang,
            target_lang=target_lang,
            source_code=source_code,
        )

        # Validate pair
        if not self.registry.is_valid_pair(source_lang, target_lang):
            result.transpile_error = (
                f"Unsupported pair: {source_lang} → {target_lang}"
            )
            result.transpile_stage = "validation"
            result.transpile_time_ms = _elapsed_ms(start)
            return result

        # Check cache
        if self.cache:
            cache_key = _cache_key(source_code, source_lang, target_lang)
            cached = self.cache.get(cache_key)
            if cached is not None:
                result.transpiled_code = cached
                result.transpile_success = True
                result.cache_hit = True
                result.transpile_time_ms = _elapsed_ms(start)
                return result

        try:
            # ── Stage 1: Preprocessing ────────────────────────────────────
            result.transpile_stage = "preprocessing"
            clean_source = _preprocess(source_code)

            # ── Stage 2: Parsing ──────────────────────────────────────────
            result.transpile_stage = "parsing"
            parser = self.registry.get_parser(source_lang)
            syntax_tree = parser.parse(clean_source)

            # ── Stage 3: Lifting ──────────────────────────────────────────
            result.transpile_stage = "lifting"
            lifter = self.registry.get_lifter(source_lang)
            canonical_ir = lifter.lift(syntax_tree, clean_source)

            # ── Stage 4: Transforms ───────────────────────────────────────
            result.transpile_stage = "transforms"
            canonical_ir = run_transforms(canonical_ir, source_lang, target_lang)

            # ── Stage 5: Code Generation ──────────────────────────────────
            result.transpile_stage = "codegen"
            generator = self.registry.get_generator(target_lang)
            output_code = generator.generate(canonical_ir)

            # Success
            result.transpiled_code = output_code
            result.transpile_success = True
            result.transpile_stage = None

            # Store in cache
            if self.cache:
                self.cache.set(cache_key, output_code)

        except SyntaxError as e:
            result.transpile_error = f"SyntaxError in {result.transpile_stage}: {e}"
        except ValueError as e:
            result.transpile_error = f"ValueError in {result.transpile_stage}: {e}"
        except Exception as e:
            result.transpile_error = (
                f"Error in {result.transpile_stage}: "
                f"{type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}"
            )

        result.transpile_time_ms = _elapsed_ms(start)
        return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _preprocess(source_code: str) -> str:
    """
    Stage 1: Clean the source code before parsing.
    - Normalize line endings
    - Strip BOM marker
    - Strip shell shebang lines
    - Strip trailing whitespace
    """
    # Normalize line endings
    code = source_code.replace("\r\n", "\n").replace("\r", "\n")

    # Strip BOM
    if code.startswith("\ufeff"):
        code = code[1:]

    # Strip shebang
    lines = code.split("\n")
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    code = "\n".join(lines)

    # Strip trailing whitespace from each line
    code = "\n".join(line.rstrip() for line in code.split("\n"))

    return code.strip()


def _cache_key(source_code: str, source_lang: str, target_lang: str) -> str:
    """Generate a deterministic cache key for a transpilation job."""
    content = f"{source_lang}:{target_lang}:{source_code}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _elapsed_ms(start: float) -> int:
    """Return elapsed milliseconds since start."""
    return int((time.monotonic() - start) * 1000)
