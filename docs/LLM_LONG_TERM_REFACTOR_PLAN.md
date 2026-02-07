# SAGE LLM Long-Term Refactor Plan

> Purpose: Provide a long-term remediation roadmap for the SAGE LLM stack, with actionable prompts for implementation.
> Scope: sagellm-core, sagellm-protocol, sagellm-backend, sagellm-kv-cache, sage-studio integration.

## 1. Goals

- Correctness first: eliminate known functional bugs in custom models and generation flow.
- HF-first baseline: HuggingFace models must be the stable default path.
- Modular optimization: performance wins come from kernels, cache, scheduler, and weight pipeline.
- Single source of truth: unify duplicated model implementations and sampling logic.
- Clean API: protocol and engine inputs should be message-centric, not prompt-centric.

## 2. Non-Negotiable Principles

- No backward-compatibility shims or fallback try/except imports.
- Fix problems at the right layer (protocol/core/backend), not in Studio.
- Do not add new model reimplementations without kernel-level gains.
- All long-term changes must add tests that reproduce the original bug.

## 3. Key Risks (Current State)

- Dual model stacks in sagellm-core:
  - model/ (legacy) and models/ (new vLLM-style) coexist with different base classes.
  - Two Qwen2 and Llama implementations diverge.
- Custom Qwen2 model has critical correctness bugs in generate() and KV cache path.
- KV cache operations are Python loops; too slow and likely incorrect in edge cases.
- Sampling logic duplicated between SagePretrainedModel.generate() and decoding/ strategies.
- RowParallelLinear lacks all-reduce (TP > 1 is wrong).
- HF model path gets incompatible kwargs (use_kv_cache).

## 4. Roadmap (Phased)

### Phase 0: Stabilize (Correctness Baseline)

- Make HFModelLoader the default path for Qwen2 until custom path is verified.
- Ensure messages -> chat template is handled inside sagellm-core only.
- Remove prompt echo by decoding only new tokens.
- Enforce strict param precedence: user params must always override defaults.

### Phase 1: Unify Model Stack

- Choose a single model stack (models/ vLLM-style or model/ legacy).
- Remove duplicate Qwen2/Llama implementations after migration.
- Update registry and loader selection logic to match the chosen stack.

### Phase 2: KV Cache and Attention Rework

- Replace Python loop KV cache read/write with backend kernels.
- Integrate sagellm-kv-cache into sagellm-core as the authoritative cache.
- Validate prefill/decode metadata alignment (seq_lens, block tables).

### Phase 3: Optimization and Scaling

- Implement TP all-reduce in RowParallelLinear.
- Add fused kernels for QKV + gate/up where beneficial.
- Extend scheduler and batching for throughput gains.

## 5. Task List with Detailed Prompts

Each task includes a ready-to-use prompt for implementation. Use them as-is with a coding agent.

### T1. Fix custom generate() decode context loss

- Repo: sagellm-core
- Files: models/base.py, models/attention.py
- Risk: High (core correctness)
- Validation: add unit test that fails before fix

Prompt:
"""
You are modifying sagellm-core. The custom SagePretrainedModel.generate() loses context during decode when KV cache is disabled, because the decode step only sees the last token. Fix this so decode always receives the full prompt context (or correct cached context) and matches HF outputs for short prompts. Add a regression test that reproduces the bug using Qwen2 (or Llama) with use_kv_cache=False and verifies the output tokens are non-degenerate (not repeated punctuation). Do not add compatibility shims. Prefer minimal, explicit fixes.
"""

### T2. Remove duplicate model stacks (choose one)

- Repo: sagellm-core
- Files: model/* and models/*
- Risk: Medium (refactor)
- Validation: unit tests and HF parity tests

Prompt:
"""
We have two parallel model stacks in sagellm-core: model/ (legacy) and models/ (vLLM-style). Pick one stack to keep and migrate the loader/registry/tests to that stack. Remove the duplicate Qwen2 and Llama implementations and update any references to the old paths. Ensure the loader selection logic is deterministic and uses the unified stack only. Update or remove tests that are tied to the deleted stack. No backward compatibility layers.
"""

### T3. Integrate sagellm-kv-cache into sagellm-core

- Repo: sagellm-core, sagellm-kv-cache
- Files: models/attention.py, attention_metadata.py, kv_cache integration points
- Risk: High (performance and correctness)
- Validation: kv cache unit tests + e2e decode test

Prompt:
"""
Integrate sagellm-kv-cache as the primary KV cache backend in sagellm-core. Replace the Python loop read/write in SageAttention with kv-cache pool APIs. Update AttentionMetadata to use block tables and slot mapping from the kv-cache layer. Ensure prefill writes and decode reads are consistent. Add tests covering prefill+decode sequences and confirm token-level parity with HF for short prompts.
"""

### T4. Remove duplicated sampling logic

- Repo: sagellm-core
- Files: models/base.py, decoding/*, llm_engine.py
- Risk: Medium
- Validation: engine decoding tests

Prompt:
"""
Eliminate duplicated sampling logic between SagePretrainedModel.generate() and decoding strategies. Choose a single source of truth (prefer decoding/ strategies) and route both HF and custom models through it. Make sure temperature=0.0 is respected and never overridden by defaults. Add tests for greedy, top-k, top-p paths.
"""

### T5. Fix RowParallelLinear all-reduce

- Repo: sagellm-core and sagellm-comm
- Files: models/linear.py, comm backends
- Risk: Medium
- Validation: TP unit test

Prompt:
"""
RowParallelLinear currently lacks all-reduce, so TP>1 outputs are incorrect. Implement the required all-reduce using sagellm-comm backends. Add a test that simulates TP=2 with a small linear layer and verifies outputs match a non-sharded reference. Keep the implementation minimal and backend-agnostic.
"""

### T6. Make HF path strict and clean

- Repo: sagellm-core
- Files: llm_engine.py
- Risk: Low
- Validation: existing engine tests

Prompt:
"""
Ensure HF models never receive custom-only kwargs like use_kv_cache. The decision should be based on the actual loader/model type, not config flags. Refactor the generate() path to separate HF vs custom kwargs cleanly. Add a test that runs HFModelLoader and verifies no unexpected kwargs are passed.
"""

### T7. Consolidate chat template handling

- Repo: sagellm-core, sagellm-protocol
- Files: tokenizer_utils.py, llm_engine.py, protocol Request
- Risk: Low
- Validation: protocol tests + engine test

Prompt:
"""
Messages must be the primary input form. Ensure that if Request.messages is provided, it is always converted to prompt via tokenizer.apply_chat_template() inside sagellm-core. Studio must never construct prompts manually. Add tests to ensure the default system message is included for Qwen2 and that missing system messages are handled correctly.
"""

### T8. Clean dead code and debug prints

- Repo: sagellm-core
- Files: models/base.py
- Risk: Low
- Validation: lint/tests

Prompt:
"""
Remove debug print statements and unreachable dead code in models/base.py. Keep the logic intact, do not change behavior. Add a small unit test or lint rule if needed to prevent debug prints from reappearing.
"""

### T9. Weight pipeline completion

- Repo: sagellm-core
- Files: model/weight_utils.py, weights/*
- Risk: Medium
- Validation: weight loading tests

Prompt:
"""
Complete the TODO stubs in model/weight_utils.py for WeightLoader and QuantizedWeightLoader. Use the existing WeightPipeline utilities for mapping, sharding, and fusion. Add tests for both fp16/bf16 and quantized paths. Ensure no silent fallback logic.
"""

### T10. Benchmark-driven optimization plan

- Repo: sagellm-core, sagellm-backend
- Files: benchmark tests, attention kernels
- Risk: Medium
- Validation: benchmark report

Prompt:
"""
Create a performance plan focused on kernel-level optimizations: paged attention, fused QKV, and CUDA graph. Implement one measurable optimization with benchmark coverage. Record before/after metrics (throughput, TTFT). Keep correctness tests unchanged.
"""

## 6. Acceptance Checklist

- HF path passes all engine tests and a minimal e2e chat flow.
- Custom model path matches HF outputs on short prompts (parity test).
- KV cache tests cover prefill+decode and do not use Python loops.
- No duplicate Qwen2/Llama implementations remain.
- TP>1 has a passing correctness test.
- No debug prints or dead code in core model path.

## 7. Suggested Order of Execution

1. T6, T7, T8 (low risk, stabilize behavior)
2. T1 (critical correctness)
3. T3 (KV cache integration)
4. T4 (sampling unification)
5. T2 (model stack unification)
6. T5 (TP correctness)
7. T9, T10 (weight + perf)

## 8. Notes for Studio Integration

- Studio should only pass messages to sagellm-core.
- Studio should not handle chat templates or echo removal.
- Keep HFModelLoader as default for Qwen2 until custom path passes parity tests.

---

End of document.
