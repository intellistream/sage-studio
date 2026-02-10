# Studio Chat Pipeline Refactor - Agent Task Prompts

## Goal
Refactor Studio chat to run through a SAGE Pipeline (not direct HTTP) and only call sagellm-gateway from within pipeline operators. Preserve existing API contracts and streaming behavior for the frontend.

---

## Agent 1: Architecture Audit + Target Flow Spec
**Scope**: Verify current end-to-end chat flow and propose the target pipeline dataflow.

**Prompt**:
You are working in sage-studio. Read and summarize the current chat flow from frontend to backend, and identify where it bypasses SAGE pipelines. Then propose a target pipeline flow that uses SAGE DataStream operators for intent, retrieval, prompt, and generation. Provide a short diagram and a list of operator candidates from SAGE middleware.

**Key files**:
- sage-studio/src/sage/studio/config/backend/api.py
- sage-studio/src/sage/studio/services/agent_orchestrator.py
- sage-studio/src/sage/studio/frontend/src/services/api.ts
- SAGE/packages/sage-middleware/src/sage/middleware/operators/rag/
- SAGE/packages/sage-middleware/src/sage/middleware/operators/llm/

**Output**:
- A flow diagram (plain text)
- A list of operators and where they live
- A short spec for the pipeline input/output schema

---

## Agent 2: Pipeline Service Prototype (Backend)
**Scope**: Build a pipeline-as-service for chat in Studio backend.

**Prompt**:
Implement a Pipeline-as-Service in sage-studio that can accept a user message and return a final response. Use SAGE PipelineService and PipelineBridge to wrap a DataStream pipeline. The pipeline should accept a dict input like {"prompt": "...", "session_id": "..."} and return {"text": "...", "meta": {...}}. Use existing middleware operators when possible. Wire the service into a new backend module (do not change frontend yet).

**Key files**:
- SAGE/packages/sage-kernel/src/sage/kernel/api/service/pipeline_service/
- sage-studio/src/sage/studio/services/pipeline_builder.py
- sage-studio/src/sage/studio/services/

**Constraints**:
- No backward-compat shims
- No try/except fallbacks
- Keep configs in code or config file, but do not hardcode ports; use SagePorts

**Output**:
- New service module
- Simple entry-point method for calling the pipeline

---

## Agent 3: Chat API Integration (Backend)
**Scope**: Replace direct Gateway calls with pipeline service calls while preserving API format.

**Prompt**:
Update /api/chat/v1/chat/completions in api.py to call the new pipeline service. Preserve streaming behavior (SSE chunks in OpenAI-compatible format). The pipeline service should produce tokens or chunks; if streaming is not supported, buffer and stream by chunking in backend. Make sure session handling stays intact.

**Key files**:
- sage-studio/src/sage/studio/config/backend/api.py
- sage-studio/src/sage/studio/services/stream_handler.py

**Constraints**:
- Must preserve existing response schema
- Must not call gateway directly from api.py

**Output**:
- Updated endpoint implementation
- If needed, helper function to convert pipeline output to SSE

---

## Agent 4: Node Registry + UI Node Types
**Scope**: Ensure chat pipeline operators are available in Studio node registry.

**Prompt**:
Extend node_registry.py to register any operators required by the new chat pipeline (promptor, retriever, generator, and any filters or context sources). Use snake_case keys and existing operator classes from sage.middleware. Update conversion rules if needed. Avoid adding compatibility shims.

**Key files**:
- sage-studio/src/sage/studio/services/node_registry.py
- SAGE/packages/sage-middleware/src/sage/middleware/operators/

**Output**:
- Updated node registry mappings
- List of newly exposed node types

---

## Agent 5: Frontend Compatibility Check
**Scope**: Confirm frontend can keep the same API usage or update minimal logic.

**Prompt**:
Check frontend chat code to ensure it still works with the backend changes. Verify /chat/v1/chat/completions SSE parsing. If API stays identical, no changes needed; otherwise, make minimal updates to parsing logic. Provide a short report.

**Key files**:
- sage-studio/src/sage/studio/frontend/src/services/api.ts
- sage-studio/src/sage/studio/frontend/src/components/ChatMode.tsx

**Output**:
- Short report on compatibility
- Patch if needed

---

## Agent 6: Tests + Manual Verification Plan
**Scope**: Validate the new pipeline path.

**Prompt**:
Create a minimal test or manual verification plan for the new pipeline-backed chat. Prefer backend unit tests if feasible; otherwise provide clear manual steps (curl). Ensure tests do not require external network.

**Key files**:
- sage-studio/tests (if any)
- sage-studio/src/sage/studio/config/backend/api.py

**Output**:
- Test plan or test additions
- Expected outputs

---

## Shared Notes
- Chat should go through SAGE pipeline, not direct gateway calls.
- LLM calls are allowed inside pipeline operators only (e.g., OpenAIGenerator or SageLLMGenerator).
- Avoid hardcoding ports; use SagePorts.
- No backward-compat layers, no try/except fallbacks.
