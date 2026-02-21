from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sage.common.config.user_paths import get_user_data_dir as get_common_user_data_dir
from sage.studio.services.file_upload_service import get_file_upload_service


class CanvasGraphNodePayload(BaseModel):
    node_id: str
    label: str = ""
    operator_ref: str | None = None
    flow_program_ref: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanvasGraphEdgePayload(BaseModel):
    source_node_id: str
    target_node_id: str
    source_port: str | None = None
    target_port: str | None = None


class CanvasGraphValidatePayload(BaseModel):
    graph_id: str | None = None
    program_id: str | None = None
    version: str = ""
    display_name: str = ""
    nodes: list[CanvasGraphNodePayload] = Field(default_factory=list)
    edges: list[CanvasGraphEdgePayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    io_contract: dict[str, Any] = Field(default_factory=dict)


class CanvasGraphValidationNormalizedResponse(BaseModel):
    graph_id: str
    program_id: str
    version: str
    display_name: str
    node_count: int
    edge_count: int
    compiled_payload: dict[str, Any]


class CanvasGraphValidationResponse(BaseModel):
    ok: bool
    errors: list[str]
    normalized: CanvasGraphValidationNormalizedResponse | None


class CanvasGraphPublishPayload(BaseModel):
    graph_id: str | None = None
    program_id: str | None = None
    version: str = ""
    display_name: str = ""
    nodes: list[CanvasGraphNodePayload] = Field(default_factory=list)
    edges: list[CanvasGraphEdgePayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    io_contract: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CanvasGraphPublishResponse(BaseModel):
    program: dict[str, Any]
    compiled_payload: dict[str, Any]


def build_canvas_router() -> APIRouter:
    router = APIRouter(tags=["canvas"])

    @router.post("/api/canvas/v1/graphs/validate", response_model=CanvasGraphValidationResponse)
    async def validate_canvas_graph_route(req: CanvasGraphValidatePayload) -> CanvasGraphValidationResponse:
        errors: list[str] = []
        if not req.nodes:
            errors.append("nodes must not be empty")
        normalized = None
        if not errors:
            graph_id = (req.graph_id or "").strip() or f"graph-{int(datetime.now().timestamp())}"
            program_id = (req.program_id or "").strip() or graph_id
            compiled_payload = {
                "graph_id": graph_id,
                "program_id": program_id,
                "version": req.version or "1.0.0",
                "display_name": req.display_name or program_id,
                "nodes": [item.model_dump() for item in req.nodes],
                "edges": [item.model_dump() for item in req.edges],
                "metadata": req.metadata,
                "io_contract": req.io_contract,
            }
            normalized = CanvasGraphValidationNormalizedResponse(
                graph_id=graph_id,
                program_id=program_id,
                version=req.version or "1.0.0",
                display_name=req.display_name or program_id,
                node_count=len(req.nodes),
                edge_count=len(req.edges),
                compiled_payload=compiled_payload,
            )

        return CanvasGraphValidationResponse(
            ok=(len(errors) == 0),
            errors=errors,
            normalized=normalized,
        )

    @router.post("/api/canvas/v1/graphs/publish", response_model=CanvasGraphPublishResponse)
    async def publish_canvas_graph_route(req: CanvasGraphPublishPayload) -> CanvasGraphPublishResponse:
        graph_id = (req.graph_id or "").strip() or f"graph-{int(datetime.now().timestamp())}"
        program_id = (req.program_id or "").strip() or graph_id
        version = req.version or "1.0.0"
        display_name = req.display_name or program_id
        compiled_payload = {
            "graph_id": graph_id,
            "program_id": program_id,
            "version": version,
            "display_name": display_name,
            "nodes": [item.model_dump() for item in req.nodes],
            "edges": [item.model_dump() for item in req.edges],
            "metadata": req.metadata,
            "io_contract": req.io_contract,
            "enabled": req.enabled,
        }
        return CanvasGraphPublishResponse(
            program={
                "id": f"program:{program_id}:{version}",
                "program_id": program_id,
                "template_id": "canvas",
                "version": version,
                "display_name": display_name,
                "entrypoint": "canvas.graph",
                "enabled": req.enabled,
                "flow_uri": f"canvas://{graph_id}",
                "metadata": req.metadata,
                "params_schema": {},
                "dataset_requirements": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            compiled_payload=compiled_payload,
        )

    @router.get("/api/operators")
    async def get_operators():
        operators = _read_real_operators()
        return operators

    @router.get("/api/operators/list")
    async def get_operators_list(page: int = 1, size: int = 10, search: str = ""):
        all_operators = _read_real_operators()
        if search:
            keyword = search.lower()
            filtered = [
                item
                for item in all_operators
                if keyword in str(item.get("name", "")).lower()
                or keyword in str(item.get("description", "")).lower()
            ]
        else:
            filtered = all_operators
        total = len(filtered)
        start = max((page - 1) * size, 0)
        end = start + max(size, 1)
        return {
            "items": filtered[start:end],
            "total": total,
        }

    @router.get("/api/flows/{flow_id}/export")
    async def export_flow(flow_id: str):
        flow_data = _load_flow_data(flow_id)
        if flow_data is None:
            raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

        export_data = {
            "version": "1.0.0",
            "exportTime": str(datetime.now(timezone.utc)),
            "flowId": flow_id,
            "flow": flow_data,
        }
        return export_data

    @router.post("/api/flows/import")
    async def import_flow(file: UploadFile = File(...)):
        try:
            content = await file.read()
            import_data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="无效的 JSON 文件") from exc

        flow_data = import_data.get("flow")
        if not isinstance(flow_data, dict):
            raise HTTPException(status_code=400, detail="无效的 Flow 文件格式")

        timestamp = int(datetime.now().timestamp() * 1000)
        new_flow_id = f"pipeline_{timestamp}"
        flow_file = _get_pipelines_dir() / f"{new_flow_id}.json"
        flow_file.write_text(json.dumps(flow_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "flowId": new_flow_id,
            "name": flow_data.get("name", "Imported Flow"),
            "message": "Flow 导入成功",
        }

    @router.post("/api/pipeline/submit")
    async def submit_pipeline(payload: dict[str, Any]):
        pipeline_id = f"pipeline_{int(datetime.now().timestamp() * 1000)}"
        file_path = get_user_pipelines_dir("1") / f"{pipeline_id}.json"
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": "success",
            "message": "Pipeline submitted",
            "pipeline_id": pipeline_id,
            "file_path": str(file_path),
        }

    @router.post("/api/uploads")
    async def upload_file(file: UploadFile = File(...)):
        service = get_file_upload_service()
        metadata = await service.upload_file(file.file, file.filename)
        return metadata

    @router.get("/api/uploads")
    async def list_uploaded_files():
        service = get_file_upload_service()
        return service.list_files()

    @router.delete("/api/uploads/{file_id}")
    async def delete_uploaded_file(file_id: str):
        service = get_file_upload_service()
        success = service.delete_file(file_id)
        if not success:
            raise HTTPException(status_code=404, detail="File not found")
        return {"success": True}

    return router


def _data_root() -> Path:
    base_dir = get_common_user_data_dir()
    studio_dir = base_dir / "studio"
    studio_dir.mkdir(parents=True, exist_ok=True)
    return studio_dir


def _get_sage_dir() -> Path:
    return _data_root()


def get_user_pipelines_dir(user_id: str) -> Path:
    pipelines_dir = _get_sage_dir() / "users" / str(user_id) / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    return pipelines_dir


def _get_pipelines_dir() -> Path:
    pipelines_dir = _data_root() / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    return pipelines_dir


def _load_flow_data(flow_id: str) -> dict[str, Any] | None:
    flow_file = _get_pipelines_dir() / f"{flow_id}.json"
    if not flow_file.exists():
        return None
    try:
        return json.loads(flow_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _operators_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "operators"


def _read_real_operators() -> list[dict[str, Any]]:
    operators: list[dict[str, Any]] = []
    operators_dir = _operators_dir()
    if not operators_dir.exists():
        return operators

    for json_file in sorted(operators_dir.glob("*.json")):
        try:
            operator_data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        required_fields = ["id", "name", "description", "isCustom"]
        if not all(key in operator_data for key in required_fields):
            continue

        operators.append(
            {
                "id": operator_data["id"],
                "name": operator_data["name"],
                "description": operator_data["description"],
                "code": operator_data.get("code", ""),
                "isCustom": operator_data["isCustom"],
                "parameters": operator_data.get("parameters", []),
            }
        )

    return operators


__all__ = ["build_canvas_router"]
