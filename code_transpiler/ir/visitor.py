"""
ir/visitor.py
=============
IRVisitor base class.

Both Lifters (reading IR) and Generators (writing IR) use this visitor
to traverse CanonicalNode trees.

Usage:
    class MyVisitor(IRVisitor):
        def visit_FunctionDef(self, node: FunctionDef):
            # handle function definitions
            ...
"""

from __future__ import annotations
from typing import Any
from .nodes import CanonicalNode


class IRVisitor:
    """
    Base visitor for CanonicalNode trees.

    Dispatches to visit_<ClassName> methods.
    Falls back to generic_visit() if no specific method exists.
    """

    def visit(self, node: CanonicalNode) -> Any:
        """Dispatch to the appropriate visit_* method."""
        if node is None:
            return None
        method_name = f"visit_{type(node).__name__}"
        method = getattr(self, method_name, self.generic_visit)
        return method(node)

    def generic_visit(self, node: CanonicalNode) -> Any:
        """
        Called when no specific visit_* method exists.
        By default, visits all child nodes.
        """
        for field_name, field_value in node.__dict__.items():
            if isinstance(field_value, CanonicalNode):
                self.visit(field_value)
            elif isinstance(field_value, list):
                for item in field_value:
                    if isinstance(item, CanonicalNode):
                        self.visit(item)

    def visit_list(self, nodes: list) -> list:
        """Visit a list of nodes, returning a list of results."""
        return [self.visit(n) for n in nodes if n is not None]
