#!/usr/bin/env python3
"""诊断 Studio 对话失败问题

检查 Studio Chat 功能的各个组件是否正常工作。
"""
import asyncio
import requests
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


async def diagnose_chat_issue():
    """诊断对话失败问题"""
    console.print(Panel.fit(
        "[bold cyan]Studio Chat 诊断工具[/bold cyan]\n"
        "检查 Gateway, LLM Engine, Backend API 状态",
        border_style="cyan"
    ))
    
    results = Table(title="组件状态", show_header=True, header_style="bold magenta")
    results.add_column("组件", style="cyan", width=20)
    results.add_column("端口", style="white", width=10)
    results.add_column("状态", style="white", width=15)
    results.add_column("详情", style="dim", width=50)
    
    # 1. 检查 Gateway (8889)
    console.print("\n[bold green]检查 1:[/bold green] Gateway (sageLLM Gateway)")
    gateway_url = "http://localhost:8889"
    gateway_status = "❌ 未运行"
    gateway_detail = "无法连接"
    
    try:
        response = requests.get(f"{gateway_url}/health", timeout=2)
        if response.status_code == 200:
            gateway_status = "✅ 运行中"
            gateway_detail = f"响应: {response.json()}"
        else:
            gateway_status = "⚠️  异常"
            gateway_detail = f"HTTP {response.status_code}"
    except requests.ConnectionError:
        pass
    except Exception as e:
        gateway_detail = str(e)[:50]
    
    results.add_row("Gateway", "8889", gateway_status, gateway_detail)
    
    # 2. 检查 LLM Engine (9001)
    console.print("\n[bold green]检查 2:[/bold green] LLM Engine (CPU Backend)")
    engine_url = "http://localhost:9001"
    engine_status = "❌ 未运行"
    engine_detail = "无法连接"
    
    try:
        response = requests.get(f"{engine_url}/health", timeout=2)
        if response.status_code == 200:
            engine_status = "✅ 运行中"
            data = response.json()
            engine_detail = f"模型: {data.get('model', 'N/A')}, Backend: {data.get('backend', 'N/A')}"
        else:
            engine_status = "⚠️  异常"
            engine_detail = f"HTTP {response.status_code}"
    except requests.ConnectionError:
        pass
    except Exception as e:
        engine_detail = str(e)[:50]
    
    results.add_row("LLM Engine", "9001", engine_status, engine_detail)
    
    # 3. 检查 Studio Backend (8080 或 8081)
    console.print("\n[bold green]检查 3:[/bold green] Studio Backend API")
    backend_ports = [8080, 8081, 8082, 8083]
    backend_status = "❌ 未运行"
    backend_port = "N/A"
    backend_detail = "无法连接"
    
    for port in backend_ports:
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=1)
            if response.status_code == 200:
                backend_status = "✅ 运行中"
                backend_port = str(port)
                backend_detail = "Studio API 就绪"
                break
        except:
            continue
    
    results.add_row("Studio Backend", backend_port, backend_status, backend_detail)
    
    # 4. 检查 Gateway Models API
    console.print("\n[bold green]检查 4:[/bold green] Gateway Models API")
    models_status = "❌ 未就绪"
    models_detail = "无法获取模型列表"
    
    try:
        response = requests.get(f"{gateway_url}/v1/models", timeout=2)
        if response.status_code == 200:
            data = response.json()
            models_list = data.get("data", [])
            if models_list:
                models_status = "✅ 可用"
                model_names = [m.get("id", "unknown") for m in models_list]
                models_detail = f"已注册: {', '.join(model_names[:2])}"
            else:
                models_status = "⚠️  无模型"
                models_detail = "Gateway 未注册任何引擎"
    except requests.ConnectionError:
        models_detail = "Gateway 未运行"
    except Exception as e:
        models_detail = str(e)[:50]
    
    results.add_row("Gateway Models", "8889", models_status, models_detail)
    
    # 5. 测试 Chat API
    console.print("\n[bold green]检查 5:[/bold green] Chat Completions API")
    chat_status = "❌ 失败"
    chat_detail = "无法测试"
    
    try:
        test_request = {
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "messages": [
                {"role": "user", "content": "Hello, are you working?"}
            ],
            "max_tokens": 50
        }
        
        # 先测试 Engine 的 chat API
        response = requests.post(
            f"{engine_url}/v1/chat/completions",
            json=test_request,
            timeout=30
        )
        
        if response.status_code == 200:
            chat_status = "✅ 正常"
            data = response.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            chat_detail = f"回复: {reply[:40]}..."
        else:
            chat_status = "⚠️  异常"
            chat_detail = f"HTTP {response.status_code}: {response.text[:50]}"
            
    except requests.ConnectionError:
        chat_detail = "Engine 未运行"
    except requests.Timeout:
        chat_status = "⚠️  超时"
        chat_detail = "推理超时（30秒）"
    except Exception as e:
        chat_detail = str(e)[:50]
    
    results.add_row("Chat API", "9001", chat_status, chat_detail)
    
    # 显示结果
    console.print("\n")
    console.print(results)
    
    # 分析问题
    console.print("\n[bold cyan]📊 诊断结果:[/bold cyan]")
    
    issues = []
    suggestions = []
    
    if "❌" in gateway_status:
        issues.append("Gateway 未运行")
        suggestions.append("启动 Gateway: sagellm-gateway --port 8889")
    
    if "❌" in engine_status:
        issues.append("LLM Engine 未运行")
        suggestions.append("查看引擎日志: tail -f /tmp/sage-studio-engine.log")
        suggestions.append("手动启动引擎: cd /home/shuhao/sagellm-core && python test_qwen_1_5b_cpu.py")
    
    if "❌" in backend_status:
        issues.append("Studio Backend 未运行")
        suggestions.append("启动 Studio: sage studio start")
    
    if "无模型" in models_detail:
        issues.append("Gateway 未注册任何引擎")
        suggestions.append("手动注册引擎到 Gateway:")
        suggestions.append("  curl -X POST http://localhost:8889/v1/management/engines/register \\")
        suggestions.append("    -H 'Content-Type: application/json' \\")
        suggestions.append("    -d '{\"engine_id\":\"studio-cpu\",\"model_id\":\"Qwen/Qwen2.5-1.5B-Instruct\",\"host\":\"localhost\",\"port\":9001,\"engine_kind\":\"llm\"}'")
    
    if "❌" in chat_status or "⚠️" in chat_status:
        issues.append("Chat API 不可用")
        if "未运行" in chat_detail:
            suggestions.append("首先确保 Engine 正常运行")
        elif "超时" in chat_status:
            suggestions.append("CPU 推理较慢，可能需要更长等待时间")
            suggestions.append("或考虑使用 GPU backend（如果有 GPU）")
    
    if not issues:
        console.print("[bold green]✨ 所有组件正常！[/bold green]")
        console.print("\n如果 Studio Chat 仍然失败，可能的原因：")
        console.print("1. 前端配置的 API 地址不正确")
        console.print("2. CORS 问题（检查浏览器控制台）")
        console.print("3. 前端未正确调用 Chat API")
    else:
        console.print("[bold red]发现以下问题：[/bold red]")
        for i, issue in enumerate(issues, 1):
            console.print(f"  {i}. {issue}")
        
        console.print("\n[bold cyan]建议解决方案：[/bold cyan]")
        for i, suggestion in enumerate(suggestions, 1):
            console.print(f"  {i}. {suggestion}")
    
    # 检查日志文件
    console.print("\n[bold cyan]📁 日志文件位置：[/bold cyan]")
    log_files = [
        ("/tmp/sage-studio-engine.log", "Engine 日志"),
        ("/tmp/sage-studio-backend.log", "Backend 日志"),
        ("~/.local/state/sage/logs/studio.log", "Studio 前端日志"),
    ]
    
    for log_path, description in log_files:
        expanded = Path(log_path).expanduser()
        if expanded.exists():
            size = expanded.stat().st_size
            console.print(f"  ✅ {description}: {expanded} ({size} bytes)")
        else:
            console.print(f"  ❌ {description}: {expanded} (不存在)")


def main():
    """主入口"""
    asyncio.run(diagnose_chat_issue())


if __name__ == "__main__":
    main()
