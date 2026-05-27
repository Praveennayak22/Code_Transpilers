"""
lifting/base_lifter.py
=======================
Abstract base class for all lifters.
"""

from __future__ import annotations
from ir.nodes import Module


class BaseLifter:
    """Abstract lifter interface."""

    def lift(self, tree) -> Module:
        raise NotImplementedError(
            f"{type(self).__name__} must implement lift()"
        )
