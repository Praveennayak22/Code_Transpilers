"""
compiler_check.py
==================
Language-specific compilation checkers.

Tests if code actually compiles for each target language.
"""

from __future__ import annotations
import subprocess
import tempfile
import os
import ast
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class CompileResult:
    """Result of a compilation attempt."""
    success: bool
    error_message: Optional[str] = None
    stderr: Optional[str] = None


class CompilerChecker:
    """Base class for compiler checks."""
    
    def check(self, code: str) -> CompileResult:
        """Check if code compiles. Must be overridden by subclasses."""
        raise NotImplementedError


class PythonChecker(CompilerChecker):
    """Python syntax checker using ast.parse()."""
    
    def check(self, code: str) -> CompileResult:
        """Check Python code for syntax errors."""
        try:
            ast.parse(code)
            return CompileResult(success=True)
        except SyntaxError as e:
            error_msg = f"Line {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f"\n{e.text}"
            return CompileResult(
                success=False,
                error_message=error_msg,
                stderr=str(e)
            )
        except Exception as e:
            return CompileResult(
                success=False,
                error_message=str(e),
                stderr=str(e)
            )


class JavaScriptChecker(CompilerChecker):
    """JavaScript syntax checker using node --check."""
    
    def check(self, code: str) -> CompileResult:
        """Check JavaScript code using Node.js."""
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ["node", "--check", temp_file],
                capture_output=True,
                timeout=5,
                text=True
            )
            
            if result.returncode == 0:
                return CompileResult(success=True)
            else:
                return CompileResult(
                    success=False,
                    error_message=result.stderr[:500],
                    stderr=result.stderr
                )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                error_message="Node.js check timed out",
                stderr="Timeout"
            )
        except FileNotFoundError:
            return CompileResult(
                success=False,
                error_message="node command not found",
                stderr="node not installed"
            )
        except Exception as e:
            return CompileResult(
                success=False,
                error_message=str(e),
                stderr=str(e)
            )
        finally:
            try:
                os.unlink(temp_file)
            except:
                pass


class CChecker(CompilerChecker):
    """C compiler checker using gcc."""
    
    def check(self, code: str) -> CompileResult:
        """Check C code using gcc."""
        return self._compile(code, "gcc", ".c")
    
    def _compile(self, code: str, compiler: str, ext: str) -> CompileResult:
        """Generic compile check."""
        with tempfile.NamedTemporaryFile(suffix=ext, mode="w", delete=False, encoding="utf-8") as f:
            f.write(code)
            source_file = f.name
        
        output_file = source_file.replace(ext, ".o")
        
        try:
            result = subprocess.run(
                [compiler, "-c", "-Wall", "-Wextra", source_file, "-o", output_file],
                capture_output=True,
                timeout=10,
                text=True
            )
            
            if result.returncode == 0:
                return CompileResult(success=True)
            else:
                # Parse error message
                error_msg = self._parse_gcc_error(result.stderr)
                return CompileResult(
                    success=False,
                    error_message=error_msg[:500],
                    stderr=result.stderr
                )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                error_message=f"{compiler} compilation timed out",
                stderr="Timeout"
            )
        except FileNotFoundError:
            return CompileResult(
                success=False,
                error_message=f"{compiler} not found",
                stderr=f"{compiler} not installed"
            )
        except Exception as e:
            return CompileResult(
                success=False,
                error_message=str(e),
                stderr=str(e)
            )
        finally:
            for f in [source_file, output_file]:
                try:
                    os.unlink(f)
                except:
                    pass
    
    @staticmethod
    def _parse_gcc_error(stderr: str) -> str:
        """Extract the first error line from gcc output."""
        lines = stderr.split("\n")
        for line in lines:
            if "error:" in line:
                return line
        return stderr[:500] if stderr else "Compilation failed"


class CppChecker(CChecker):
    """C++ compiler checker using g++."""
    
    def check(self, code: str) -> CompileResult:
        """Check C++ code using g++."""
        return self._compile(code, "g++", ".cpp")


class JavaChecker(CompilerChecker):
    """Java compiler checker using javac."""
    
    def check(self, code: str) -> CompileResult:
        """Check Java code using javac."""
        # Extract class name from code
        class_match = re.search(r'(?:public\s+)?class\s+(\w+)', code)
        class_name = class_match.group(1) if class_match else "TranspiledCode"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / f"{class_name}.java"
            
            try:
                # Write source file
                source_file.write_text(code, encoding="utf-8")
                
                # Compile
                result = subprocess.run(
                    ["javac", str(source_file)],
                    capture_output=True,
                    timeout=10,
                    text=True,
                    cwd=temp_dir
                )
                
                if result.returncode == 0:
                    return CompileResult(success=True)
                else:
                    error_msg = self._parse_javac_error(result.stderr)
                    return CompileResult(
                        success=False,
                        error_message=error_msg[:500],
                        stderr=result.stderr
                    )
            except subprocess.TimeoutExpired:
                return CompileResult(
                    success=False,
                    error_message="javac compilation timed out",
                    stderr="Timeout"
                )
            except FileNotFoundError:
                return CompileResult(
                    success=False,
                    error_message="javac not found",
                    stderr="javac not installed"
                )
            except Exception as e:
                return CompileResult(
                    success=False,
                    error_message=str(e),
                    stderr=str(e)
                )
    
    @staticmethod
    def _parse_javac_error(stderr: str) -> str:
        """Extract the first error line from javac output."""
        lines = stderr.split("\n")
        for line in lines:
            if "error:" in line or "symbol" in line:
                return line
        return stderr[:500] if stderr else "Compilation failed"


def get_checker(target_lang: str) -> CompilerChecker:
    """Get the appropriate checker for a target language."""
    checkers = {
        "Python": PythonChecker,
        "JavaScript": JavaScriptChecker,
        "Java": JavaChecker,
        "C": CChecker,
        "C++": CppChecker,
    }
    
    checker_class = checkers.get(target_lang)
    if not checker_class:
        raise ValueError(f"No checker for language: {target_lang}")
    
    return checker_class()
