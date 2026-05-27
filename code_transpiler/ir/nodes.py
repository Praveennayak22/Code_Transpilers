"""
ir/nodes.py
===========
Canonical Intermediate Representation (IR) node definitions.

These dataclasses are the language-neutral AST that sits between
the source language lifters and the target language generators.

Every construct that can appear in Python, Java, or JavaScript
has a corresponding CanonicalNode here.

Design inspired by SQLGlot's Expression hierarchy.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CanonicalNode:
    """Base class for all canonical IR nodes."""
    # Optional source location for debugging (line number in original file)
    source_line: Optional[int] = field(default=None, repr=False, compare=False)


# ─────────────────────────────────────────────────────────────────────────────
# Top-level
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Module(CanonicalNode):
    """Top-level module / file."""
    body: List[CanonicalNode] = field(default_factory=list)
    imports: List["Import"] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Declarations
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Param(CanonicalNode):
    """A function parameter."""
    name: str = ""
    type_annotation: Optional[str] = None     # e.g. "int", "String", None
    default_value: Optional[CanonicalNode] = None


@dataclass
class FunctionDef(CanonicalNode):
    """A function or method definition."""
    name: str = ""
    params: List[Param] = field(default_factory=list)
    body: List[CanonicalNode] = field(default_factory=list)
    return_type: Optional[str] = None         # e.g. "int", "void", None
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    is_static: bool = False
    access_modifier: str = "public"           # public / private / protected


@dataclass
class ClassDef(CanonicalNode):
    """A class definition."""
    name: str = ""
    bases: List[str] = field(default_factory=list)    # parent class names
    body: List[CanonicalNode] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class VarDecl(CanonicalNode):
    """A variable declaration (with optional type, used in Java/C/C++)."""
    name: str = ""
    type_annotation: Optional[str] = None
    value: Optional[CanonicalNode] = None
    is_const: bool = False                    # const / final


# ─────────────────────────────────────────────────────────────────────────────
# Statements
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Assignment(CanonicalNode):
    """An assignment: target = value."""
    target: Optional[CanonicalNode] = None
    value: Optional[CanonicalNode] = None
    type_annotation: Optional[str] = None    # for typed assignments


@dataclass
class AugAssignment(CanonicalNode):
    """An augmented assignment: target op= value (e.g. x += 1)."""
    target: Optional[CanonicalNode] = None
    op: str = "+="
    value: Optional[CanonicalNode] = None


@dataclass
class Return(CanonicalNode):
    """A return statement."""
    value: Optional[CanonicalNode] = None


@dataclass
class IfStmt(CanonicalNode):
    """An if / else-if / else statement."""
    condition: Optional[CanonicalNode] = None
    then_body: List[CanonicalNode] = field(default_factory=list)
    elif_clauses: List["ElifClause"] = field(default_factory=list)
    else_body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class ElifClause(CanonicalNode):
    """An elif / else-if clause."""
    condition: Optional[CanonicalNode] = None
    body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class WhileLoop(CanonicalNode):
    """A while loop."""
    condition: Optional[CanonicalNode] = None
    body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class ForLoop(CanonicalNode):
    """A C-style for loop: for(init; condition; update)."""
    init: Optional[CanonicalNode] = None
    condition: Optional[CanonicalNode] = None
    update: Optional[CanonicalNode] = None
    body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class ForEachLoop(CanonicalNode):
    """A for-each loop: for item in iterable / for(Type item : iterable)."""
    target: str = ""                          # loop variable name
    target_type: Optional[str] = None        # Java: type of loop variable
    iterable: Optional[CanonicalNode] = None
    body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class Break(CanonicalNode):
    """A break statement."""
    pass


@dataclass
class Continue(CanonicalNode):
    """A continue statement."""
    pass


@dataclass
class ExprStmt(CanonicalNode):
    """An expression used as a statement (e.g. a function call)."""
    expr: Optional[CanonicalNode] = None


@dataclass
class TryExcept(CanonicalNode):
    """A try/catch/except block."""
    try_body: List[CanonicalNode] = field(default_factory=list)
    handlers: List["ExceptHandler"] = field(default_factory=list)
    finally_body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class ExceptHandler(CanonicalNode):
    """A single except/catch handler."""
    exception_type: Optional[str] = None     # e.g. "ValueError", "Exception"
    name: Optional[str] = None               # the 'as e' part
    body: List[CanonicalNode] = field(default_factory=list)


@dataclass
class Raise(CanonicalNode):
    """A raise / throw statement."""
    exception: Optional[CanonicalNode] = None


@dataclass
class Delete(CanonicalNode):
    """A delete statement (del in Python)."""
    target: Optional[CanonicalNode] = None


@dataclass
class Assert(CanonicalNode):
    """An assert statement."""
    condition: Optional[CanonicalNode] = None
    message: Optional[CanonicalNode] = None


@dataclass
class Comment(CanonicalNode):
    """A comment."""
    text: str = ""


@dataclass
class Import(CanonicalNode):
    """An import statement."""
    module: str = ""
    alias: Optional[str] = None
    names: List[str] = field(default_factory=list)   # from X import a, b


@dataclass
class PrintStmt(CanonicalNode):
    """A print statement (Python print / System.out.println / console.log)."""
    args: List[CanonicalNode] = field(default_factory=list)
    sep: str = " "
    end: str = "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Expressions
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Name(CanonicalNode):
    """A variable or identifier reference."""
    id: str = ""


@dataclass
class Literal(CanonicalNode):
    """A literal value: int, float, string, bool, None/null."""
    value: Any = None
    kind: str = "int"       # "int" | "float" | "string" | "bool" | "null"


@dataclass
class BinaryOp(CanonicalNode):
    """A binary operation: left op right."""
    left: Optional[CanonicalNode] = None
    op: str = "+"
    right: Optional[CanonicalNode] = None


@dataclass
class UnaryOp(CanonicalNode):
    """A unary operation: op operand."""
    op: str = "-"           # "-" | "not" | "!" | "~"
    operand: Optional[CanonicalNode] = None


@dataclass
class CompareOp(CanonicalNode):
    """A comparison: left op right."""
    left: Optional[CanonicalNode] = None
    op: str = "=="          # "==" | "!=" | "<" | ">" | "<=" | ">=" | "in" | "not in"
    right: Optional[CanonicalNode] = None


@dataclass
class BoolOp(CanonicalNode):
    """A boolean operation: val1 and/or val2."""
    op: str = "and"         # "and" | "or"
    values: List[CanonicalNode] = field(default_factory=list)


@dataclass
class Call(CanonicalNode):
    """A function or method call."""
    func: Optional[CanonicalNode] = None     # Name or Attribute
    args: List[CanonicalNode] = field(default_factory=list)
    kwargs: List["Keyword"] = field(default_factory=list)


@dataclass
class Keyword(CanonicalNode):
    """A keyword argument in a function call: key=value."""
    key: str = ""
    value: Optional[CanonicalNode] = None


@dataclass
class Attribute(CanonicalNode):
    """Attribute access: obj.attr."""
    obj: Optional[CanonicalNode] = None
    attr: str = ""


@dataclass
class Index(CanonicalNode):
    """Index access: obj[index]."""
    obj: Optional[CanonicalNode] = None
    index: Optional[CanonicalNode] = None


@dataclass
class Slice(CanonicalNode):
    """Slice access: obj[start:stop:step]."""
    obj: Optional[CanonicalNode] = None
    start: Optional[CanonicalNode] = None
    stop: Optional[CanonicalNode] = None
    step: Optional[CanonicalNode] = None


@dataclass
class Ternary(CanonicalNode):
    """Ternary expression: value_if_true if condition else value_if_false."""
    condition: Optional[CanonicalNode] = None
    true_value: Optional[CanonicalNode] = None
    false_value: Optional[CanonicalNode] = None


@dataclass
class Lambda(CanonicalNode):
    """A lambda / arrow function."""
    params: List[Param] = field(default_factory=list)
    body: Optional[CanonicalNode] = None


# ─────────────────────────────────────────────────────────────────────────────
# Collections
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ListLiteral(CanonicalNode):
    """A list literal: [1, 2, 3]."""
    elements: List[CanonicalNode] = field(default_factory=list)


@dataclass
class DictLiteral(CanonicalNode):
    """A dict literal: {key: value, ...}."""
    keys: List[CanonicalNode] = field(default_factory=list)
    values: List[CanonicalNode] = field(default_factory=list)


@dataclass
class SetLiteral(CanonicalNode):
    """A set literal: {1, 2, 3}."""
    elements: List[CanonicalNode] = field(default_factory=list)


@dataclass
class TupleLiteral(CanonicalNode):
    """A tuple literal: (1, 2, 3)."""
    elements: List[CanonicalNode] = field(default_factory=list)


@dataclass
class ListComp(CanonicalNode):
    """A list comprehension: [expr for target in iterable if condition]."""
    element: Optional[CanonicalNode] = None
    target: str = ""
    iterable: Optional[CanonicalNode] = None
    condition: Optional[CanonicalNode] = None   # optional filter


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Operator mapping: canonical op string → per-language override
OPERATOR_MAP = {
    # Arithmetic
    "+": {"Python": "+", "Java": "+", "JavaScript": "+", "C": "+", "C++": "+"},
    "-": {"Python": "-", "Java": "-", "JavaScript": "-", "C": "-", "C++": "-"},
    "*": {"Python": "*", "Java": "*", "JavaScript": "*", "C": "*", "C++": "*"},
    "/": {"Python": "/", "Java": "/", "JavaScript": "/", "C": "/", "C++": "/"},
    "%": {"Python": "%", "Java": "%", "JavaScript": "%", "C": "%", "C++": "%"},
    "**": {"Python": "**", "Java": "Math.pow", "JavaScript": "**", "C": "pow", "C++": "pow"},
    # Comparison
    "==": {"Python": "==", "Java": "==", "JavaScript": "===", "C": "==", "C++": "=="},
    "!=": {"Python": "!=", "Java": "!=", "JavaScript": "!==", "C": "!=", "C++": "!="},
    "<":  {"Python": "<",  "Java": "<",  "JavaScript": "<",  "C": "<",  "C++": "<"},
    ">":  {"Python": ">",  "Java": ">",  "JavaScript": ">",  "C": ">",  "C++": ">"},
    "<=": {"Python": "<=", "Java": "<=", "JavaScript": "<=", "C": "<=", "C++": "<="},
    ">=": {"Python": ">=", "Java": ">=", "JavaScript": ">=", "C": ">=", "C++": ">="},
    # Boolean
    "and": {"Python": "and", "Java": "&&",  "JavaScript": "&&",  "C": "&&",  "C++": "&&"},
    "or":  {"Python": "or",  "Java": "||",  "JavaScript": "||",  "C": "||",  "C++": "||"},
    "not": {"Python": "not", "Java": "!",   "JavaScript": "!",   "C": "!",   "C++": "!"},
}
