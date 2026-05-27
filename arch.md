                    ┌─────────────────────┐
                    │                     │
   Python ──────────►                     ├──────────► Java
                    │                     │
   Java   ──────────►   CANONICAL  IR     ├──────────► JavaScript
                    │  (Language-neutral  │
   JavaScript ──────►    AST tree)        ├──────────► Python
                    │                     │
                    │                     ├──────────► C
                    │                     │
                    └─────────────────────┴──────────► C++

        N Parsers + Lifters          M Code Generators


┌─────────────────────────────────────────────────────────┐
│                  SOURCE CODE (raw text)                  │
└──────────────────────────┬──────────────────────────────┘
                           │
                    Stage 1: PREPROCESS
                    (clean Unicode, remove BOMs,
                     normalize whitespace)
                           │
                    Stage 2: PARSE
                    (source text → Syntax Tree)
                           │
                    Stage 3: LIFT
                    (Syntax Tree → Canonical IR)
                           │
                    Stage 4: TRANSFORM
                    (IR → IR, with target-specific adjustments)
                           │
                    Stage 5: GENERATE
                    (IR → target language text)
                           │
┌──────────────────────────▼──────────────────────────────┐
│               TRANSPILED CODE (target text)              │
└─────────────────────────────────────────────────────────┘