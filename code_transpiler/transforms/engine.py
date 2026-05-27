"""
transforms/engine.py
====================
Stage 4 Transform Engine — ALL passes for maximum compilation improvement.

Passes for C / C++ targets:
  1. pass_range_to_forloop       — for x in range(n) -> for(int x=0;x<n;x+=1)
  2. pass_input_to_scanf         — x=input("msg")    -> printf+scanf
  3. pass_string_methods_to_c    — s.lower()         -> str_lower(s)
  4. pass_strip_python_globals   — __name__,__author__ -> removed
  5. pass_flatten_main_guard     — if __name__=="__main__": -> body only
  6. pass_sys_to_c               — sys.exit() -> exit(), sys.argv -> argv
  7. pass_infer_variable_types   — x=5 -> int x=5 (basic type inference)
  8. pass_strip_python_typing    — Optional[X],List[X] -> None annotation

Passes for Python target:
  9. pass_clean_java_types       — String[],List<T> -> None annotation
"""

from __future__ import annotations
from ir.nodes import (
    CanonicalNode, Module, FunctionDef, ClassDef,
    ForEachLoop, ForLoop, ListComp, Assignment, VarDecl, AugAssignment,
    ExprStmt, PrintStmt, Call, Name, Attribute,
    Literal, BinaryOp, ListLiteral, IfStmt, CompareOp,
    WhileLoop, TryExcept, Param, Return, DictLiteral,
    TupleLiteral, SetLiteral,
)
from typing import List, Callable, Optional, Set


TransformPass = Callable[[Module, str, str], Module]


def run_transforms(ir: Module, source_lang: str, target_lang: str) -> Module:
    """Run all applicable transform passes on the Canonical IR."""
    for pass_fn in _get_passes(source_lang, target_lang):
        ir = pass_fn(ir, source_lang, target_lang)
    return ir


def _get_passes(source_lang: str, target_lang: str) -> List[TransformPass]:
    passes = []
    if target_lang in ("C", "C++"):
        passes.append(pass_strip_python_globals)    # Remove __name__, __author__
        passes.append(pass_flatten_main_guard)      # Flatten if __name__=="__main__"
        passes.append(pass_strip_python_typing)     # Remove Optional[X], List[X] etc.
        passes.append(pass_sys_to_c)               # sys.exit()->exit(), sys.argv->argv
        passes.append(pass_range_to_forloop)        # range() -> C for loop
        passes.append(pass_input_to_scanf)          # input() -> scanf
        passes.append(pass_string_methods_to_c)    # s.lower() -> str_lower(s)
        passes.append(pass_infer_variable_types)   # x=5 -> int x=5
    if target_lang == "Python" and source_lang == "Java":
        passes.append(pass_clean_java_types)        # Strip String[], List<T>
    return passes


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — range() → C-style ForLoop
# ─────────────────────────────────────────────────────────────────────────────

def pass_range_to_forloop(ir: Module, src: str, tgt: str) -> Module:
    """for x in range(n) -> for (int x=0; x<n; x+=1)"""
    _walk_and_fix_bodies(ir, _range_fix)
    return ir


def _range_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if (isinstance(stmt, ForEachLoop)
                and isinstance(stmt.iterable, Call)
                and isinstance(stmt.iterable.func, Name)
                and stmt.iterable.func.id == "range"):
            args = stmt.iterable.args
            if len(args) == 1:
                start = Literal(value=0, kind="int")
                stop  = args[0]
                step  = Literal(value=1, kind="int")
            elif len(args) == 2:
                start, stop = args[0], args[1]
                step = Literal(value=1, kind="int")
            elif len(args) == 3:
                start, stop, step = args[0], args[1], args[2]
            else:
                out.append(stmt); continue
            var = stmt.target if stmt.target else "_i"
            out.append(ForLoop(
                init=VarDecl(name=var, type_annotation="int", value=start),
                condition=CompareOp(left=Name(id=var), op="<", right=stop),
                update=AugAssignment(target=Name(id=var), op="+=", value=step),
                body=stmt.body,
            ))
        else:
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — input() → printf + char buf + scanf
# ─────────────────────────────────────────────────────────────────────────────

def pass_input_to_scanf(ir: Module, src: str, tgt: str) -> Module:
    """x = input("Enter: ") -> printf("Enter: "); char x[256]; scanf("%s", x);"""
    _walk_and_fix_bodies(ir, _input_fix)
    return ir


def _input_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if (isinstance(stmt, Assignment)
                and isinstance(stmt.value, Call)
                and isinstance(stmt.value.func, Name)
                and stmt.value.func.id == "input"):
            args        = stmt.value.args
            target_name = stmt.target.id if isinstance(stmt.target, Name) else "_buf"
            if args:
                out.append(ExprStmt(expr=Call(func=Name(id="printf"), args=[args[0]])))
            out.append(VarDecl(name=target_name, type_annotation="char",
                               value=Literal(value=256, kind="int")))
            out.append(ExprStmt(expr=Call(func=Name(id="scanf"),
                args=[Literal(value="%s", kind="string"), Name(id=target_name)])))
        else:
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3 — String methods → C helper functions
# ─────────────────────────────────────────────────────────────────────────────

_STR_MAP = {
    "lower": "str_lower", "upper": "str_upper",
    "strip": "str_strip", "lstrip": "str_lstrip", "rstrip": "str_rstrip",
    "replace": "str_replace", "split": "str_split", "join": "str_join",
    "find": "str_find", "startswith": "str_startswith",
    "endswith": "str_endswith", "isdigit": "str_isdigit",
    "isalpha": "str_isalpha", "count": "str_count", "format": "str_format",
    "append": "arr_append", "extend": "arr_extend", "pop": "arr_pop",
    "sort": "arr_sort", "reverse": "arr_reverse", "index": "arr_index",
    "keys": "dict_keys", "values": "dict_values", "items": "dict_items",
    "get": "dict_get", "update": "dict_update",
    "encode": "str_encode", "decode": "str_decode",
}


def pass_string_methods_to_c(ir: Module, src: str, tgt: str) -> Module:
    """s.lower() -> str_lower(s),  s.replace(a,b) -> str_replace(s,a,b)"""
    _remap_calls(ir)
    return ir


def _remap_calls(node: CanonicalNode):
    if node is None:
        return
    for fname, fval in node.__dict__.items():
        if isinstance(fval, Call):
            if (isinstance(fval.func, Attribute)
                    and fval.func.attr in _STR_MAP):
                obj           = fval.func.obj
                fval.func     = Name(id=_STR_MAP[fval.func.attr])
                fval.args     = [obj] + fval.args
            _remap_calls(fval)
        elif isinstance(fval, CanonicalNode):
            _remap_calls(fval)
        elif isinstance(fval, list):
            for item in fval:
                if isinstance(item, CanonicalNode):
                    _remap_calls(item)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 4 — Strip Python dunder globals (__name__, __author__, etc.)
# ─────────────────────────────────────────────────────────────────────────────

_DUNDER_VARS: Set[str] = {
    "__name__", "__file__", "__doc__", "__author__", "__version__",
    "__all__", "__package__", "__spec__", "__license__", "__email__",
    "__maintainer__", "__status__", "__copyright__", "__description__",
}


def pass_strip_python_globals(ir: Module, src: str, tgt: str) -> Module:
    """Remove __author__ = ..., __version__ = ... etc. from module body."""
    ir.body = _strip_dunders(ir.body)
    return ir


def _strip_dunders(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if isinstance(stmt, Assignment) and isinstance(stmt.target, Name):
            if stmt.target.id in _DUNDER_VARS:
                continue
        if isinstance(stmt, VarDecl) and stmt.name in _DUNDER_VARS:
            continue
        out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 5 — Flatten if __name__ == "__main__": body into module level
# ─────────────────────────────────────────────────────────────────────────────

def pass_flatten_main_guard(ir: Module, src: str, tgt: str) -> Module:
    """
    if __name__ == "__main__":
        do_stuff()
    ->
    do_stuff()    (body inlined at module level, or into main())
    """
    new_body = []
    for stmt in ir.body:
        if _is_main_guard(stmt):
            # Inline the body — these become top-level statements
            new_body.extend(stmt.then_body)
        else:
            new_body.append(stmt)
    ir.body = new_body
    return ir


def _is_main_guard(stmt) -> bool:
    if not isinstance(stmt, IfStmt):
        return False
    cond = stmt.condition
    if not isinstance(cond, CompareOp):
        return False
    left_is_name = isinstance(cond.left, Name) and cond.left.id == "__name__"
    right_is_main = (isinstance(cond.right, Literal)
                     and str(cond.right.value) == "__main__")
    return left_is_name and right_is_main and cond.op == "=="


# ─────────────────────────────────────────────────────────────────────────────
# Pass 6 — sys module → C equivalents
# ─────────────────────────────────────────────────────────────────────────────

def pass_sys_to_c(ir: Module, src: str, tgt: str) -> Module:
    """
    sys.exit(0)   -> exit(0)
    sys.exit()    -> exit(0)
    sys.argv      -> argv
    sys.stdin     -> stdin
    sys.stdout    -> stdout
    sys.stderr    -> stderr
    """
    _remap_sys_calls(ir)
    return ir


def _remap_sys_calls(node: CanonicalNode):
    if node is None:
        return
    for fname, fval in node.__dict__.items():
        if isinstance(fval, Call):
            # sys.exit(...) -> exit(...)
            if (isinstance(fval.func, Attribute)
                    and isinstance(fval.func.obj, Name)
                    and fval.func.obj.id == "sys"):
                attr = fval.func.attr
                if attr == "exit":
                    fval.func = Name(id="exit")
                    if not fval.args:
                        fval.args = [Literal(value=0, kind="int")]
                elif attr in ("stdin", "stdout", "stderr"):
                    fval.func = Name(id=attr)
            _remap_sys_calls(fval)
        elif isinstance(fval, Attribute):
            # sys.argv -> argv, sys.stdin -> stdin
            if (isinstance(fval.obj, Name) and fval.obj.id == "sys"):
                attr_map = {"argv": "argv", "stdin": "stdin",
                            "stdout": "stdout", "stderr": "stderr",
                            "maxsize": "INT_MAX", "version": "\"3\""}
                if fval.attr in attr_map:
                    # Replace in-place by changing the node's fields
                    fval.obj  = Name(id="")
                    fval.attr = attr_map[fval.attr]
        elif isinstance(fval, CanonicalNode):
            _remap_sys_calls(fval)
        elif isinstance(fval, list):
            for item in fval:
                if isinstance(item, CanonicalNode):
                    _remap_sys_calls(item)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 7 — Basic type inference for variable declarations
# ─────────────────────────────────────────────────────────────────────────────

def pass_infer_variable_types(ir: Module, src: str, tgt: str) -> Module:
    """
    Convert first assignment of each variable to a typed VarDecl.
    x = 5        -> int x = 5;
    name = "hi"  -> char* name = "hi";
    pi = 3.14    -> double pi = 3.14;
    """
    # Walk all function bodies + top-level body
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            node.body = _infer_in_body(node.body)
    # Top-level (goes into main() in C)
    ir.body = _infer_in_body(ir.body)
    return ir


def _infer_type_from_value(value_node) -> str:
    """Infer C type from an expression node."""
    if isinstance(value_node, Literal):
        mapping = {"int": "int", "float": "double",
                   "string": "char*", "bool": "int", "null": "void*"}
        return mapping.get(value_node.kind, "int")
    if isinstance(value_node, ListLiteral):
        return "int*"
    if isinstance(value_node, DictLiteral):
        return "void*"
    if isinstance(value_node, (TupleLiteral, SetLiteral)):
        return "int*"
    if isinstance(value_node, Call):
        # Common patterns
        if isinstance(value_node.func, Name):
            name_map = {
                "int": "int", "float": "double", "str": "char*",
                "bool": "int", "len": "int", "range": "int*",
                "list": "int*", "dict": "void*", "set": "void*",
            }
            return name_map.get(value_node.func.id, "int")
    if isinstance(value_node, BinaryOp):
        # Try to infer from left operand
        return _infer_type_from_value(value_node.left)
    return "int"  # Safe default


def _infer_in_body(stmts: list) -> list:
    """Convert first Assignment for each new variable into a VarDecl."""
    declared: Set[str] = set()
    out = []
    for stmt in stmts:
        # Skip: already declared, dunder vars, or non-Name targets
        if (isinstance(stmt, Assignment)
                and isinstance(stmt.target, Name)
                and stmt.target.id not in declared
                and not stmt.target.id.startswith("__")):
            var = stmt.target.id
            declared.add(var)
            c_type = _infer_type_from_value(stmt.value)
            out.append(VarDecl(
                name=var,
                type_annotation=c_type,
                value=stmt.value,
            ))
        else:
            # Track VarDecl names too
            if isinstance(stmt, VarDecl):
                declared.add(stmt.name)
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 8 — Strip Python typing module annotations
# ─────────────────────────────────────────────────────────────────────────────

_TYPING_PREFIXES = (
    "Optional", "List", "Dict", "Set", "Tuple", "Union", "Any",
    "Callable", "Generator", "Iterator", "Iterable", "Sequence",
    "FrozenSet", "Type", "ClassVar", "Final",
)


def pass_strip_python_typing(ir: Module, src: str, tgt: str) -> Module:
    """Strip Python typing annotations: Optional[X], List[X], Dict[K,V] etc."""
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            for p in node.params:
                p.type_annotation = _strip_typing(p.type_annotation)
            node.return_type = _strip_typing(node.return_type)
        elif isinstance(node, VarDecl):
            node.type_annotation = _strip_typing(node.type_annotation)
    return ir


def _strip_typing(ann: Optional[str]) -> Optional[str]:
    if ann is None:
        return None
    # Strip anything that looks like a typing generic: Optional[X], List[X]
    for prefix in _TYPING_PREFIXES:
        if ann.startswith(prefix):
            return None
    # Also strip if contains brackets (any generic)
    if "[" in ann or "]" in ann:
        return None
    return ann


# ─────────────────────────────────────────────────────────────────────────────
# Pass 9 — Clean Java type annotations for Python target
# ─────────────────────────────────────────────────────────────────────────────

_JAVA_TO_PY = {
    "String": "str", "boolean": "bool", "Boolean": "bool",
    "long": "int", "Long": "int", "short": "int", "byte": "int",
    "double": "float", "Double": "float", "float": "float",
    "Integer": "int", "Character": "str", "void": "None", "Object": None,
}


def pass_clean_java_types(ir: Module, src: str, tgt: str) -> Module:
    """Strip Java-specific type annotations for Python target."""
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            for p in node.params:
                p.type_annotation = _clean_java(p.type_annotation)
            node.return_type = _clean_java(node.return_type)
        elif isinstance(node, VarDecl):
            node.type_annotation = _clean_java(node.type_annotation)
    return ir


def _clean_java(ann: Optional[str]) -> Optional[str]:
    if ann is None:
        return None
    if "[" in ann or "]" in ann or "<" in ann or ">" in ann:
        return None
    return _JAVA_TO_PY.get(ann, ann)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _all_nodes(node: CanonicalNode):
    """Yield every CanonicalNode in the tree (depth-first)."""
    if node is None:
        return
    yield node
    for v in node.__dict__.values():
        if isinstance(v, CanonicalNode):
            yield from _all_nodes(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, CanonicalNode):
                    yield from _all_nodes(item)


def _walk_and_fix_bodies(node: CanonicalNode, fix_fn):
    """
    Recursively walk the tree. For every list-of-statements body,
    apply fix_fn which may expand 1 statement into multiple.
    """
    if node is None:
        return
    for fname in ("body", "then_body", "else_body", "try_body", "finally_body"):
        body = getattr(node, fname, None)
        if isinstance(body, list):
            fixed = fix_fn(body)
            setattr(node, fname, fixed)
            for child in fixed:
                if isinstance(child, CanonicalNode):
                    _walk_and_fix_bodies(child, fix_fn)
    for clause in getattr(node, "elif_clauses", []):
        if hasattr(clause, "body"):
            clause.body = fix_fn(clause.body)
            for child in clause.body:
                if isinstance(child, CanonicalNode):
                    _walk_and_fix_bodies(child, fix_fn)
    for handler in getattr(node, "handlers", []):
        if hasattr(handler, "body"):
            handler.body = fix_fn(handler.body)
