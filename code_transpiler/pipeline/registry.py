"""
pipeline/registry.py
====================
Language Registry — maps language names to their components.

Every language pair (source → target) is resolved through this registry.
Adding a new language = register its parser, lifter, and/or generator here.
"""

from __future__ import annotations
from typing import Dict, Type, Optional


class LanguageRegistry:
    """
    Central registry mapping language names to pipeline components.

    Supported source languages: Python, Java, JavaScript
    Supported target languages: Python, Java, JavaScript, C, C++
    """

    def __init__(self):
        self._parsers: Dict[str, object] = {}
        self._lifters: Dict[str, object] = {}
        self._generators: Dict[str, object] = {}

        # Valid language pairs: source → list of valid targets
        self.LANGUAGE_PAIRS: Dict[str, list] = {
            "Python":     ["Java", "JavaScript", "C", "C++"],
            "Java":       ["Python", "JavaScript"],
            "JavaScript": ["Java", "Python"],
        }

        # All valid target languages
        self.TARGET_LANGUAGES = {"Python", "Java", "JavaScript", "C", "C++"}

        # All valid source languages
        self.SOURCE_LANGUAGES = set(self.LANGUAGE_PAIRS.keys())

    # ── Registration ──────────────────────────────────────────────────────

    def register_parser(self, language: str, parser) -> None:
        """Register a parser for a source language."""
        self._parsers[language] = parser

    def register_lifter(self, language: str, lifter) -> None:
        """Register a lifter for a source language."""
        self._lifters[language] = lifter

    def register_generator(self, language: str, generator) -> None:
        """Register a code generator for a target language."""
        self._generators[language] = generator

    # ── Lookup ────────────────────────────────────────────────────────────

    def get_parser(self, language: str):
        """Get the parser for a source language."""
        if language not in self._parsers:
            raise ValueError(
                f"No parser registered for '{language}'. "
                f"Registered: {list(self._parsers.keys())}"
            )
        return self._parsers[language]

    def get_lifter(self, language: str):
        """Get the lifter for a source language."""
        if language not in self._lifters:
            raise ValueError(
                f"No lifter registered for '{language}'. "
                f"Registered: {list(self._lifters.keys())}"
            )
        return self._lifters[language]

    def get_generator(self, language: str):
        """Get the code generator for a target language."""
        if language not in self._generators:
            raise ValueError(
                f"No generator registered for '{language}'. "
                f"Registered: {list(self._generators.keys())}"
            )
        return self._generators[language]

    # ── Validation ────────────────────────────────────────────────────────

    def is_valid_pair(self, source_lang: str, target_lang: str) -> bool:
        """Check if a source → target pair is supported."""
        return target_lang in self.LANGUAGE_PAIRS.get(source_lang, [])

    def get_valid_targets(self, source_lang: str) -> list:
        """Get all valid target languages for a given source language."""
        return self.LANGUAGE_PAIRS.get(source_lang, [])

    def is_registered(self, language: str) -> dict:
        """Check registration status of a language."""
        return {
            "has_parser":    language in self._parsers,
            "has_lifter":    language in self._lifters,
            "has_generator": language in self._generators,
        }

    def summary(self) -> str:
        """Print a summary of all registered components."""
        lines = ["LanguageRegistry Summary:"]
        lines.append(f"  Parsers    : {sorted(self._parsers.keys())}")
        lines.append(f"  Lifters    : {sorted(self._lifters.keys())}")
        lines.append(f"  Generators : {sorted(self._generators.keys())}")
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────

def build_registry() -> LanguageRegistry:
    """
    Build and return the fully configured LanguageRegistry.
    All parsers, lifters, and generators are registered here.
    """
    from parsing.python_parser import PythonParser
    from parsing.treesitter_parser import TreeSitterParser
    from lifting.python_lifter import PythonLifter
    from lifting.java_lifter import JavaLifter
    from lifting.javascript_lifter import JavaScriptLifter
    from codegen.python_generator import PythonGenerator
    from codegen.java_generator import JavaGenerator
    from codegen.javascript_generator import JavaScriptGenerator
    from codegen.c_generator import CGenerator
    from codegen.cpp_generator import CppGenerator

    registry = LanguageRegistry()

    # Parsers (source languages only)
    registry.register_parser("Python",     PythonParser())
    registry.register_parser("Java",       TreeSitterParser("java"))
    registry.register_parser("JavaScript", TreeSitterParser("javascript"))

    # Lifters (source languages only)
    registry.register_lifter("Python",     PythonLifter())
    registry.register_lifter("Java",       JavaLifter())
    registry.register_lifter("JavaScript", JavaScriptLifter())

    # Generators (all 5 target languages)
    registry.register_generator("Python",     PythonGenerator())
    registry.register_generator("Java",       JavaGenerator())
    registry.register_generator("JavaScript", JavaScriptGenerator())
    registry.register_generator("C",          CGenerator())
    registry.register_generator("C++",        CppGenerator())

    return registry
