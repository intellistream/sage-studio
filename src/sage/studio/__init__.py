"""
SAGE Studio - Web 界面管理工具

Layer: L6 (Interface - Web UI)
Dependencies: All layers (L1-L5)

提供 SAGE Studio 的 Web 界面管理功能。

主要组件:
- StudioManager: 主管理器
- models: 数据模型
- services: 服务层
- adapters: Pipeline 适配器（需要时手动导入）

Architecture:
- L6 界面层，提供可视化管理界面
- 依赖所有下层组件
- 用于可视化配置、监控和管理 SAGE 系统
"""

__layer__ = "L6"

from ._version import __version__


def __getattr__(name: str):
    """懒加载重型模块，避免 import 时触发 torch 等大型依赖。"""
    if name == "models":
        from . import models

        return models
    if name == "services":
        from . import services

        return services
    if name == "StudioManager":
        from .studio_manager import StudioManager

        return StudioManager
    raise AttributeError(f"module 'sage.studio' has no attribute {name!r}")


__all__ = [
    "__version__",
    "StudioManager",
    "models",
    "services",
]
