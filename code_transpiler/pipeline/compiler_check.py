"""
pipeline/compiler_check.py
===========================
Reusable compilation checker for all 5 supported languages.

Used in two places:
  1. source_audit.py  — audit raw source code before transpilation
  2. batch_runner.py  — verify source + target code during the pipeline run

Toggle:
    Set ENABLE_COMPILATION_CHECK = True/False in batch_runner.py
    to turn compilation checking ON or OFF without touching this file.

Supported languages:
    Python      → ast.parse()           (no subprocess, instant)
    Java        → javac                 (requires JDK)
    JavaScript  → node --check          (requires Node.js)
    C           → gcc -fsyntax-only     (requires gcc)
    C++         → g++ -fsyntax-only     (requires g++)
"""

from __future__ import annotations
import ast
import os
import subprocess
import tempfile


# ── Per-language compile checkers ─────────────────────────────────────────────

def check_python(code: str) -> tuple[bool, str]:
    """Check Python syntax using the built-in ast parser. No subprocess needed."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def check_javascript(code: str) -> tuple[bool, str]:
    """Check JavaScript syntax using node --check."""
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        r = subprocess.run(["node", "--check", tmp],
                           capture_output=True, timeout=5, text=True)
        if r.returncode == 0:
            return True, ""
        err = next((l for l in r.stderr.splitlines() if l.strip()), r.stderr[:200])
        return False, err
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, "node not found — install Node.js"
    except Exception as e:
        return False, str(e)
    finally:
        try: os.unlink(tmp)
        except: pass


def check_java(code: str) -> tuple[bool, str]:
    """Check Java syntax using javac."""
    import re
    m = re.search(r'(?:public\s+)?class\s+(\w+)', code)
    class_name = m.group(1) if m else "TranspiledCode"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, f"{class_name}.java")
        open(p, "w", encoding="utf-8").write(code)
        try:
            r = subprocess.run(["javac", p],
                               capture_output=True, timeout=15, text=True)
            if r.returncode == 0:
                return True, ""
            err = next((l for l in r.stderr.splitlines()
                        if "error:" in l), r.stderr[:200])
            return False, err
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except FileNotFoundError:
            return False, "javac not found — install JDK"
        except Exception as e:
            return False, str(e)


def check_c(code: str) -> tuple[bool, str]:
    """Check C syntax using gcc -fsyntax-only."""
    return _gcc_check(code, "gcc", ".c")


def check_cpp(code: str) -> tuple[bool, str]:
    """Check C++ syntax using g++ -fsyntax-only."""
    return _gcc_check(code, "g++", ".cpp")


def _gcc_check(code: str, compiler: str, ext: str) -> tuple[bool, str]:
    """Shared gcc/g++ syntax-only check."""
    with tempfile.NamedTemporaryFile(suffix=ext, mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        src = f.name
    try:
        r = subprocess.run([compiler, "-fsyntax-only", "-w", src],
                           capture_output=True, timeout=10, text=True)
        if r.returncode == 0:
            return True, ""
        err = next((l for l in r.stderr.splitlines()
                    if "error:" in l), r.stderr[:200])
        return False, err
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, f"{compiler} not found — install GCC"
    except Exception as e:
        return False, str(e)
    finally:
        try: os.unlink(src)
        except: pass


# ── Registry ──────────────────────────────────────────────────────────────────

CHECKERS: dict[str, callable] = {
    "Python":     check_python,
    "Java":       check_java,
    "JavaScript": check_javascript,
    "C":          check_c,
    "C++":        check_cpp,
}


def check_compiles(code: str, lang: str) -> tuple[bool, str]:
    """
    Main entry point. Returns (success: bool, error_msg: str).

    Args:
        code: Source code string to check.
        lang: Language name — must be one of: Python, Java, JavaScript, C, C++

    Returns:
        (True, "")           — if code compiles/parses successfully
        (False, "error msg") — if compilation fails
        (False, "unsupported language") — if lang is not in CHECKERS
    """
    checker = CHECKERS.get(lang)
    if checker is None:
        return False, f"unsupported language: {lang}"
    return checker(code)
