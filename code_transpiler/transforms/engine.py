"""
transforms/engine.py
====================
Stage 4 Transform Engine — target-language-specific IR adaptation passes.

Every language pair now has at least one guaranteed-firing pass that makes
transformed_IR meaningfully different from canonical_IR.

Passes for C / C++ targets:
  1.  pass_range_to_forloop       — for x in range(n) -> for(int x=0;x<n;x+=1)
  2.  pass_input_to_scanf         — x=input("msg")    -> printf+scanf
  3.  pass_string_methods_to_c    — s.lower()         -> str_lower(s)
  4.  pass_strip_python_globals   — __name__,__author__ -> removed
  5.  pass_flatten_main_guard     — if __name__=="__main__": -> body only
  6.  pass_sys_to_c               — sys.exit() -> exit(), sys.argv -> argv
  7.  pass_infer_variable_types   — x=5 -> int x=5 (basic type inference)
  8.  pass_strip_python_typing    — Optional[X],List[X] -> None annotation
  9.  pass_inject_c_headers       — auto-inject #include headers for used symbols

Passes for Java target:
  10. pass_python_types_to_java   — str->String, bool->boolean, int->int etc.
  11. pass_print_to_system_out    — PrintStmt -> System.out.println(...)
  12. pass_inject_java_imports    — auto-inject java.util.* etc. based on usage
  13. pass_wrap_in_java_class     — wrap all top-level functions in public class Main

Passes for JavaScript target:
  14. pass_vars_to_let            — bare Assignment at top/fn level -> let x = ...
  15. pass_print_to_console_log   — PrintStmt -> console.log(...)

Passes for Python target (from Java):
  16. pass_clean_java_types       — String[],List<T> -> None annotation

Passes for Python target (from C/C++):
  17. pass_strip_c_headers        — Remove stdio.h, stdlib.h imports
  18. pass_strip_c_main           — Remove main() wrapper
  19. pass_clean_java_types       — Reuse: strip any leftover type annotations

Passes for Python target (from JavaScript):
  20. pass_console_to_print       — console.log -> print
"""

from __future__ import annotations
from ir.nodes import (
    CanonicalNode, Module, FunctionDef, ClassDef,
    ForEachLoop, ForLoop, ListComp, Assignment, VarDecl, AugAssignment,
    ExprStmt, PrintStmt, Call, Name, Attribute,
    Literal, BinaryOp, ListLiteral, IfStmt, CompareOp,
    WhileLoop, TryExcept, Param, Return, DictLiteral, Import,
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

    # ── → C / C++ ─────────────────────────────────────────────────────────────
    if target_lang in ("C", "C++"):
        passes.append(pass_strip_docstrings)           # NEW — always fires
        passes.append(pass_strip_python_globals)
        passes.append(pass_flatten_main_guard)
        passes.append(pass_strip_python_typing)
        passes.append(pass_sys_to_c)
        passes.append(pass_range_to_forloop)
        passes.append(pass_input_to_scanf)
        passes.append(pass_string_methods_to_c)
        passes.append(pass_infer_variable_types)
        passes.append(pass_rename_c_keywords)          # NEW — rename reserved words
        if target_lang == "C++":
            passes.append(pass_strip_self_from_methods)  # NEW — self→this, __init__→ctor
            passes.append(pass_arr_append_to_push_back)  # NEW — arr_append→push_back
        passes.append(pass_inject_c_headers)

    # ── → Java ────────────────────────────────────────────────────────────────
    elif target_lang == "Java":
        passes.append(pass_strip_docstrings)           # strip docstrings first
        passes.append(pass_strip_self_from_methods)    # NEW — remove self, __init__→ctor
        passes.append(pass_rename_c_keywords)          # NEW — char→char_var etc.
        passes.append(pass_python_types_to_java)
        passes.append(pass_print_to_system_out)
        passes.append(pass_inject_java_imports)
        passes.append(pass_wrap_in_java_class)

    # ── → JavaScript ──────────────────────────────────────────────────────────
    elif target_lang == "JavaScript":
        passes.append(pass_strip_docstrings)           # NEW — raw strings → comments
        passes.append(pass_print_to_console_log)
        passes.append(pass_vars_to_let)

    # ── → Python ──────────────────────────────────────────────────────────────
    elif target_lang == "Python":
        if source_lang == "Java":
            passes.append(pass_clean_java_types)
        if source_lang in ("C", "C++"):
            passes.append(pass_strip_c_headers)
            passes.append(pass_strip_c_main)
            passes.append(pass_clean_java_types)
        if source_lang == "JavaScript":
            passes.append(pass_console_to_print)

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
# Pass 4 — Strip Python dunder globals
# ─────────────────────────────────────────────────────────────────────────────

_DUNDER_VARS: Set[str] = {
    "__name__", "__file__", "__doc__", "__author__", "__version__",
    "__all__", "__package__", "__spec__", "__license__", "__email__",
    "__maintainer__", "__status__", "__copyright__", "__description__",
}


def pass_strip_python_globals(ir: Module, src: str, tgt: str) -> Module:
    """Remove __author__ = ..., __version__ = ... etc."""
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
# Pass 5 — Flatten if __name__ == "__main__": body
# ─────────────────────────────────────────────────────────────────────────────

def pass_flatten_main_guard(ir: Module, src: str, tgt: str) -> Module:
    new_body = []
    for stmt in ir.body:
        if _is_main_guard(stmt):
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
    left_is_name  = isinstance(cond.left, Name) and cond.left.id == "__name__"
    right_is_main = (isinstance(cond.right, Literal)
                     and str(cond.right.value) == "__main__")
    return left_is_name and right_is_main and cond.op == "=="


# ─────────────────────────────────────────────────────────────────────────────
# Pass 6 — sys module → C equivalents
# ─────────────────────────────────────────────────────────────────────────────

def pass_sys_to_c(ir: Module, src: str, tgt: str) -> Module:
    _remap_sys_calls(ir)
    return ir


def _remap_sys_calls(node: CanonicalNode):
    if node is None:
        return
    for fname, fval in node.__dict__.items():
        if isinstance(fval, Call):
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
            if (isinstance(fval.obj, Name) and fval.obj.id == "sys"):
                attr_map = {"argv": "argv", "stdin": "stdin",
                            "stdout": "stdout", "stderr": "stderr",
                            "maxsize": "INT_MAX", "version": "\"3\""}
                if fval.attr in attr_map:
                    fval.obj  = Name(id="")
                    fval.attr = attr_map[fval.attr]
        elif isinstance(fval, CanonicalNode):
            _remap_sys_calls(fval)
        elif isinstance(fval, list):
            for item in fval:
                if isinstance(item, CanonicalNode):
                    _remap_sys_calls(item)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 7 — Basic type inference for C/C++ variable declarations
# ─────────────────────────────────────────────────────────────────────────────

def pass_infer_variable_types(ir: Module, src: str, tgt: str) -> Module:
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            node.body = _infer_in_body(node.body)
    ir.body = _infer_in_body(ir.body)
    return ir


def _infer_type_from_value(value_node) -> str:
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
        if isinstance(value_node.func, Name):
            name_map = {
                "int": "int", "float": "double", "str": "char*",
                "bool": "int", "len": "int", "range": "int*",
                "list": "int*", "dict": "void*", "set": "void*",
            }
            return name_map.get(value_node.func.id, "int")
    if isinstance(value_node, BinaryOp):
        return _infer_type_from_value(value_node.left)
    return "int"


def _infer_in_body(stmts: list) -> list:
    declared: Set[str] = set()
    out = []
    for stmt in stmts:
        if (isinstance(stmt, Assignment)
                and isinstance(stmt.target, Name)
                and stmt.target.id not in declared
                and not stmt.target.id.startswith("__")):
            var = stmt.target.id
            declared.add(var)
            c_type = _infer_type_from_value(stmt.value)
            out.append(VarDecl(name=var, type_annotation=c_type, value=stmt.value))
        else:
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
    for prefix in _TYPING_PREFIXES:
        if ann.startswith(prefix):
            return None
    if "[" in ann or "]" in ann:
        return None
    return ann


# ─────────────────────────────────────────────────────────────────────────────
# Pass 9 — NEW: Inject C/C++ #include headers based on symbols used
# ─────────────────────────────────────────────────────────────────────────────

# Maps function/symbol names → the C/C++ header that provides them
_C_SYMBOL_TO_HEADER = {
    # stdio.h
    "printf": "stdio.h", "scanf": "stdio.h", "fprintf": "stdio.h",
    "fscanf": "stdio.h", "sprintf": "stdio.h", "sscanf": "stdio.h",
    "fopen": "stdio.h", "fclose": "stdio.h", "fread": "stdio.h",
    "fwrite": "stdio.h", "fgets": "stdio.h", "fputs": "stdio.h",
    "puts": "stdio.h", "gets": "stdio.h", "getchar": "stdio.h",
    "putchar": "stdio.h", "EOF": "stdio.h", "FILE": "stdio.h",
    # stdlib.h
    "malloc": "stdlib.h", "calloc": "stdlib.h", "realloc": "stdlib.h",
    "free": "stdlib.h", "exit": "stdlib.h", "atoi": "stdlib.h",
    "atof": "stdlib.h", "atol": "stdlib.h", "rand": "stdlib.h",
    "srand": "stdlib.h", "abs": "stdlib.h", "qsort": "stdlib.h",
    # string.h
    "strlen": "string.h", "strcpy": "string.h", "strncpy": "string.h",
    "strcat": "string.h", "strcmp": "string.h", "strncmp": "string.h",
    "strchr": "string.h", "strstr": "string.h", "memset": "string.h",
    "memcpy": "string.h", "memmove": "string.h",
    # math.h
    "sqrt": "math.h", "pow": "math.h", "fabs": "math.h", "ceil": "math.h",
    "floor": "math.h", "log": "math.h", "log2": "math.h", "log10": "math.h",
    "sin": "math.h", "cos": "math.h", "tan": "math.h", "exp": "math.h",
    "round": "math.h", "fmod": "math.h",
    # C++ iostream
    "cout": "iostream", "cin": "iostream", "cerr": "iostream",
    "endl": "iostream",
    # C++ string
    "string": "string",
    # C++ vector
    "vector": "vector",
    # C++ algorithm
    "sort": "algorithm", "find": "algorithm", "max": "algorithm",
    "min": "algorithm", "reverse": "algorithm", "count": "algorithm",
    # C++ map/set
    "map": "map", "set": "set", "unordered_map": "unordered_map",
    "unordered_set": "unordered_set",
    # C++ stack/queue
    "stack": "stack", "queue": "queue", "priority_queue": "queue",
    # ctype.h
    "isdigit": "ctype.h", "isalpha": "ctype.h", "isspace": "ctype.h",
    "toupper": "ctype.h", "tolower": "ctype.h",
    # stdbool.h (C only)
    "bool": "stdbool.h", "true": "stdbool.h", "false": "stdbool.h",
}

# C++ vs C specific headers (we include both and let the compiler sort it)
_CPP_ONLY_HEADERS = {"iostream", "string", "vector", "algorithm", "map", "set",
                     "unordered_map", "unordered_set", "stack", "queue"}


def pass_inject_c_headers(ir: Module, src: str, tgt: str) -> Module:
    """
    Scan all function calls in the IR.
    For every known symbol, inject the corresponding #include header.
    Always inject stdio.h for C (printf is almost always needed).
    """
    needed: Set[str] = set()

    # Always include stdio.h for C/C++ — almost every program needs it
    needed.add("stdio.h")
    if tgt == "C++":
        needed.add("iostream")

    # Collect all called function names
    for node in _all_nodes(ir):
        if isinstance(node, Call):
            if isinstance(node.func, Name):
                hdr = _C_SYMBOL_TO_HEADER.get(node.func.id)
                if hdr:
                    # Skip C++ headers if target is pure C
                    if tgt == "C" and hdr in _CPP_ONLY_HEADERS:
                        continue
                    needed.add(hdr)
            elif isinstance(node.func, Attribute):
                hdr = _C_SYMBOL_TO_HEADER.get(node.func.attr)
                if hdr:
                    if tgt == "C" and hdr in _CPP_ONLY_HEADERS:
                        continue
                    needed.add(hdr)
        elif isinstance(node, Name):
            hdr = _C_SYMBOL_TO_HEADER.get(node.id)
            if hdr:
                if tgt == "C" and hdr in _CPP_ONLY_HEADERS:
                    continue
                needed.add(hdr)

    # Preferred header ordering
    _ORDER = ["stdio.h", "stdlib.h", "string.h", "math.h", "ctype.h",
              "stdbool.h", "iostream", "string", "vector", "algorithm",
              "map", "set", "unordered_map", "unordered_set", "stack", "queue"]

    def _hdr_key(h):
        try:
            return _ORDER.index(h)
        except ValueError:
            return 999

    # REPLACE ir.imports with only valid C headers (discard Python imports like 'numpy')
    ordered_headers = []
    for hdr in sorted(needed, key=_hdr_key):
        ordered_headers.append(Import(module=hdr))
    ir.imports = ordered_headers
    return ir


# ─────────────────────────────────────────────────────────────────────────────
# Pass 10 — NEW: Python types → Java types
# ─────────────────────────────────────────────────────────────────────────────

_PY_TO_JAVA = {
    "int": "int", "float": "double", "str": "String", "bool": "boolean",
    "list": "List", "dict": "Map", "set": "Set", "tuple": "Object[]",
    "None": "void", "bytes": "byte[]", "object": "Object",
    # Already Java types (pass-through)
    "String": "String", "boolean": "boolean", "double": "double",
    "long": "long", "short": "short", "byte": "byte", "char": "char",
    "Integer": "Integer", "Double": "Double", "Boolean": "Boolean",
    "void": "void",
}


def pass_python_types_to_java(ir: Module, src: str, tgt: str) -> Module:
    """Convert Python type annotations to Java types on all params and returns."""
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            for p in node.params:
                # Params: unknown type -> Object
                p.type_annotation = _py_to_java_type(p.type_annotation, default="Object")
            # Return types: unknown/missing -> void (not Object)
            node.return_type = _py_to_java_type(node.return_type, default="void")
            node.is_static = True
            node.access_modifier = "public"
        elif isinstance(node, VarDecl):
            node.type_annotation = _py_to_java_type(node.type_annotation, default="Object")
    return ir


def _py_to_java_type(ann: Optional[str], default: str = "Object") -> Optional[str]:
    if ann is None:
        return default
    base = ann.split("[")[0].strip()
    return _PY_TO_JAVA.get(base, default)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 11 — NEW: PrintStmt → System.out.println for Java
# ─────────────────────────────────────────────────────────────────────────────

def pass_print_to_system_out(ir: Module, src: str, tgt: str) -> Module:
    """PrintStmt(args=[x]) -> System.out.println(x)"""
    _walk_and_fix_bodies(ir, _print_to_sysout_fix)
    return ir


def _print_to_sysout_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if isinstance(stmt, PrintStmt):
            # Build System.out.println(args joined by +)
            if len(stmt.args) == 0:
                args = [Literal(value="", kind="string")]
            elif len(stmt.args) == 1:
                args = [stmt.args[0]]
            else:
                # Join multiple args: arg1 + " " + arg2 + ...
                joined = stmt.args[0]
                for a in stmt.args[1:]:
                    joined = BinaryOp(
                        left=BinaryOp(left=joined, op="+",
                                      right=Literal(value=" ", kind="string")),
                        op="+", right=a
                    )
                args = [joined]
            out.append(ExprStmt(expr=Call(
                func=Attribute(
                    obj=Attribute(obj=Name(id="System"), attr="out"),
                    attr="println"
                ),
                args=args,
            )))
        else:
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 12 — NEW: Inject java.util.* imports based on usage
# ─────────────────────────────────────────────────────────────────────────────

_JAVA_TYPE_TO_IMPORT = {
    "List":          "java.util.List",
    "ArrayList":     "java.util.ArrayList",
    "Map":           "java.util.Map",
    "HashMap":       "java.util.HashMap",
    "Set":           "java.util.Set",
    "HashSet":       "java.util.HashSet",
    "LinkedList":    "java.util.LinkedList",
    "Queue":         "java.util.Queue",
    "Stack":         "java.util.Stack",
    "Collections":   "java.util.Collections",
    "Arrays":        "java.util.Arrays",
    "Optional":      "java.util.Optional",
    "Iterator":      "java.util.Iterator",
    "Scanner":       "java.util.Scanner",
    "Random":        "java.util.Random",
    "Math":          "java.lang.Math",
}


def pass_inject_java_imports(ir: Module, src: str, tgt: str) -> Module:
    """
    Scan the IR for Java type names / function calls.
    Auto-inject the corresponding import statements.
    Always inject java.util.* as a catch-all safety net.
    """
    needed: Set[str] = {"java.util.*"}   # Always inject as safety net

    # Scan for specific types in use
    for node in _all_nodes(ir):
        if isinstance(node, (VarDecl, Param, FunctionDef)):
            ann = getattr(node, "type_annotation", None) or getattr(node, "return_type", None)
            if ann and ann in _JAVA_TYPE_TO_IMPORT:
                needed.add(_JAVA_TYPE_TO_IMPORT[ann])
        if isinstance(node, Name) and node.id in _JAVA_TYPE_TO_IMPORT:
            needed.add(_JAVA_TYPE_TO_IMPORT[node.id])

    # REPLACE ir.imports with only valid Java imports (discard Python imports)
    ir.imports = [Import(module=m) for m in sorted(needed)]
    return ir


# ─────────────────────────────────────────────────────────────────────────────
# Pass 13 — NEW: Wrap everything in public class Main
# ─────────────────────────────────────────────────────────────────────────────

def pass_wrap_in_java_class(ir: Module, src: str, tgt: str) -> Module:
    """
    Wrap all top-level functions and statements inside:
        public class Main {
            ...methods...
            public static void main(String[] args) { ...statements... }
        }

    If there is already a top-level ClassDef, leave it as-is (don't double-wrap).
    If source already has a function named 'main', don't add a second one.
    """
    # Check if already has a top-level class (don't double-wrap)
    has_class = any(isinstance(n, ClassDef) for n in ir.body)
    if has_class:
        return ir

    functions = []
    statements = []

    for node in ir.body:
        if isinstance(node, FunctionDef):
            node.is_static = True
            node.access_modifier = "public"
            functions.append(node)
        else:
            statements.append(node)

    # Don't add main(String[] args) if there's already a function named 'main'
    has_existing_main = any(f.name == "main" for f in functions)
    main_body = statements if statements else []

    if has_existing_main:
        # Append top-level statements into the existing main() body
        for fn in functions:
            if fn.name == "main" and main_body:
                fn.body = fn.body + main_body
                break
        class_body = functions
    else:
        main_method = FunctionDef(
            name="main",
            params=[Param(name="args", type_annotation="String[]")],
            body=main_body,
            return_type="void",
            is_static=True,
            access_modifier="public",
        )
        class_body = functions + ([main_method] if main_body else [])

    if not class_body:
        return ir   # Nothing to wrap

    main_class = ClassDef(
        name="Main",
        bases=[],
        body=class_body,
    )

    ir.body = [main_class]
    return ir


# ─────────────────────────────────────────────────────────────────────────────
# Pass 14 — NEW: Bare assignments → let declarations for JavaScript
# ─────────────────────────────────────────────────────────────────────────────

def pass_vars_to_let(ir: Module, src: str, tgt: str) -> Module:
    """
    Convert first assignment of each variable to a VarDecl with type='let'.
    x = 5  ->  let x = 5
    """
    for node in _all_nodes(ir):
        if isinstance(node, FunctionDef):
            node.body = _vars_to_let_in_body(node.body)
    ir.body = _vars_to_let_in_body(ir.body)
    return ir


def _vars_to_let_in_body(stmts: list) -> list:
    declared: Set[str] = set()
    out = []
    for stmt in stmts:
        if (isinstance(stmt, Assignment)
                and isinstance(stmt.target, Name)
                and stmt.target.id not in declared
                and not stmt.target.id.startswith("__")):
            var = stmt.target.id
            declared.add(var)
            out.append(VarDecl(
                name=var,
                type_annotation="let",   # "let" used as JS keyword marker
                value=stmt.value,
            ))
        else:
            if isinstance(stmt, VarDecl):
                declared.add(stmt.name)
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 15 — NEW: PrintStmt / print() → console.log() for JavaScript
# ─────────────────────────────────────────────────────────────────────────────

def pass_print_to_console_log(ir: Module, src: str, tgt: str) -> Module:
    """PrintStmt(args=[x,y]) -> console.log(x, y)"""
    _walk_and_fix_bodies(ir, _print_to_console_fix)
    return ir


def _print_to_console_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if isinstance(stmt, PrintStmt):
            args = stmt.args if stmt.args else [Literal(value="", kind="string")]
            out.append(ExprStmt(expr=Call(
                func=Attribute(obj=Name(id="console"), attr="log"),
                args=args,
            )))
        else:
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 16 — Clean Java type annotations for Python target
# ─────────────────────────────────────────────────────────────────────────────

_JAVA_TO_PY = {
    "String": "str", "boolean": "bool", "Boolean": "bool",
    "long": "int", "Long": "int", "short": "int", "byte": "int",
    "double": "float", "Double": "float", "float": "float",
    "Integer": "int", "Character": "str", "void": "None", "Object": None,
}


def pass_clean_java_types(ir: Module, src: str, tgt: str) -> Module:
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
# Pass 17 — Strip C standard library headers (for C/C++ → Python)
# ─────────────────────────────────────────────────────────────────────────────

_C_STDLIB_HEADERS = {
    "stdio.h", "stdlib.h", "string.h", "math.h", "ctype.h",
    "assert.h", "errno.h", "float.h", "limits.h", "locale.h",
    "signal.h", "stdarg.h", "stddef.h", "time.h", "stdbool.h",
    "stdint.h", "unistd.h", "fcntl.h", "sys/types.h", "sys/stat.h",
    "iostream", "fstream", "sstream", "vector", "map", "set",
    "string", "algorithm", "cmath", "cstdlib", "cstdio",
    "memory", "utility", "functional", "numeric", "array",
    "list", "deque", "queue", "stack", "tuple",
}


def pass_strip_c_headers(ir: Module, src: str, tgt: str) -> Module:
    """
    Strip ALL C/C++ headers from imports when targeting Python.
    Uses pattern-matching rather than a fixed allowlist so that custom
    project headers (main.h, kvm.h, bits/stdc++.h, etc.) are also removed.
    """
    def _is_c_header(module: str) -> bool:
        m = module.strip()
        return (
            m in _C_STDLIB_HEADERS           # known stdlib headers
            or m.endswith('.h')              # any .h file (main.h, fb.h, kvm.h)
            or m.endswith('.hpp')            # any .hpp file (Human.hpp)
            or '/' in m                      # path-style (sys/types.h, bits/stdc++.h)
            or '+' in m                      # bits/stdc++.h
        )
    ir.imports = [imp for imp in ir.imports if not _is_c_header(imp.module)]
    return ir


# ─────────────────────────────────────────────────────────────────────────────
# Pass 18 — Remove C-style main() wrapper (for C/C++ → Python)
# ─────────────────────────────────────────────────────────────────────────────

def pass_strip_c_main(ir: Module, src: str, tgt: str) -> Module:
    new_body = []
    main_body = []
    for node in ir.body:
        if isinstance(node, FunctionDef) and node.name == "main":
            for stmt in node.body:
                if isinstance(stmt, Return):
                    if isinstance(stmt.value, Literal) and stmt.value.value == 0:
                        continue
                main_body.append(stmt)
        else:
            new_body.append(node)

    if main_body:
        guard = IfStmt(
            condition=CompareOp(
                left=Name(id="__name__"),
                op="==",
                right=Literal(value="__main__", kind="string"),
            ),
            then_body=main_body,
            else_body=[],
        )
        new_body.append(guard)

    ir.body = new_body
    return ir


# ─────────────────────────────────────────────────────────────────────────────
# Pass 19 — NEW: console.log → print for JavaScript → Python
# ─────────────────────────────────────────────────────────────────────────────

def pass_console_to_print(ir: Module, src: str, tgt: str) -> Module:
    """
    console.log(x) -> print(x) for JavaScript → Python translations.
    Also handles System.out.println(x) -> print(x) for Java → Python.
    """
    _walk_and_fix_bodies(ir, _console_to_print_fix)
    return ir


def _console_to_print_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, Call):
            call = stmt.expr
            # console.log(...)
            if (isinstance(call.func, Attribute)
                    and isinstance(call.func.obj, Name)
                    and call.func.obj.id == "console"
                    and call.func.attr == "log"):
                out.append(PrintStmt(args=call.args))
                continue
            # System.out.println(...)
            if (isinstance(call.func, Attribute)
                    and isinstance(call.func.obj, Attribute)
                    and isinstance(call.func.obj.obj, Name)
                    and call.func.obj.obj.id == "System"
                    and call.func.obj.attr == "out"
                    and call.func.attr in ("println", "print")):
                out.append(PrintStmt(args=call.args))
                continue
        out.append(stmt)
    return out


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


# ─────────────────────────────────────────────────────────────────────────────
# Pass 20 — NEW: Strip Python docstrings → C/C++/Java comments
# ─────────────────────────────────────────────────────────────────────────────

from ir.nodes import Comment   # noqa: E402  (already imported at top via *)

def pass_strip_docstrings(ir: Module, src: str, tgt: str) -> Module:
    """
    ExprStmt(Literal(kind="string")) at the top of function/class bodies
    is a Python docstring. In C/C++/Java it becomes a syntax error.
    Convert them to Comment nodes so the generator emits // ...
    """
    _walk_and_fix_bodies(ir, _docstring_fix)
    return ir


def _docstring_fix(stmts: list) -> list:
    out = []
    for stmt in stmts:
        if (isinstance(stmt, ExprStmt)
                and isinstance(stmt.expr, Literal)
                and stmt.expr.kind == "string"):
            # Convert to a comment instead of a dangling string literal
            text = str(stmt.expr.value).replace("\n", " ").strip()
            out.append(Comment(text=text))
        else:
            out.append(stmt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pass 21 — NEW: Rename Python variable names that are C/C++ reserved keywords
# ─────────────────────────────────────────────────────────────────────────────

# C and C++ reserved keywords that cannot be used as variable names
_C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default",
    "do", "double", "else", "enum", "extern", "float", "for", "goto",
    "if", "inline", "int", "long", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "struct", "switch", "typedef",
    "union", "unsigned", "void", "volatile", "while",
    # C++ extras
    "class", "new", "delete", "this", "template", "namespace", "using",
    "virtual", "override", "public", "private", "protected", "friend",
    "operator", "explicit", "true", "false", "nullptr", "bool",
    "try", "catch", "throw", "noexcept", "const_cast", "dynamic_cast",
    "reinterpret_cast", "static_cast", "typeid", "typename",
}

_RENAMED: dict = {}   # module-level cache reset per pass call


def pass_rename_c_keywords(ir: Module, src: str, tgt: str) -> Module:
    """
    Rename any variable/param/function name that collides with a C/C++ keyword.
    e.g. Python variable `char` → `char_var`, `int` → `int_var`
    """
    _RENAMED.clear()
    _rename_keywords_in_node(ir)
    return ir


def _safe_name(name: str) -> str:
    if name in _C_KEYWORDS:
        safe = f"{name}_var"
        _RENAMED[name] = safe
        return safe
    return name


def _rename_keywords_in_node(node: CanonicalNode):
    if node is None:
        return
    # Rename Name references
    if isinstance(node, Name):
        node.id = _safe_name(node.id)
    # Rename VarDecl names
    elif isinstance(node, VarDecl):
        node.name = _safe_name(node.name)
    # Rename Param names
    elif isinstance(node, Param):
        node.name = _safe_name(node.name)
    # Rename FunctionDef names (but NOT __init__, main, etc.)
    elif isinstance(node, FunctionDef):
        if node.name not in ("main", "__init__", "constructor"):
            node.name = _safe_name(node.name)
    # Recurse into all children
    for v in node.__dict__.values():
        if isinstance(v, CanonicalNode):
            _rename_keywords_in_node(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, CanonicalNode):
                    _rename_keywords_in_node(item)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 22 — NEW: Strip `self` from C++ method params, __init__ → constructor
# ─────────────────────────────────────────────────────────────────────────────

def pass_strip_self_from_methods(ir: Module, src: str, tgt: str) -> Module:
    """
    For C++ target:
    1. Remove `self` as first parameter from all methods inside ClassDef.
    2. Rename `__init__` → the class name (C++ constructor).
    3. Convert `self.attr` → `attr` (member access without explicit self).
    """
    for node in _all_nodes(ir):
        if isinstance(node, ClassDef):
            class_name = node.name
            for item in node.body:
                if isinstance(item, FunctionDef):
                    # Strip self from params
                    if item.params and item.params[0].name == "self":
                        item.params = item.params[1:]
                    # Rename __init__ to constructor (class name)
                    if item.name == "__init__":
                        item.name = class_name
                        item.return_type = None  # constructors have no return type
                    # Strip self. prefixes in attribute access inside body
                    _strip_self_refs(item)
    return ir


def _strip_self_refs(node: CanonicalNode):
    """
    Replace every Name(id='self') → Name(id='_this_cpp_ref') recursively.
    The C++ generator converts _this_cpp_ref.attr → this->attr via expr_Attribute.
    Works by mutating Name nodes in place (dataclass fields are mutable).
    """
    if node is None:
        return
    # If this node IS a Name with id 'self', rename it
    if isinstance(node, Name) and node.id == "self":
        node.id = "_this_cpp_ref"
        return
    for fname, fval in list(node.__dict__.items()):
        if isinstance(fval, CanonicalNode):
            _strip_self_refs(fval)
        elif isinstance(fval, list):
            for item in fval:
                if isinstance(item, CanonicalNode):
                    _strip_self_refs(item)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 23 — NEW: arr_append(x, val) → x.push_back(val) for C++
# ─────────────────────────────────────────────────────────────────────────────

_ARR_SHIM_MAP = {
    "arr_append":  "push_back",
    "arr_extend":  "insert",
    "arr_pop":     "pop_back",
    "arr_sort":    "sort",
    "arr_reverse": "reverse",
    "arr_index":   "find",
    "arr_count":   "count",
}


def pass_arr_append_to_push_back(ir: Module, src: str, tgt: str) -> Module:
    """
    Convert arr_append(container, val) → container.push_back(val).
    Also handles other arr_* shim functions we generate.
    """
    for node in _all_nodes(ir):
        if isinstance(node, ExprStmt) and isinstance(node.expr, Call):
            call = node.expr
            if isinstance(call.func, Name) and call.func.id in _ARR_SHIM_MAP:
                method = _ARR_SHIM_MAP[call.func.id]
                if call.args:
                    container = call.args[0]
                    rest_args = call.args[1:]
                    call.func = Attribute(obj=container, attr=method)
                    call.args = rest_args
    return ir
