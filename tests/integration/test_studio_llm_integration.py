#!/usr/bin/env python3
"""测试 Studio LLM 集成

验证 Studio 启动时能否正常启动 sageLLM CPU backend。
"""
import os
import sys
from pathlib import Path

import pytest

# Add Studio to path
studio_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(studio_root / "src"))


@pytest.mark.integration
@pytest.mark.slow
def test_engine_script_generation():
    """测试 sageLLM CPU 引擎脚本生成"""
    from sage.studio.studio_manager import StudioManager
    
    manager = StudioManager()
    
    # 获取测试配置
    model = os.getenv("SAGE_STUDIO_TEST_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    
    # 生成启动脚本
    script_path = manager._create_sagellm_cpu_engine_script(
        model=model,
        port=9001,
        log_file=Path("/tmp/test-engine.log")
    )
    
    # 验证脚本已生成
    assert script_path.exists(), "Engine script should exist"
    assert script_path.stat().st_size > 0, "Engine script should not be empty"
    
    # 验证脚本内容
    with open(script_path) as f:
        content = f.read()
    
    assert "LLMEngine" in content, "Script should import LLMEngine"
    assert "LLMEngineConfig" in content, "Script should import LLMEngineConfig"
    assert "backend_type=\"cpu\"" in content or "backend_type='cpu'" in content, \
        "Script should use CPU backend"
    assert "FastAPI" in content, "Script should use FastAPI"
    assert "/v1/chat/completions" in content, "Script should have chat endpoint"


@pytest.mark.integration
def test_engine_script_content_quality():
    """测试引擎脚本内容质量"""
    from sage.studio.studio_manager import StudioManager
    
    manager = StudioManager()
    model = os.getenv("SAGE_STUDIO_TEST_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    
    script_path = manager._create_sagellm_cpu_engine_script(
        model=model,
        port=9001,
        log_file=Path("/tmp/test-engine.log")
    )
    
    with open(script_path) as f:
        content = f.read()
    
    # 检查关键组件
    required_components = [
        "import asyncio",
        "from sagellm_protocol.types import Request",
        "from sagellm_core import LLMEngine",
        "async def",
        "uvicorn.run",
    ]
    
    for component in required_components:
        assert component in content, f"Script should contain: {component}"


@pytest.mark.integration
def test_default_model_configuration():
    """测试默认模型配置"""
    default_model = os.getenv("SAGE_DEFAULT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    
    # 验证模型名称格式
    assert "/" in default_model, "Model name should be in 'org/model' format"
    assert len(default_model) > 5, "Model name should not be empty"
    
    # 在测试环境中应该使用较小的模型
    if os.getenv("CI"):
        assert "1.5B" in default_model or "0.5B" in default_model, \
            "CI should use small models (1.5B or 0.5B)"


@pytest.mark.integration
def test_gateway_detection():
    """测试 Gateway 运行检测"""
    from sage.studio.studio_manager import StudioManager
    
    manager = StudioManager()
    
    # is_gateway_running 应该返回 PID 或 None
    result = manager.is_gateway_running()
    assert result is None or isinstance(result, int), \
        "is_gateway_running should return None or PID (int)"


def main():
    """主入口（用于手动运行）"""
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    console.print(Panel.fit(
        "[bold cyan]SAGE Studio LLM 集成测试[/bold cyan]\n"
        "测试 sageLLM CPU Backend 启动",
        border_style="cyan"
    ))
    
    # 运行 pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "-m", "integration"
    ])
    
    if exit_code == 0:
        console.print("\n[bold green]🎉 所有测试通过！[/bold green]")
        console.print("\n[bold cyan]下一步:[/bold cyan]")
        console.print("1. 启动 Studio: sage studio start")
        console.print("2. 查看引擎日志: tail -f /tmp/sage-studio-engine.log")
        console.print("3. 测试对话: 打开 Studio Chat 界面")
    else:
        console.print("\n[bold red]❌ 测试失败[/bold red]")
    
    return exit_code


if __name__ == "__main__":
    exit(main())
