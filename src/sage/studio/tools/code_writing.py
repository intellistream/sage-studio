"""
Code Writing Tools - 代码生成与文件系统工具

Layer: L6 (sage-studio)

提供编码 Agent 所需的文件系统操作工具:
- FileWriteTool:     写入文件到工作区
- FileReadTool:      读取工作区文件内容
- ListDirectoryTool: 列出工作区目录结构
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from sage.studio.tools.base import BaseTool

logger = logging.getLogger(__name__)

# 为编码 Agent 提供一个沙箱根目录（可通过环境变量覆盖）
_DEFAULT_WORKSPACE_ROOT = Path(
    os.environ.get("SAGE_STUDIO_CODE_WORKSPACE", Path.home() / "sage_studio_projects")
)


def _resolve_safe_path(workspace_root: Path, relative_path: str) -> Path:
    """将相对路径解析为安全的绝对路径，防止路径穿越攻击。"""
    target = (workspace_root / relative_path).resolve()
    workspace_resolved = workspace_root.resolve()
    if not str(target).startswith(str(workspace_resolved)):
        raise ValueError(f"路径穿越攻击检测: '{relative_path}' 超出工作区 '{workspace_root}'")
    return target


# ---------------------------------------------------------------------------
# FileWriteTool
# ---------------------------------------------------------------------------


class FileWriteInput(BaseModel):
    path: str = Field(
        ...,
        description="相对于项目工作区的文件路径，例如 'my-app/backend/main.py'",
    )
    content: str = Field(..., description="要写入文件的完整内容")
    project: str = Field(
        default="default",
        description="项目名称（工作区子目录），例如 'ticket-booking-app'",
    )


class FileWriteTool(BaseTool):
    """将代码写入工作区文件。

    Agent 调用此工具完成文件创建或覆盖。父目录会自动创建。
    所有写操作被约束在 ``{SAGE_STUDIO_CODE_WORKSPACE}/{project}/`` 下。
    """

    name: ClassVar[str] = "file_write"
    description: ClassVar[str] = (
        "将指定内容写入工作区内的文件（自动创建父目录）。"
        "用于生成源代码、配置文件、README 等任何文本文件。"
    )
    args_schema: ClassVar[type[BaseModel]] = FileWriteInput

    def __init__(self, workspace_root: Path | None = None):
        self._workspace_root = workspace_root or _DEFAULT_WORKSPACE_ROOT

    async def _run(self, path: str, content: str, project: str = "default") -> dict[str, Any]:
        project_root = self._workspace_root / project
        try:
            target = _resolve_safe_path(project_root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("file_write: wrote %s bytes to %s", len(content), target)
            return {
                "status": "success",
                "path": str(target.relative_to(self._workspace_root)),
                "bytes_written": len(content.encode("utf-8")),
            }
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        except OSError as exc:
            logger.error("file_write OSError for %s: %s", path, exc)
            return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# FileReadTool
# ---------------------------------------------------------------------------


class FileReadInput(BaseModel):
    path: str = Field(
        ...,
        description="要读取的文件的相对路径，例如 'ticket-booking-app/backend/main.py'",
    )
    project: str = Field(default="default", description="项目名称（工作区子目录）")


class FileReadTool(BaseTool):
    """读取工作区内文件的内容。"""

    name: ClassVar[str] = "file_read"
    description: ClassVar[str] = "读取工作区内指定文件的文本内容。用于检查已生成的代码。"
    args_schema: ClassVar[type[BaseModel]] = FileReadInput

    def __init__(self, workspace_root: Path | None = None):
        self._workspace_root = workspace_root or _DEFAULT_WORKSPACE_ROOT

    async def _run(self, path: str, project: str = "default") -> dict[str, Any]:
        project_root = self._workspace_root / project
        try:
            target = _resolve_safe_path(project_root, path)
            if not target.exists():
                return {"status": "error", "error": f"文件不存在: {path}"}
            content = target.read_text(encoding="utf-8")
            return {"status": "success", "path": path, "content": content}
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        except OSError as exc:
            return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# ListDirectoryTool
# ---------------------------------------------------------------------------


class ListDirectoryInput(BaseModel):
    path: str = Field(
        default=".",
        description="要列举的相对目录路径，默认为项目根目录 '.'",
    )
    project: str = Field(default="default", description="项目名称（工作区子目录）")
    max_depth: int = Field(default=3, description="最大递归深度，默认 3", ge=1, le=6)


class ListDirectoryTool(BaseTool):
    """列出工作区目录的树形结构。"""

    name: ClassVar[str] = "list_directory"
    description: ClassVar[str] = (
        "列出工作区中指定目录的文件和子目录树形结构。用于了解项目当前文件布局。"
    )
    args_schema: ClassVar[type[BaseModel]] = ListDirectoryInput

    def __init__(self, workspace_root: Path | None = None):
        self._workspace_root = workspace_root or _DEFAULT_WORKSPACE_ROOT

    async def _run(
        self, path: str = ".", project: str = "default", max_depth: int = 3
    ) -> dict[str, Any]:
        project_root = self._workspace_root / project
        try:
            target = _resolve_safe_path(project_root, path)
            if not target.exists():
                return {"status": "error", "error": f"目录不存在: {path}"}
            tree_lines = _build_tree(target, max_depth=max_depth)
            return {
                "status": "success",
                "path": path,
                "tree": "\n".join(tree_lines),
                "file_count": sum(1 for _ in target.rglob("*") if _.is_file()),
            }
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        except OSError as exc:
            return {"status": "error", "error": str(exc)}


def _build_tree(root: Path, max_depth: int, _depth: int = 0, _prefix: str = "") -> list[str]:
    lines: list[str] = []
    if _depth == 0:
        lines.append(root.name + "/")
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return lines
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{_prefix}{connector}{entry.name}{suffix}")
        if entry.is_dir() and _depth < max_depth - 1:
            extension = "    " if is_last else "│   "
            lines.extend(
                _build_tree(entry, max_depth, _depth=_depth + 1, _prefix=_prefix + extension)
            )
    return lines
