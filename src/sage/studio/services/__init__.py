"""
Studio Services - Business Logic Layer

提供 Studio 所需的服务，但不包含执行引擎。
所有 Pipeline 执行都委托给 SAGE Engine。
"""

from .auth_service import (
    AuthService,
    Token,
    TokenData,
    User,
    UserCreate,
    UserInDB,
    get_auth_service,
)
from .file_upload_service import FileUploadService, get_file_upload_service
from .node_manifest import NODE_PLUGIN_MANIFEST
from .node_registry import NodeRegistry
from .pipeline_builder import PipelineBuilder, get_pipeline_builder
from .playground_executor import PlaygroundExecutor
from .workflow_generator import (
    WorkflowGenerationRequest,
    WorkflowGenerationResult,
    WorkflowGenerator,
    generate_workflow_from_chat,
)

__all__ = [
    # Auth
    "AuthService",
    "Token",
    "TokenData",
    "User",
    "UserCreate",
    "UserInDB",
    "get_auth_service",
    # File Upload
    "FileUploadService",
    "get_file_upload_service",
    # Node manifest
    "NODE_PLUGIN_MANIFEST",
    # Node & Pipeline
    "NodeRegistry",
    "PipelineBuilder",
    "get_pipeline_builder",
    # Playground
    "PlaygroundExecutor",
    # Workflow Generation
    "WorkflowGenerator",
    "WorkflowGenerationRequest",
    "WorkflowGenerationResult",
    "generate_workflow_from_chat",
]
