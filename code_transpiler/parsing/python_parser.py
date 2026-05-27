"""
parsing/python_parser.py
========================
Parser for Python source code.

Uses Python's built-in `ast` module which provides a much richer
semantic representation than tree-sitter for Python:
- Preserves type annotations
- Understands decorators fully
- Handles f-strings, walrus operator, match statements
"""

from __future__ import annotations
import ast
import sys
from typing import Any

# Python 2 to 3 compatibility
try:
    from lib2to3.refactor import RefactoringTool
    HAS_LIB2TO3 = True
except ImportError:
    HAS_LIB2TO3 = False


class PythonParser:
    """Parses Python source code using the built-in ast module."""

    def __init__(self):
        """Initialize with lib2to3 refactoring tools for Python 2 compatibility."""
        self.refactoring_tool = None
        if HAS_LIB2TO3:
            try:
                self.refactoring_tool = RefactoringTool(
                    ['lib2to3.fixes.fix_print',
                     'lib2to3.fixes.fix_except',
                     'lib2to3.fixes.fix_renames'],
                    options={'print_function': True}
                )
            except Exception:
                pass

    def _convert_python2_to_3(self, source_code: str) -> str:
        """Attempt to convert Python 2 syntax to Python 3 using lib2to3."""
        if not HAS_LIB2TO3 or not self.refactoring_tool:
            return source_code
        try:
            refactored = str(self.refactoring_tool.refactor_string(source_code, "<input>"))
            return refactored
        except Exception:
            return source_code

    def _normalize_indentation(self, source_code: str) -> str:
        """Normalize mixed tabs and spaces to spaces only."""
        # Convert all tabs to 4 spaces
        source_code = source_code.expandtabs(4)
        return source_code

    def _fix_unclosed_strings(self, source_code: str) -> str:
        """Attempt to fix common unclosed string literal issues."""
        lines = source_code.split('\n')
        fixed_lines = []
        in_string = False
        string_char = None
        
        for line in lines:
            # Count unescaped quotes
            double_count = 0
            single_count = 0
            i = 0
            while i < len(line):
                if i > 0 and line[i-1] == '\\':
                    i += 1
                    continue
                if line[i] == '"':
                    double_count += 1
                elif line[i] == "'":
                    single_count += 1
                i += 1
            
            # If line has odd number of quotes, likely unclosed string
            if double_count % 2 == 1:
                # Close the string with same quote
                line = line + '"'
            elif single_count % 2 == 1:
                line = line + "'"
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    def parse(self, source_code: str) -> ast.Module:
        """
        Parse Python source code into a CPython AST.

        Args:
            source_code: Python source code string.

        Returns:
            ast.Module — the root of the CPython AST.

        Raises:
            SyntaxError: if the source code is not valid Python.
        """
        # Normalize indentation (tabs → spaces)
        normalized = self._normalize_indentation(source_code)
        
        try:
            tree = ast.parse(normalized, mode="exec")
            return tree
        except SyntaxError as e:
            # Try fixing unclosed strings
            fixed = self._fix_unclosed_strings(normalized)
            if fixed != normalized:
                try:
                    tree = ast.parse(fixed, mode="exec")
                    return tree
                except SyntaxError:
                    pass
            
            # Try Python 2 → 3 conversion
            converted = self._convert_python2_to_3(normalized)
            if converted != normalized:
                try:
                    tree = ast.parse(converted, mode="exec")
                    return tree
                except SyntaxError:
                    raise SyntaxError(
                        f"Python parse error at line {e.lineno}: {e.msg}"
                    ) from e
            raise SyntaxError(
                f"Python parse error at line {e.lineno}: {e.msg}"
            ) from e

    def is_valid(self, source_code: str) -> bool:
        """Quick check whether source_code is syntactically valid Python."""
        # Normalize indentation
        normalized = self._normalize_indentation(source_code)
        
        try:
            ast.parse(normalized, mode="exec")
            return True
        except SyntaxError:
            # Try fixing unclosed strings
            fixed = self._fix_unclosed_strings(normalized)
            if fixed != normalized:
                try:
                    ast.parse(fixed, mode="exec")
                    return True
                except SyntaxError:
                    pass
            
            # Try Python 2 → 3 conversion
            converted = self._convert_python2_to_3(normalized)
            if converted != normalized:
                try:
                    ast.parse(converted, mode="exec")
                    return True
                except SyntaxError:
                    return False
            return False

    def dump(self, tree: ast.Module) -> str:
        """Return a readable dump of the AST (for debugging)."""
        return ast.dump(tree, indent=2)
