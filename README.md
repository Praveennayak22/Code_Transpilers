# Code Transpiler Pipeline

> Automated, scalable cross-language code translation using intermediate representation (IR) and LLM-powered repair mechanisms.

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

## 🎯 Overview

A **production-grade many-to-many code transpiler** that automatically converts source code between 5 major programming languages: **Python, Java, JavaScript, C, and C++**.

This project solves the N² transpilation problem by using a **hub-and-spoke architecture** with a canonical intermediate representation (IR), reducing complexity from O(N²) to O(N+M).

**Perfect for:**
- Building cross-language training datasets for LLMs
- Automated code migration and refactoring at scale
- Creating multilingual test suites
- Research in cross-language code understanding

---

## ✨ Key Features

### 🏗️ Hub-and-Spoke Architecture
- **Single canonical IR** replaces N×M separate transpilers
- **5 language parsers/lifters** (Python, Java, JavaScript, C, C++)
- **5 code generators** producing target language code
- Extensible design for adding new languages

### 🤖 LLM-Powered Repair (Stage 6)
- Automatic detection of compilation errors post-generation
- DeepSeek-v3 integration for intelligent error fixing
- Multi-attempt retry strategy (configurable)
- Cost and token tracking per repair

### ⚡ Production-Ready
- **Batch processing** at scale (tested on 12,956+ files)
- **SLURM HPC cluster support** for distributed execution
- **Comprehensive caching** to avoid redundant work
- **Language detection** and validation

### 📊 Advanced Error Handling
- Pre-generation parsing fixes (Python 2→3, indentation normalization, unclosed strings)
- Numeric suffix handling (Java: `1L`, `0x123L`)
- Hex/Octal/Binary detection (JavaScript)
- Compilation validation for all target languages

---

## 🏛️ Architecture

### The Problem: N² Complexity
Translating between N languages naively requires **N × (N-1)** separate transpilers:

```
5 languages → 20 transpilers ❌
10 languages → 90 transpilers ❌
```

### Our Solution: IR-Based Hub-and-Spoke
```
Source Code (Python, Java, JavaScript, C, C++)
         ↓ Parse & Lift (5 components)
    ┌─────────────────────┐
    │  Canonical IR       │
    │  (Language-neutral  │
    │   AST structure)    │
    └─────────────────────┘
         ↓ Generate (5 components)
Target Code (Python, Java, JavaScript, C, C++)
```

**Result:** 5 + 5 = **10 components** (not 20 separate systems)

---

## 📦 Project Structure

```
code_transpiler/
├── parsing/                 # Language parsers (TreeSitter-based)
│   ├── python_parser.py
│   ├── treesitter_parser.py
│   └── ...
├── lifting/                 # Concrete syntax → Canonical IR
│   ├── base_lifter.py
│   ├── python_lifter.py
│   ├── java_lifter.py
│   └── ...
├── ir/                      # Canonical intermediate representation
│   ├── nodes.py             # IR node definitions
│   └── visitor.py
├── codegen/                 # IR → Target language code
│   ├── base_generator.py
│   ├── python_generator.py
│   ├── java_generator.py
│   └── ...
├── pipeline/                # Orchestration & execution
│   ├── runner.py
│   ├── batch_runner.py
│   ├── cache.py
│   └── registry.py
├── transforms/              # Post-generation transformations
│   └── engine.py
├── llm_client.py           # DeepSeek integration
├── repair_engine.py        # Error repair loop
├── compiler_check.py       # Multi-language compilation validation
└── main.py                 # CLI entry point
```

---

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/your-org/code-transpiler.git
cd code_transpiler
pip install -r requirements.txt
```

### Basic Usage

```bash
# Transpile a single file
python main.py input.py --target java

# Batch transpile with LLM repair enabled
python main.py --input-dir ./sources --output-dir ./output --use-llm-repair

# Enable DeepSeek repair with custom endpoint
python main.py --use-llm-repair --llm-endpoint http://localhost:8000
```

### Available Options

```
--input-dir DIR              Directory of source files to transpile
--output-dir DIR             Output directory for generated code
--target LANG                Target language (python, java, javascript, c, cpp)
--source-lang LANG           Override source language detection
--use-llm-repair            Enable LLM repair loop for compilation errors
--repair-max-attempts INT    Max repair retry attempts (default: 3)
--llm-endpoint URL           DeepSeek API endpoint
--batch-size INT             Files to process per batch
--num-workers INT            Parallel workers for batch processing
```

---

## 📊 Performance Metrics

### Test Results (500-file sample)
| Metric | Before LLM Repair | After LLM Repair | Improvement |
|--------|------------------|------------------|-------------|
| **Successful Compilations** | ~20% | ~50%+ | **150%+** |
| **Python** | 85% | 92% | +7% |
| **Java** | 15% | 45% | +30% |
| **JavaScript** | 25% | 55% | +30% |
| **C/C++** | 5% | 35% | +30% |

### Scale Capability
- **Tested on:** 12,956+ JSONL files
- **Processing rate:** ~1-1.25 files/second
- **Batch time:** ~3-4 hours for full dataset
- **Infrastructure:** SLURM HPC cluster with GPU acceleration (optional)

---

## 🔧 Core Components

### 1. **Parsing & Lifting**
Converts source code → Canonical IR using:
- **TreeSitter** for robust parsing
- Language-specific lifters for semantic extraction
- Automatic error recovery (Python 2→3, indentation, strings)

### 2. **Canonical IR**
Language-neutral AST with:
- Function definitions, calls, returns
- Variable declarations, assignments
- Control flow (if/else, loops, exceptions)
- Type information where available
- Extensible node types for language-specific constructs

### 3. **Code Generation**
IR → Target language via:
- Template-based generation
- Language idiom mapping
- Automatic type conversion
- Import/dependency management

### 4. **Compilation Validation**
Verifies generated code:
- Python: `ast.parse()` + execution checks
- Java: `javac` compilation
- JavaScript: `node --check` syntax validation
- C/C++: GCC compilation with warnings

### 5. **LLM Repair Loop**
Error-driven code fixing:
1. Detect compilation errors
2. Send error + source to LLM
3. LLM generates fix suggestions
4. Retry compilation (up to 3 attempts)
5. Track tokens, costs, and success rates

---

## 📚 Documentation

- **[Architecture Details](./architecture_explanation.md)** — Deep dive into IR design and hub-and-spoke pattern
- **[Pipeline Explanation](./pipeline_explanation.md)** — Complete data flow and processing pipeline
- **[Implementation Plan](./implementation_plan.md)** — Development roadmap and phase breakdown
- **[LLM Repair Guide](./code_transpiler/LLM_REPAIR_README.md)** — Configuration and usage of repair mechanisms
- **[Deployment Guide](./code_transpiler/DEPLOYMENT_GUIDE.md)** — Production deployment on SLURM clusters

---

## 💻 System Requirements

**Minimum:**
- Python 3.8+
- 4GB RAM (8GB recommended)
- 10GB disk space

**For Production/Batch Processing:**
- SLURM cluster with compute nodes
- GPU support (optional, improves speed)
- Centralized storage (NFS/parallel filesystem)

**For LLM Repair:**
- Access to DeepSeek API or compatible endpoint
- API key/credentials in environment variables

---

## 📋 Dependencies

Key libraries used:
- **tree-sitter** — Fast, accurate parsing
- **pyarrow** — Efficient data handling
- **pandas** — Data processing and analysis
- **tqdm** — Progress monitoring
- **pytest** — Testing framework

Full requirements: [requirements.txt](./code_transpiler/requirements.txt)

---

## 🧪 Testing

Run the test suite:

```bash
cd code_transpiler
pytest tests/ -v

# Test specific language lifter
pytest tests/test_c_lifter.py -v

# Run pipeline integration tests
pytest tests/test_pipeline.py -v
```

---

## 🔄 Pipeline Stages

The transpiler runs through 6 stages:

1. **Parse** — Read source file, detect language
2. **Lift** — Convert to Canonical IR
3. **Transform** — Apply target-specific transformations
4. **Generate** — Convert IR to target code
5. **Validate** — Check syntax and basic compilation
6. **Repair** (Optional) — Run LLM fix loop if errors detected

---

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-language`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Submit a pull request

### Adding a New Language

To add a new language (e.g., Go, Rust):
1. Implement `GoParser` in `parsing/`
2. Create `GoLifter` in `lifting/`
3. Create `GoGenerator` in `codegen/`
4. Add to pipeline registry
5. Write tests in `tests/`

---

## 📈 Roadmap

- [x] Core transpiler (Python, Java, JavaScript, C, C++)
- [x] LLM repair integration (DeepSeek)
- [x] Production batch processing
- [ ] Go and Rust support
- [ ] WebAssembly generation
- [ ] Advanced optimization passes
- [ ] Interactive IDE plugin

---

## 📝 License

MIT License — see [LICENSE](./LICENSE) file

---

## 📧 Support

For issues, questions, or feedback:
- Open an issue on GitHub
- Check [documentation](./architecture_explanation.md) for troubleshooting
- Review test files for usage examples

---

## 🙏 Acknowledgments

- Built on top of **TreeSitter** for robust parsing
- Inspired by production systems like **LLVM**, **Babel**, and **SQLGlot**
- Powered by **DeepSeek-v3** for intelligent error repair

---

**Made with ❤️ for cross-language code understanding and transformation.**
