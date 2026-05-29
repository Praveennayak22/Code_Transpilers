"""
parsing/treesitter_parser.py
============================
Parser for Java and JavaScript using tree-sitter.

tree-sitter produces a Concrete Syntax Tree (CST) with every token
preserved. The Lifter then walks this CST to build Canonical IR.
"""

from __future__ import annotations
from typing import Any


class TreeSitterParser:
    """Parses Java, JavaScript, C, or C++ source using tree-sitter."""

    LANGUAGE_MAP = {
        "java":       "tree_sitter_java",
        "javascript": "tree_sitter_javascript",
        "c":          "tree_sitter_c",
        "cpp":        "tree_sitter_cpp",
    }

    def __init__(self, language: str):
        """
        Args:
            language: 'java' or 'javascript'
        """
        self.language_name = language.lower()
        self._parser = None
        self._language = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load tree-sitter to avoid import errors if not installed."""
        if self._loaded:
            return
        try:
            from tree_sitter import Language, Parser

            lang = self.language_name
            if lang == "java":
                import tree_sitter_java
                self._language = Language(tree_sitter_java.language())
            elif lang == "javascript":
                import tree_sitter_javascript
                self._language = Language(tree_sitter_javascript.language())
            elif lang == "c":
                import tree_sitter_c
                self._language = Language(tree_sitter_c.language())
            elif lang == "cpp":
                import tree_sitter_cpp
                self._language = Language(tree_sitter_cpp.language())
            else:
                raise ValueError(f"Unsupported language: {self.language_name}")

            self._parser = Parser(self._language)
            self._loaded = True

        except ImportError as e:
            raise ImportError(
                f"tree-sitter not installed. Run: "
                f"pip install tree-sitter tree-sitter-java tree-sitter-javascript "
                f"tree-sitter-c tree-sitter-cpp\n"
                f"Original error: {e}"
            ) from e

    def parse(self, source_code: str):
        """
        Parse source code into a tree-sitter Tree (CST).

        Args:
            source_code: Java or JavaScript source code string.

        Returns:
            tree_sitter.Tree — the root of the CST.
        """
        self._ensure_loaded()
        source_bytes = source_code.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        return tree

    def is_valid(self, source_code: str) -> bool:
        """Check if the parsed tree has no errors."""
        try:
            tree = self.parse(source_code)
            return not tree.root_node.has_error
        except Exception:
            return False

    def get_node_text(self, node, source_bytes: bytes) -> str:
        """Extract text for a given tree-sitter node."""
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8")

    def dump(self, tree, source_code: str) -> str:
        """Return a readable dump of the CST (for debugging)."""
        source_bytes = source_code.encode("utf-8")
        lines = []

        def _dump(node, indent=0):
            text = self.get_node_text(node, source_bytes)
            preview = text[:40].replace("\n", "\\n") if text else ""
            lines.append(f"{'  ' * indent}{node.type}: {repr(preview)}")
            for child in node.children:
                _dump(child, indent + 1)

        _dump(tree.root_node)
        return "\n".join(lines)
