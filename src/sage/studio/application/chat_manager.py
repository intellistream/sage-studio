"""Chat Mode Manager - Studio Manager with integrated LLM support"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import psutil
import requests
from rich.console import Console
from rich.table import Table
from sage.common.config import find_sage_project_root
from sage.common.config.user_paths import get_user_paths

from sage.studio.application.studio_manager import StudioManager
from sage.studio.config.ports import StudioPorts
from sage.studio.utils.gpu_check import is_gpu_available

console = Console()


class ChatModeManager(StudioManager):
    """Studio Manager with integrated local LLM support.

    Extends StudioManager to add sageLLM integration for local LLM services.
    This is now the default manager - no need for backward compatibility.
    """

    def __init__(self):
        super().__init__()

        # Local LLM service management (via sageLLM)
        self.llm_service = None  # Will be sageLLM service instance
        # All started LLM services: list of {"port": int, "log": Path}
        self.llm_services: list[dict] = []
        # Default to enabling LLM with a small model
        self.llm_enabled = os.getenv("SAGE_STUDIO_LLM", "true").lower() in ("true", "1", "yes")
        # Use Qwen2.5-0.5B as default - lightweight for local development
        self.llm_model = os.getenv("SAGE_STUDIO_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
        self.llm_port = StudioPorts.BENCHMARK_LLM  # Unified default port (8901)

        # Health monitoring
        self._health_monitor_thread: threading.Thread | None = None
        self._health_monitor_stop = threading.Event()
        self._last_model_name: str | None = None  # Track which model is running

    # ------------------------------------------------------------------
    # Fine-tuned Model Discovery
    # ------------------------------------------------------------------
    def list_finetuned_models(self) -> list[dict]:
        """List available fine-tuned models from Studio's finetune manager.

        Returns:
            List of fine-tuned model info dictionaries
        """
        try:
            from sage_libs.sage_finetune import finetune_manager

            models = []
            for task in finetune_manager.tasks.values():
                if task.status.value == "completed":
                    # Check for merged model (preferred) or LoRA checkpoint
                    output_path = Path(task.output_dir)
                    merged_path = output_path / "merged_model"
                    lora_path = output_path / "lora"

                    model_path = None
                    model_type = None

                    if merged_path.exists():
                        model_path = str(merged_path)
                        model_type = "merged"
                    elif lora_path.exists():
                        model_path = str(lora_path)
                        model_type = "lora"

                    if model_path:
                        models.append(
                            {
                                "path": model_path,
                                "name": task.task_id,
                                "base_model": task.model_name,
                                "type": model_type,
                                "completed_at": task.completed_at,
                            }
                        )

            return models
        except ImportError:
            console.print("[yellow]⚠️  FinetuneManager not available[/yellow]")
            return []

    def get_finetuned_model_path(self, model_name: str) -> str | None:
        """Get path of a fine-tuned model by name.

        Args:
            model_name: Task ID or model name

        Returns:
            Path to the fine-tuned model, or None if not found
        """
        models = self.list_finetuned_models()
        for model in models:
            if model["name"] == model_name or model_name in model["path"]:
                return model["path"]
        return None

    def apply_finetuned_model(self, model_path: str) -> dict[str, Any]:
        """Apply a finetuned model to the running LLM service (hot-swap).

        This will restart the local LLM service with the new model.
        Gateway will automatically detect the new model.

        **Architecture Note**: This method belongs in sage-studio (L6) because it
        directly depends on ChatModeManager and Studio-specific infrastructure.
        It was moved from sage-libs (L3) to fix architecture layering violations.

        Args:
            model_path: Path to the finetuned model (local path or HF model name)

        Returns:
            Dict with status and message
        """
        try:
            # Check if LLM service is running
            if not self.llm_service or not self.llm_service.is_running():
                return {
                    "success": False,
                    "message": "本地 LLM 服务未运行。请先启动 Studio 的 LLM 服务。",
                }

            print(f"🔄 正在切换到微调模型: {model_path}")

            # Stop current LLM service
            print("   停止当前 LLM 服务...")
            self.llm_service.stop()

            # Update config with new model
            import time

            time.sleep(2)  # Wait for cleanup

            from sage.studio.config.ports import StudioPorts

            # Use subprocess to start sageLLM full-stack (Gateway + Engine)
            serve_cmd = [
                "sage-llm",
                "serve",
                "--model",
                model_path,
                "--port",
                str(StudioPorts.LLM_DEFAULT),
            ]

            # Start new service with finetuned model
            print(f"   启动新模型: {model_path}")
            proc = subprocess.Popen(
                serve_cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.llm_service = proc
            success = True

            # Wait for service to be ready
            base_url = f"http://127.0.0.1:{StudioPorts.LLM_DEFAULT}/v1"
            for _ in range(30):
                try:
                    resp = requests.get(f"{base_url}/models", timeout=2)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                success = False

            if success:
                # Update FinetuneManager's current_model for UI display
                try:
                    from sage_libs.sage_finetune import finetune_manager

                    finetune_manager.current_model = model_path
                    finetune_manager._save_tasks()
                except Exception as e:
                    console.print(f"[yellow]Warning: 无法更新 FinetuneManager: {e}[/yellow]")

                console.print("[green]模型切换成功[/green]")
                console.print(f"   当前模型: {model_path}")
                console.print("   Gateway 会自动检测到新模型")

                return {
                    "success": True,
                    "message": f"成功切换到模型: {model_path}",
                    "model": model_path,
                }
            else:
                return {
                    "success": False,
                    "message": "LLM 服务启动失败，请查看日志",
                }

        except Exception as e:
            import traceback

            print(f"❌ 模型切换失败: {e}")
            print(traceback.format_exc())
            return {
                "success": False,
                "message": f"切换失败: {str(e)}",
            }

    # ------------------------------------------------------------------
    # Service Detection helpers
    # ------------------------------------------------------------------
    def _normalize_base_url(self, url: str | None) -> str | None:
        return url.rstrip("/") if url else url

    def _probe_llm_endpoint(self, base_url: str | None) -> bool:
        """Return True if the provided endpoint responds to /health.

        sageLLM provides /health endpoint (not /v1/models).
        """
        if not base_url:
            return False
        normalized = self._normalize_base_url(base_url)
        if not normalized:
            return False
        try:
            # Remove /v1 suffix if present (sageLLM health is at root level)
            if normalized.endswith("/v1"):
                base = normalized[:-3]  # Remove last 3 chars: '/v1'
            else:
                base = normalized
            health_url = base + "/health"
            resp = requests.get(health_url, timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _test_llm_inference(self, base_url: str | None) -> bool:
        """Test if LLM can actually perform inference (not just port check).

        Args:
            base_url: Base URL ending with /v1

        Returns:
            True if inference succeeds, False if engine is dead/OOM
        """
        if not base_url:
            return False

        normalized = self._normalize_base_url(base_url)
        if not normalized:
            return False

        try:
            # Send a minimal chat request
            resp = requests.post(
                f"{normalized}/chat/completions",
                json={
                    "model": "test",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                    "stream": False,
                },
                timeout=15,  # Allow time for inference
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _check_oom_killed(self, process_name: str = "sage-llm") -> bool:
        """Check if a process was OOM killed recently.

        Args:
            process_name: Process name to check in dmesg

        Returns:
            True if OOM kill detected
        """
        try:
            import subprocess

            result = subprocess.run(
                ["dmesg", "-T"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Check last 50 lines for recent OOM kills
                lines = result.stdout.strip().split("\n")[-50:]
                for line in lines:
                    if "oom-kill" in line.lower() and process_name in line.lower():
                        return True
        except Exception:
            pass
        return False

    def _start_health_monitor(self) -> None:
        """Start background health monitoring thread."""
        if self._health_monitor_thread and self._health_monitor_thread.is_alive():
            return  # Already running

        self._health_monitor_stop.clear()
        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True,
            name="LLM-HealthMonitor",
        )
        self._health_monitor_thread.start()
        console.print("[dim]🔍 已启动引擎健康监控[/dim]")

    def _stop_health_monitor(self) -> None:
        """Stop background health monitoring thread."""
        if self._health_monitor_thread and self._health_monitor_thread.is_alive():
            self._health_monitor_stop.set()
            self._health_monitor_thread.join(timeout=5)

    def _health_monitor_loop(self) -> None:
        """Background loop to monitor LLM engine health."""
        consecutive_failures = 0
        check_interval = 30  # Check every 30 seconds

        while not self._health_monitor_stop.wait(timeout=check_interval):
            try:
                base_url = f"http://127.0.0.1:{self.llm_port}/v1"

                # Quick port check first
                if not self._probe_llm_endpoint(base_url):
                    consecutive_failures += 1
                    console.print(
                        f"[yellow]⚠️  引擎健康检查失败 ({consecutive_failures}/3)[/yellow]"
                    )

                    if consecutive_failures >= 3:
                        # Check if OOM killed
                        if self._check_oom_killed("sage-llm") or self._check_oom_killed("python"):
                            console.print("[red]❌ 检测到引擎 OOM，尝试重启最小模型...[/red]")

                            # Stop dead service
                            self._stop_llm_service(force=True)
                            time.sleep(2)

                            # Restart with smallest model
                            if self._start_llm_service(model="Qwen/Qwen2.5-0.5B-Instruct"):
                                console.print("[green]✅ 引擎自动恢复成功[/green]")
                                consecutive_failures = 0
                            else:
                                console.print("[red]❌ 引擎自动恢复失败[/red]")
                                break  # Stop monitoring
                        else:
                            console.print("[yellow]⚠️  引擎意外停止，尝试重启...[/yellow]")
                            if self._last_model_name and self._start_llm_service(
                                model=self._last_model_name
                            ):
                                console.print("[green]✅ 引擎自动恢复成功[/green]")
                                consecutive_failures = 0
                            else:
                                console.print("[red]❌ 引擎自动恢复失败[/red]")
                                break
                else:
                    # Reset failure counter on success
                    if consecutive_failures > 0:
                        console.print("[green]✅ 引擎恢复正常[/green]")
                    consecutive_failures = 0

            except Exception as e:
                console.print(f"[yellow]⚠️  健康检查异常: {e}[/yellow]")
                consecutive_failures += 1

    def _detect_existing_llm_service(self) -> tuple[bool, str | None]:
        """Detect if LLM service is already running at known ports.

        Checks common LLM ports (8901, 8001, 8000) for existing service
        by probing the OpenAI-compatible /v1/models endpoint.

        Returns:
            Tuple of (is_running, base_url) - base_url is set if service found
        """
        candidates: list[str] = []
        seen: set[str] = set()

        def _add_candidate(url: str | None) -> None:
            normalized = self._normalize_base_url(url)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        # Ports to check in order of preference
        llm_ports = [
            self.llm_port,
            StudioPorts.get_recommended_llm_port(),
            StudioPorts.LLM_DEFAULT,
            StudioPorts.BENCHMARK_LLM,
        ]

        for port in llm_ports:
            _add_candidate(f"http://127.0.0.1:{port}/v1")

        for candidate in candidates:
            if self._probe_llm_endpoint(candidate):
                return True, candidate

        # Fallback: honor explicit env only if it is reachable AND loopback, to avoid
        # blocking auto-start when a cloud endpoint is configured.
        env_base_url = os.environ.get("SAGE_CHAT_BASE_URL") or os.environ.get(
            "SAGE_UNIFIED_BASE_URL"
        )
        if env_base_url and self._probe_llm_endpoint(env_base_url):
            try:
                parsed = requests.utils.urlparse(env_base_url)
                host = parsed.hostname
                if host and host in {"127.0.0.1", "localhost", "::1"}:
                    return True, env_base_url
            except Exception:
                pass

        return (False, None)

    def _detect_existing_embedding_service(
        self, port: int | None = None
    ) -> tuple[bool, str | None]:
        """Detect if Embedding service is already running.

        Args:
            port: Specific port to check, or None to check common ports

        Returns:
            Tuple of (is_running, base_url) - base_url is set if service found
        """
        # Check environment variables first (align with UnifiedInferenceClient)
        env_base_url = os.environ.get("SAGE_EMBEDDING_BASE_URL") or os.environ.get(
            "SAGE_UNIFIED_BASE_URL"
        )
        if env_base_url and self._probe_llm_endpoint(env_base_url):
            return (True, env_base_url)

        ports_to_check = (
            [port] if port else [StudioPorts.EMBEDDING_DEFAULT, StudioPorts.BENCHMARK_EMBEDDING]
        )

        for p in ports_to_check:
            if p is None:
                continue
            try:
                resp = requests.get(f"http://127.0.0.1:{p}/v1/models", timeout=2)
                if resp.status_code == 200:
                    return (True, f"http://127.0.0.1:{p}/v1")
            except Exception:
                continue

        return (False, None)

    # ------------------------------------------------------------------
    # Local LLM Service helpers (via sageLLM CLI subprocess)
    # ------------------------------------------------------------------
    def _select_model_by_memory(self, requested_model: str | None = None) -> str:
        """Select appropriate model based on available memory.

        Args:
            requested_model: User-requested model name

        Returns:
            Model name that fits in available memory
        """
        import psutil

        # Get available memory in GB
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024**3)

        # Model memory requirements (approximate, in GB)
        model_requirements = {
            "Qwen/Qwen2.5-0.5B-Instruct": 2.0,
            "Qwen/Qwen2.5-1.5B-Instruct": 6.0,
            "Qwen/Qwen2.5-3B-Instruct": 10.0,
            "Qwen/Qwen2.5-7B-Instruct": 18.0,
        }

        requested = requested_model or self.llm_model

        # Check if requested model fits
        required = model_requirements.get(requested, 6.0)  # Default 6GB if unknown

        if available_gb >= required:
            return requested

        # Auto-downgrade to smaller model
        console.print(
            f"[yellow]⚠️  内存不足 (可用: {available_gb:.1f}GB, 需要: {required:.1f}GB)[/yellow]"
        )

        # Try smaller models in order
        for model, req in sorted(model_requirements.items(), key=lambda x: x[1]):
            if available_gb >= req:
                console.print(f"[yellow]→  自动选择更小的模型: {model}[/yellow]")
                return model

        # Fallback to smallest model
        console.print("[yellow]→  使用最小模型: Qwen/Qwen2.5-0.5B-Instruct[/yellow]")
        return "Qwen/Qwen2.5-0.5B-Instruct"

    def _start_llm_service(self, model: str | None = None, use_finetuned: bool = False) -> bool:
        """Start local LLM service via sageLLM.

        Uses sageLLM CLI (sage-llm serve) to start the full sageLLM stack
        (Gateway + Control Plane + Engine). The Gateway provides an
        OpenAI-compatible API at http://127.0.0.1:{port}/v1

        If an LLM service is already running at known ports, it will be reused
        instead of starting a new one.

        Args:
            model: Model name/path to load (can be HF model or local path)
            use_finetuned: If True, try to use a fine-tuned model

        Returns:
            True if started successfully or existing service found, False otherwise
        """
        # First, check if LLM service is already running
        is_running, existing_url = self._detect_existing_llm_service()
        if is_running:
            console.print(f"[green]✅ 发现已运行的 LLM 服务: {existing_url}[/green]")
            console.print("[dim]   跳过启动新服务，将复用现有服务[/dim]")
            return True

        # Check if sage-llm CLI is available
        if shutil.which("sage-llm") is None:
            console.print(
                "[yellow]⚠️  sageLLM 未安装，跳过本地 LLM 启动[/yellow]\n提示：pip install isagellm"
            )
            return False

        # Determine which model to use with memory-aware selection
        requested_model = model or self.llm_model
        model_name = self._select_model_by_memory(requested_model)

        if model_name != requested_model:
            console.print(f"[blue]ℹ️  原请求模型: {requested_model}[/blue]")
            console.print(f"[green]✓  实际启动模型: {model_name}[/green]")

        # Get finetuned model path if needed
        if use_finetuned and not model:
            finetuned_models = self.list_finetuned_models()
            if finetuned_models:
                model_name = finetuned_models[0]["path"]
                console.print(f"[blue]🎯 使用微调模型: {model_name}[/blue]")
            else:
                console.print("[yellow]⚠️  未找到可用的微调模型，使用默认模型[/yellow]")

        # Launch sageLLM engine via CLI subprocess
        console.print(
            f"[blue]🚀 启动 sageLLM 引擎 (模型: {model_name}, 端口: {self.llm_port})...[/blue]"
        )

        log_dir = get_user_paths().logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        llm_log = log_dir / "llm_engine.log"

        serve_cmd = [
            "sage-llm",
            "serve",
            "--model",
            model_name,
            "--port",
            str(self.llm_port),
        ]

        try:
            log_handle = open(llm_log, "w")
            child_env = os.environ.copy()
            child_env["SAGELLM_PREFLIGHT_CANARY"] = "0"
            child_env["SAGELLM_STARTUP_CANARY"] = "0"
            child_env["SAGELLM_PERIODIC_CANARY"] = "0"
            proc = subprocess.Popen(
                serve_cmd,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=child_env,
            )

            # Save PID for later management
            llm_pid_file = log_dir / "llm_engine.pid"
            llm_pid_file.write_text(str(proc.pid))
            self.llm_service = proc  # Track the process
            self.llm_services.append({"port": self.llm_port, "log": llm_log})

            console.print(f"   [green]✓[/green] sageLLM 引擎已启动 (PID: {proc.pid})")
            console.print(f"   日志: {llm_log}")
        except FileNotFoundError:
            console.print("[yellow]⚠️  sage-llm 命令不可用[/yellow]")
            console.print("   提示：pip install isagellm")
            return False
        except Exception as exc:
            console.print(f"[red]❌ 启动 sageLLM 引擎失败: {exc}[/red]")
            return False

        # Wait for service to be ready (phase 1: initial 60s fast poll)
        console.print("[dim]   等待引擎就绪...[/dim]")
        base_url = f"http://127.0.0.1:{self.llm_port}/v1"
        engine_healthy = False
        for i in range(60):
            # Check if process is still alive
            if proc.poll() is not None:
                console.print("[red]❌ sageLLM 引擎进程已退出[/red]")
                console.print(f"   查看日志: {llm_log}")
                return False
            if self._probe_llm_endpoint(base_url):
                engine_healthy = True
                break
            time.sleep(1)

        if not engine_healthy:
            # Phase 2: extended retry with back-off (up to 120s more for CPU cold-start)
            console.print("[yellow]⚠️  引擎尚未就绪 (60s)，进程仍在运行，继续等待...[/yellow]")
            console.print(f"   查看日志: {llm_log}")
            retry_intervals = [2, 3, 5, 5, 5, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]  # ~120s extra
            for wait_s in retry_intervals:
                if proc.poll() is not None:
                    console.print("[red]❌ sageLLM 引擎进程已退出[/red]")
                    console.print(f"   查看日志: {llm_log}")
                    return False
                time.sleep(wait_s)
                if self._probe_llm_endpoint(base_url):
                    elapsed_extra = sum(retry_intervals[: retry_intervals.index(wait_s) + 1])
                    console.print(f"[green]   ✓ 引擎在额外等待 ~{elapsed_extra}s 后就绪[/green]")
                    engine_healthy = True
                    break

        if not engine_healthy:
            console.print("[yellow]⚠️  引擎启动超时 (约180s)，但进程仍在运行[/yellow]")
            console.print(f"   查看日志: {llm_log}")
            # Still try to verify inference below as a last-ditch attempt

        # Verify engine can actually perform inference
        console.print("[blue]🔍 验证引擎健康状态...[/blue]")
        time.sleep(2)

        # Retry inference test a few times (engine may need warm-up after health OK)
        inference_ok = False
        for attempt in range(3):
            if self._test_llm_inference(base_url):
                inference_ok = True
                break
            if attempt < 2:
                time.sleep(3)

        if inference_ok:
            console.print("[green]✅ 引擎验证成功，可正常推理[/green]")
            self._last_model_name = model_name
            self._start_health_monitor()
            return True
        else:
            console.print("[yellow]⚠️  引擎启动但无法推理，检查是否 OOM...[/yellow]")

            time.sleep(3)
            if self._check_oom_killed("sage-llm") or self._check_oom_killed("python"):
                console.print("[red]❌ 检测到 OOM (内存不足)，引擎已被系统杀死[/red]")

                if model_name != "Qwen/Qwen2.5-0.5B-Instruct":
                    console.print("[yellow]🔄 尝试使用最小模型 (0.5B) 重启...[/yellow]")
                    self._stop_llm_service(force=True)
                    time.sleep(2)
                    return self._start_llm_service(
                        model="Qwen/Qwen2.5-0.5B-Instruct",
                        use_finetuned=False,
                    )
                else:
                    console.print("[red]❌ 即使最小模型也内存不足，无法启动[/red]")
                    return False
            else:
                console.print("[yellow]⚠️  引擎无响应但未检测到 OOM，可能配置问题[/yellow]")
                return False

    def _stop_llm_service(self, force: bool = False) -> bool:
        """Stop local LLM service.

        Args:
            force: If True, aggressively scan and stop services on related ports.
        """
        # Stop health monitoring first
        self._stop_health_monitor()

        stopped = False

        # First, try to stop via self.llm_service (subprocess.Popen) if it exists
        if self.llm_service is not None:
            console.print("[blue]🛑 停止本地 LLM 服务...[/blue]")
            try:
                if hasattr(self.llm_service, "terminate"):
                    self.llm_service.terminate()
                    try:
                        self.llm_service.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.llm_service.kill()
                elif hasattr(self.llm_service, "stop"):
                    self.llm_service.stop()
                self.llm_service = None
                console.print("[green]✅ 本地 LLM 服务已停止[/green]")
                stopped = True
            except Exception as exc:
                console.print(f"[red]❌ 停止 LLM 服务失败: {exc}[/red]")

        # Try to stop via PID file
        log_dir = get_user_paths().logs_dir
        llm_pid_file = log_dir / "llm_engine.pid"
        if not stopped and llm_pid_file.exists():
            try:
                pid = int(llm_pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    console.print(f"[blue]🛑 停止 LLM 引擎 (PID: {pid})...[/blue]")
                    os.kill(pid, signal.SIGTERM)
                    for _ in range(10):
                        if not psutil.pid_exists(pid):
                            break
                        time.sleep(0.5)
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                    console.print("[green]✅ LLM 引擎已停止[/green]")
                    stopped = True
                llm_pid_file.unlink(missing_ok=True)
            except Exception as e:
                console.print(f"[yellow]⚠️  清理 LLM PID 文件失败: {e}[/yellow]")

        # If force is enabled, scan LLM port range (8001, 8901-8910)
        if force:
            for port in [StudioPorts.LLM_DEFAULT] + list(range(8901, 8911)):
                try:
                    for conn in psutil.net_connections(kind="inet"):
                        if conn.status == "LISTEN" and conn.laddr.port == port:
                            pid = conn.pid
                            if pid:
                                console.print(
                                    f"[blue]🛑 发现端口 {port} 上的残留服务 (PID: {pid})...[/blue]"
                                )
                                try:
                                    proc = psutil.Process(pid)
                                    proc.terminate()
                                    try:
                                        proc.wait(timeout=5)
                                    except psutil.TimeoutExpired:
                                        proc.kill()
                                    console.print(f"[green]✅ 服务已停止 (端口 {port})[/green]")
                                    stopped = True
                                except Exception as e:
                                    console.print(f"[yellow]⚠️ 停止失败: {e}[/yellow]")
                                    try:
                                        os.kill(pid, signal.SIGKILL)
                                    except Exception:
                                        pass
                except Exception:
                    pass

        return stopped

    # ------------------------------------------------------------------
    # Embedding Service helpers
    # ------------------------------------------------------------------
    def _load_models_config(self) -> list[dict[str, object]]:
        try:
            project_root = find_sage_project_root()
        except Exception:
            project_root = None

        if not project_root:
            project_root = Path.cwd()

        config_path = project_root / "config" / "models.json"
        if not config_path.exists():
            return []

        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)

            # Expand environment variables in api_key
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        api_key = entry.get("api_key")
                        if (
                            isinstance(api_key, str)
                            and api_key.startswith("${")
                            and api_key.endswith("}")
                        ):
                            env_var = api_key[2:-1]
                            entry["api_key"] = os.getenv(env_var, "")

            return data if isinstance(data, list) else []
        except Exception as exc:
            console.print(f"[yellow]⚠️ 读取模型配置失败: {exc}[/yellow]")
            return []

    def _select_embedding_model_from_config(self) -> str | None:
        candidates = [
            entry
            for entry in self._load_models_config()
            if entry.get("engine_kind") == "embedding" and not entry.get("base_url")
        ]
        if not candidates:
            return None
        preferred = next((entry for entry in candidates if entry.get("default")), candidates[0])
        return preferred.get("name")

    def _start_embedding_service(self, model: str | None = None, port: int | None = None) -> bool:
        """Start Embedding service as a background process.

        If an Embedding service is already running at known ports, it will be reused
        instead of starting a new one.

        Args:
            model: Embedding model name (default: config/models.json embedding or BAAI/bge-m3)
            port: Server port (default: StudioPorts.EMBEDDING_DEFAULT = 8090)

        Returns:
            True if started successfully or existing service found
        """
        if port is None:
            port = StudioPorts.EMBEDDING_DEFAULT  # 8090

        selected_model = model or self._select_embedding_model_from_config()
        model_name = selected_model or "BAAI/bge-small-zh-v1.5"

        # Check if already running (use the new detection method for consistent output)
        is_running, existing_url = self._detect_existing_embedding_service(port)
        if is_running:
            console.print(f"[green]✅ 发现已运行的 Embedding 服务: {existing_url}[/green]")
            console.print("[dim]   跳过启动新服务，将复用现有服务[/dim]")
            return True

        if selected_model:
            console.print(
                f"[blue]🎯 根据 config/models.json 启动 Embedding 模型: {model_name}[/blue]"
            )
        console.print(f"[blue]🎯 启动 Embedding 服务 (模型: {model_name}, 端口: {port})[/blue]")

        # Ensure log directory exists
        log_dir = get_user_paths().logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        embedding_log = log_dir / "embedding.log"

        embedding_cmd = [
            sys.executable,
            "-m",
            "sagellm_core.embedding_server",
            "--port",
            str(port),
        ]

        # The embedding_server reads model from SAGELLM_EMBEDDING_MODEL env var
        embedding_env = {**os.environ, "SAGELLM_EMBEDDING_MODEL": model_name}

        try:
            with open(embedding_log, "w") as log_handle:
                proc = subprocess.Popen(
                    embedding_cmd,
                    stdin=subprocess.DEVNULL,  # 阻止子进程读取 stdin
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=embedding_env,
                    start_new_session=True,
                )
                # Log handle will be closed by context manager,
                # but subprocess keeps its copy open

            # Save PID for later cleanup
            embedding_pid_file = log_dir / "embedding.pid"
            embedding_pid_file.write_text(str(proc.pid))

            console.print(f"   [green]✓[/green] Embedding 服务已启动 (PID: {proc.pid})")

            # Wait for service to be ready (up to 180 seconds for model download)
            console.print("   [dim]等待服务就绪 (首次可能需要下载模型)...[/dim]")
            for i in range(180):
                # Check if process is still alive
                if proc.poll() is not None:
                    console.print("[red]❌ Embedding 服务进程已退出[/red]")
                    console.print(f"   查看日志: {embedding_log}")
                    return False

                try:
                    # Use /health endpoint (more reliable than /v1/models)
                    resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
                    if resp.status_code == 200:
                        console.print("   [green]✓[/green] Embedding 服务已就绪")
                        return True
                except Exception:
                    pass
                time.sleep(1)

            console.print("[yellow]⚠️  Embedding 服务启动超时，但进程仍在运行[/yellow]")
            console.print(f"   查看日志: {embedding_log}")
            return True  # Process started, might just be slow to load model

        except Exception as e:
            console.print(f"[red]❌ 启动 Embedding 服务失败: {e}[/red]")
            return False

    def _stop_embedding_service(self, force: bool = False) -> bool:
        """Stop Embedding service if running.

        Args:
            force: If True, kill process on embedding port even if PID file is missing.

        NOTE: Only stops the service if it was started by Studio (has PID file).
        Does NOT kill orphan processes to allow reuse of manually started services,
        unless force=True is specified.
        """
        log_dir = Path.home() / ".sage" / "logs"
        embedding_pid_file = log_dir / "embedding.pid"

        stopped = False

        # Try to stop via PID file first
        if embedding_pid_file.exists():
            try:
                pid = int(embedding_pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    console.print(f"[blue]🛑 停止 Embedding 服务 (PID: {pid})...[/blue]")
                    os.kill(pid, signal.SIGTERM)
                    # Wait for graceful shutdown
                    for _ in range(5):
                        if not psutil.pid_exists(pid):
                            break
                        time.sleep(0.5)
                    # Force kill if still running
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                    console.print("[green]✅ Embedding 服务已停止[/green]")
                    stopped = True
                embedding_pid_file.unlink()
            except Exception as e:
                console.print(f"[yellow]⚠️  清理 Embedding PID 文件失败: {e}[/yellow]")

        if force and not stopped:
            # Check default embedding port
            port = StudioPorts.EMBEDDING_DEFAULT  # 8090
            try:
                for conn in psutil.net_connections(kind="inet"):
                    if conn.status == "LISTEN" and conn.laddr.port == port:
                        pid = conn.pid
                        if pid:
                            console.print(
                                f"[blue]🛑 发现 Embedding 端口 {port} 上的残留服务 (PID: {pid})...[/blue]"
                            )
                            try:
                                proc = psutil.Process(pid)
                                proc.terminate()
                                try:
                                    proc.wait(timeout=5)
                                except psutil.TimeoutExpired:
                                    proc.kill()
                                console.print(
                                    f"[green]✅ Embedding 服务已停止 (端口 {port})[/green]"
                                )
                                stopped = True
                            except Exception as e:
                                console.print(f"[yellow]⚠️ 停止失败: {e}[/yellow]")
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except Exception:
                                    pass
            except Exception:
                pass

        return stopped

    # ------------------------------------------------------------------
    # Gateway helpers
    # ------------------------------------------------------------------
    def _is_gateway_running(self) -> int | None:
        """Detect a running gateway process and align internal state.

        Looks at the PID file first, then scans candidate ports (current, default,
        fallback, and env override) for a process whose cmdline includes
        ``sagellm_gateway``/``sagellm-gateway``. When found, updates
        ``self.gateway_port`` and rewrites the PID file so subsequent stop/restart
        flows can clean it up.
        """

        candidate_ports: set[int] = {
            self.gateway_port,
            StudioPorts.GATEWAY,
            8899,  # Edge port
        }

        for env_name in ("SAGE_GATEWAY_PORT", "SAGELLM_GATEWAY_PORT"):
            env_port = os.environ.get(env_name)
            if env_port:
                try:
                    candidate_ports.add(int(env_port))
                except ValueError:
                    pass

        # 1) PID file check
        if self.gateway_pid_file.exists():
            try:
                pid = int(self.gateway_pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    return pid
            except Exception:
                pass

            # Clean up invalid PID file
            try:
                self.gateway_pid_file.unlink()
            except OSError:
                pass

        # 2) Scan known ports for our gateway process (handles orphaned starts)
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    for conn in proc.connections(kind="inet"):
                        if conn.status != psutil.CONN_LISTEN:
                            continue
                        if conn.laddr.port not in candidate_ports:
                            continue

                        try:
                            cmdline = " ".join(proc.cmdline())
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            cmdline = ""

                        if (
                            "sagellm_gateway" not in cmdline
                            and "sagellm-gateway" not in cmdline
                            and "sage-llm-gateway" not in cmdline
                        ):
                            continue

                        # Align internal state to the discovered process
                        try:
                            self.gateway_port = conn.laddr.port
                        except Exception:
                            pass
                        try:
                            self.gateway_pid_file.write_text(str(proc.pid))
                        except Exception:
                            pass
                        return proc.pid
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

        return None

    def _start_gateway(self, port: int | None = None) -> bool:
        if self._is_gateway_running():
            console.print("[green]✅ sage-gateway 已运行[/green]")
            return True

        # Skip slow import check - just try to start directly
        # If gateway is not installed, subprocess will fail anyway
        gateway_port = port or self.gateway_port

        # Detect user override; only auto-fallback when using built-in default
        explicit_port = (port is not None) or ("SAGE_GATEWAY_PORT" in os.environ)

        # Check if port is in use
        if self._is_port_in_use(gateway_port):
            console.print(f"[yellow]⚠️  端口 {gateway_port} 已被占用[/yellow]")
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        for conn in proc.connections(kind="inet"):
                            if conn.laddr.port == gateway_port:
                                console.print(
                                    f"[yellow]   占用进程: {proc.pid} ({proc.name()})[/yellow]"
                                )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception:
                pass

            if (not explicit_port) and gateway_port == StudioPorts.GATEWAY:
                fallback_port = 8899  # Try Edge port
                console.print(
                    f"[cyan]💡 端口 {gateway_port} 被占用，自动切换 Gateway 到 {fallback_port}[/cyan]"
                )
                gateway_port = fallback_port
                self.gateway_port = fallback_port
            else:
                console.print(
                    "[yellow]继续尝试当前端口，若失败请手动指定 --gateway-port 或设置 SAGE_GATEWAY_PORT[/yellow]"
                )

        env = os.environ.copy()
        env.setdefault("SAGE_GATEWAY_PORT", str(gateway_port))
        # sagellm-gateway reads SAGELLM_GATEWAY_PORT (not SAGE_GATEWAY_PORT)
        env["SAGELLM_GATEWAY_PORT"] = str(gateway_port)

        console.print(f"[blue]🚀 启动 sagellm-gateway (端口: {gateway_port})...[/blue]")
        try:
            log_handle = open(self.gateway_log_file, "w")
            process = subprocess.Popen(
                [sys.executable, "-m", "sagellm_gateway.server"],
                stdin=subprocess.DEVNULL,  # 阻止子进程读取 stdin
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if os.name != "nt" else None,
                env=env,
            )
            self.gateway_pid_file.write_text(str(process.pid))
        except Exception as exc:
            console.print(f"[red]❌ 启动 gateway 失败: {exc}")
            console.print(
                "[yellow]提示: 请确保已安装 sagellm-gateway: pip install isagellm[/yellow]"
            )
            return False

        # 等待服务就绪 - Gateway 需要加载 MemoryManager 和 FAISS 索引，需要更长时间
        url = f"http://127.0.0.1:{gateway_port}/health"
        max_attempts = 120  # 最多等待 60 秒 (120 * 0.5)
        console.print("[blue]   等待 Gateway 服务就绪...[/blue]")
        for i in range(max_attempts):
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    console.print(f"[green]✅ Gateway 已就绪 (耗时 {(i + 1) * 0.5:.1f}秒)[/green]")
                    return True
            except requests.RequestException:
                pass
            # 每 10 秒输出一次状态
            if (i + 1) % 20 == 0:
                console.print(
                    f"[blue]   等待 Gateway 响应... ({(i + 1) * 0.5:.0f}/{max_attempts * 0.5:.0f}秒)[/blue]"
                )
                # 检查进程是否还在
                if self.gateway_pid_file.exists():
                    try:
                        pid = int(self.gateway_pid_file.read_text().strip())
                        if not psutil.pid_exists(pid):
                            console.print("[red]❌ Gateway 进程已退出[/red]")
                            # 输出日志帮助调试
                            if self.gateway_log_file.exists():
                                console.print("[yellow]Gateway 日志（最后 20 行）:[/yellow]")
                                try:
                                    lines = self.gateway_log_file.read_text().splitlines()
                                    for line in lines[-20:]:
                                        console.print(f"[dim]  {line}[/dim]")
                                except Exception:
                                    pass
                            return False
                    except Exception:
                        pass
            time.sleep(0.5)

        # 超时，检查进程状态
        console.print("[yellow]⚠️ Gateway 启动超时[/yellow]")
        if self.gateway_pid_file.exists():
            try:
                pid = int(self.gateway_pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    console.print(f"[yellow]   进程仍在运行 (PID: {pid})，可能仍在初始化[/yellow]")
                    # 输出日志帮助调试
                    if self.gateway_log_file.exists():
                        console.print("[yellow]   Gateway 日志（最后 30 行）:[/yellow]")
                        try:
                            lines = self.gateway_log_file.read_text().splitlines()
                            for line in lines[-30:]:
                                console.print(f"[dim]  {line}[/dim]")
                        except Exception:
                            pass
                    return True  # 进程还在，可能只是启动慢
                else:
                    console.print("[red]❌ Gateway 进程已退出[/red]")
                    return False
            except Exception:
                pass
        return False

    def _stop_gateway(self) -> bool:
        pid = self._is_gateway_running()
        if not pid:
            console.print("[yellow]gateway 未运行[/yellow]")
            return True

        console.print(f"[blue]🛑 停止 sage-gateway (PID: {pid})...[/blue]")
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True)
            else:
                # Try to kill process group first
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    # Fallback to killing PID directly
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

                # Wait for process to exit
                for _ in range(10):
                    if not psutil.pid_exists(pid):
                        break
                    time.sleep(0.5)

                if psutil.pid_exists(pid):
                    console.print("[yellow]⚠️  Gateway 未响应 SIGTERM，尝试强制停止...[/yellow]")
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass

            # Double check port release
            import socket

            port_free = False
            for _ in range(10):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("localhost", self.gateway_port)) != 0:
                        port_free = True
                        break
                time.sleep(0.5)

            # If port is still in use, check if another process took it (or zombie/orphan)
            if not port_free:
                console.print(
                    f"[yellow]⚠️  端口 {self.gateway_port} 仍被占用，检查残留进程...[/yellow]"
                )
                try:
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            for conn in proc.connections(kind="inet"):
                                if conn.laddr.port == self.gateway_port:
                                    console.print(
                                        f"[yellow]⚠️  发现残留进程 {proc.pid} ({proc.name()}) 占用端口，强制清理...[/yellow]"
                                    )
                                    proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception:
                    pass

            self.gateway_pid_file.unlink(missing_ok=True)
            console.print("[green]✅ gateway 已停止[/green]")
            return True
        except Exception as exc:
            console.print(f"[red]❌ 停止 gateway 失败: {exc}")
            return False

    # ------------------------------------------------------------------
    # Engine Registration with Gateway Control Plane
    # ------------------------------------------------------------------
    def _register_engines_with_gateway(self) -> None:
        """Register running LLM and Embedding engines with Gateway's Control Plane.

        After the gateway starts, the Control Plane has no knowledge of running
        engines. This method discovers running LLM/Embedding services and
        registers them via the management API.
        """
        gw_base = f"http://127.0.0.1:{self.gateway_port}"
        register_url = f"{gw_base}/v1/management/engines/register"
        unregister_base = f"{gw_base}/v1/management/engines"

        # --- Register LLM engine(s) ---
        # Scan the LLM port range for running engines
        llm_ports_to_check = list(range(StudioPorts.BENCHMARK_LLM, StudioPorts.BENCHMARK_LLM + 10))
        llm_ports_to_check.append(StudioPorts.LLM_DEFAULT)  # 8001
        registered_llm_count = 0
        for port in llm_ports_to_check:
            if port == self.gateway_port:
                continue

            health_url = f"http://127.0.0.1:{port}/health"
            health_ready = False
            for _ in range(8):
                try:
                    resp = requests.get(health_url, timeout=2)
                    if resp.status_code == 200:
                        health_ready = True
                        break
                except requests.RequestException:
                    pass
                time.sleep(1)

            if not health_ready:
                continue

            model_names: list[str] = []
            for _ in range(8):
                try:
                    models_resp = requests.get(f"http://127.0.0.1:{port}/v1/models", timeout=2)
                    if models_resp.status_code == 200:
                        data = models_resp.json()
                        model_names = [
                            str(model.get("id", "")).strip()
                            for model in data.get("data", [])
                            if str(model.get("id", "")).strip()
                        ]
                    if model_names:
                        break
                except Exception:
                    pass
                time.sleep(1)

            if not model_names:
                continue

            model_name = model_names[0]

            engine_id = f"engine-llm-{port}"
            # Unregister first to handle restart (ignore 404)
            try:
                requests.delete(f"{unregister_base}/{engine_id}", timeout=3)
            except Exception:
                pass

            payload = {
                "engine_id": engine_id,
                "model_id": model_name,
                "host": "127.0.0.1",
                "port": port,
                "engine_kind": "llm",
            }
            try:
                r = requests.post(register_url, json=payload, timeout=5)
                if r.status_code == 200:
                    registered_llm_count += 1
                    console.print(
                        f"[green]✅ 已注册 LLM 引擎到 Gateway: {model_name} @ :{port}[/green]"
                    )
                else:
                    console.print(f"[yellow]⚠️  注册 LLM 引擎失败 (:{port}): {r.text}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]⚠️  注册 LLM 引擎异常 (:{port}): {e}[/yellow]")

        if registered_llm_count == 0:
            console.print(
                "[yellow]⚠️  未发现可注册的 LLM 引擎端口（已跳过网关端口）。请检查模型引擎是否真正启动。[/yellow]"
            )

        # --- Register Embedding engine ---
        embed_port = StudioPorts.EMBEDDING_DEFAULT
        try:
            resp = requests.get(f"http://127.0.0.1:{embed_port}/health", timeout=2)
            if resp.status_code != 200:
                raise requests.RequestException("not healthy")
        except requests.RequestException:
            # Try /v1/models as fallback health check
            try:
                resp = requests.get(f"http://127.0.0.1:{embed_port}/v1/models", timeout=2)
                if resp.status_code != 200:
                    return
            except requests.RequestException:
                return

        # Determine embedding model name
        embed_model = "unknown"
        try:
            model_resp = requests.get(f"http://127.0.0.1:{embed_port}/v1/models", timeout=2)
            if model_resp.status_code == 200:
                data = model_resp.json()
                models = data.get("data", [])
                if models:
                    embed_model = models[0].get("id", embed_model)
        except Exception:
            pass

        embed_engine_id = f"engine-embedding-{embed_port}"
        # Unregister first to handle restart (ignore 404)
        try:
            requests.delete(f"{unregister_base}/{embed_engine_id}", timeout=3)
        except Exception:
            pass

        payload = {
            "engine_id": embed_engine_id,
            "model_id": embed_model,
            "host": "127.0.0.1",
            "port": embed_port,
            "engine_kind": "embedding",
        }
        try:
            r = requests.post(register_url, json=payload, timeout=5)
            if r.status_code == 200:
                console.print(
                    f"[green]✅ 已注册 Embedding 引擎到 Gateway: {embed_model} @ :{embed_port}[/green]"
                )
            else:
                console.print(f"[yellow]⚠️  注册 Embedding 引擎失败: {r.text}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️  注册 Embedding 引擎异常: {e}[/yellow]")

    # ------------------------------------------------------------------
    # Auto-Scaling Logic
    # ------------------------------------------------------------------
    def _get_gpu_memory(self) -> list[dict[str, int]]:
        """Get GPU memory info for all GPUs.

        Returns:
            List of dicts: [{'index': 0, 'total': 81920, 'free': 81920}, ...]
        """
        try:
            # Check if nvidia-smi exists
            if shutil.which("nvidia-smi") is None:
                return []

            # Get info for all GPUs
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                encoding="utf-8",
            )

            gpus = []
            for line in output.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) >= 3:
                    gpus.append(
                        {
                            "index": int(parts[0].strip()),
                            "total": int(parts[1].strip()),
                            "free": int(parts[2].strip()),
                        }
                    )

            return gpus
        except Exception:
            return []

    def _get_used_llm_ports(self) -> set[int]:
        """Discover LLM ports in use by scanning listening TCP connections."""
        ports: set[int] = set()
        llm_range = range(StudioPorts.LLM_DEFAULT, StudioPorts.BENCHMARK_LLM + 10)
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr.port in llm_range:
                    ports.add(conn.laddr.port)
        except Exception:
            pass
        return ports

    def _find_free_llm_port(self, start_port: int, used_ports: set[int]) -> int | None:
        """Return the next available TCP port for LLM services (clamped to 8901-8910)."""
        from sage.studio.config.ports import StudioPorts

        port = max(start_port, StudioPorts.BENCHMARK_LLM)
        max_port = StudioPorts.BENCHMARK_LLM + 9  # 8901-8910 inclusive
        while port <= max_port:
            if port not in used_ports and not self._is_port_in_use(port):
                return port
            port += 1
        return None

    def _auto_start_llms(self, start_port: int | None = None) -> bool:
        """Automatically start multiple LLMs to fill GPU memory."""
        gpus = self._get_gpu_memory()
        if not gpus:
            return False

        total_system_mem = sum(g["total"] for g in gpus)
        free_system_mem = sum(g["free"] for g in gpus)

        console.print(
            f"[blue]🧠 检测到 {len(gpus)} 个 GPU: 总计 {total_system_mem} MB, 可用 {free_system_mem} MB[/blue]"
        )
        for gpu in gpus:
            console.print(
                f"[dim]   GPU {gpu['index']}: {gpu['free']} MB free / {gpu['total']} MB total[/dim]"
            )

        console.print("[blue]🚀 正在根据显存自动调度模型 (Auto-Scaling)...[/blue]")

        # Candidates: Name, Approx Memory (MB) (BF16 + Cache overhead)
        # 32B ~ 65GB, 14B ~ 30GB, 7B ~ 16GB, 1.5B ~ 4GB, 0.5B ~ 2GB
        candidates = [
            ("Qwen/Qwen2.5-32B-Instruct", 65000),
            ("Qwen/Qwen2.5-14B-Instruct", 30000),
            ("Qwen/Qwen2.5-7B-Instruct", 16000),
            ("Qwen/Qwen2.5-1.5B-Instruct", 4000),
            ("Qwen/Qwen2.5-0.5B-Instruct", 2000),
        ]

        started_count = 0
        current_port = start_port or self.llm_port  # 8901 default
        used_ports = self._get_used_llm_ports()

        # Check if sage-llm CLI is available
        if shutil.which("sage-llm") is None:
            console.print("[yellow]⚠️  sageLLM 未安装，跳过自动调度[/yellow]")
            return False

        log_dir = get_user_paths().logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        for model_name, required_mem in candidates:
            # Sort GPUs by free memory descending (to match api_server.py selection logic)
            gpus.sort(key=lambda x: x["free"], reverse=True)

            # Try to find a GPU that fits the model
            target_gpu = None
            for gpu in gpus:
                # Check if we have enough remaining memory (leave 2GB buffer)
                if gpu["free"] > (required_mem + 2000):
                    target_gpu = gpu
                    break

            if target_gpu:
                # gpu_memory_utilization is based on TOTAL memory of the specific GPU
                # Add 4GB buffer to utilization to ensure enough space for KV cache + overhead
                utilization = (required_mem + 4000) / target_gpu["total"]
                # Cap at 0.95 to be safe (default is 0.9)
                if utilization > 0.95:
                    utilization = 0.95
                # Min utilization 0.1
                if utilization < 0.1:
                    utilization = 0.1

                next_port = self._find_free_llm_port(current_port, used_ports)
                if next_port is None:
                    console.print("[yellow]⚠️  没有可用端口用于新的 LLM 服务，停止自动调度[/yellow]")
                    break

                console.print(
                    f"[blue]   尝试启动 {model_name} (端口 {next_port}, 显存 {utilization:.1%})...[/blue]"
                )

                try:
                    llm_log = log_dir / f"llm_engine_{next_port}.log"
                    engine_port = next_port + 1  # sagellm 内部引擎端口 (gateway+1)
                    serve_cmd = [
                        "sage-llm",
                        "serve",
                        "--model",
                        model_name,
                        "--port",
                        str(next_port),
                        "--engine-port",
                        str(engine_port),
                    ]
                    log_handle = open(llm_log, "w")
                    child_env = os.environ.copy()
                    child_env["SAGELLM_PREFLIGHT_CANARY"] = "0"
                    child_env["SAGELLM_STARTUP_CANARY"] = "0"
                    child_env["SAGELLM_PERIODIC_CANARY"] = "0"
                    proc = subprocess.Popen(
                        serve_cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        env=child_env,
                    )

                    # Wait briefly to check if process started
                    time.sleep(3)
                    if proc.poll() is None:
                        console.print(f"[green]✅ {model_name} 启动成功 (PID: {proc.pid})[/green]")
                        # Update virtual free memory for the target GPU
                        target_gpu["free"] -= required_mem
                        used_ports.add(next_port)
                        used_ports.add(engine_port)  # 同时占用内部引擎端口
                        started_count += 1
                        current_port = next_port + 2  # 跳过 gateway port + engine port
                        self.llm_services.append({"port": next_port, "log": llm_log})

                        if self.llm_service is None:
                            self.llm_service = proc
                    else:
                        console.print(f"[yellow]⚠️ {model_name} 启动失败，尝试下一个...[/yellow]")

                except Exception as e:
                    console.print(f"[red]❌ 启动 {model_name} 出错: {e}[/red]")

        if started_count > 0:
            console.print(f"[green]✨ 自动调度完成，共启动 {started_count} 个模型[/green]")
            return True

        console.print("[yellow]⚠️ 自动调度未启动任何模型 (可能是显存不足)[/yellow]")
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(
        self,
        frontend_port: int | None = None,
        backend_port: int | None = None,
        gateway_port: int | None = None,
        host: str = "localhost",
        dev: bool = True,
        llm: bool | None = None,
        llm_model: str | None = None,
        use_finetuned: bool = False,
        skip_confirm: bool = False,
        no_embedding: bool = False,
    ) -> bool:
        """Start Studio Chat Mode services.

        Args:
            frontend_port: Studio frontend port
            backend_port: Studio backend port
            gateway_port: Gateway API port (default: 8000)
            host: Host to bind to
            dev: Run in development mode
            llm: Enable local LLM service via sageLLM (default: from SAGE_STUDIO_LLM env)
            llm_model: Model to load (default: from SAGE_STUDIO_LLM_MODEL env)
            use_finetuned: Use latest fine-tuned model (overrides llm_model if True)
            skip_confirm: Skip all interactive confirmations (for CI/CD)
            no_embedding: Disable Embedding service (for CI/CD without GPU)

        Returns:
            True if all services started successfully
        """
        if gateway_port:
            self.gateway_port = gateway_port

        # Determine if local LLM should be started
        start_llm = llm if llm is not None else self.llm_enabled

        # DEBUG
        console.print(
            f"[dim]DEBUG: llm arg={llm}, llm_enabled={self.llm_enabled}, start_llm={start_llm}[/dim]"
        )

        # Start local LLM service first (if enabled)
        # Note: sageLLM supports multiple backends (CPU, CUDA, NPU).
        # Do NOT gate on GPU availability — sageLLM handles backend selection.
        if start_llm:
            llm_started = False

            # Check if user requested specific model or finetuned
            is_specific_request = (llm_model is not None) or use_finetuned

            # Try GPU Auto-Scaling if:
            # 1. No specific model requested
            # 2. GPU is available (auto-scaling uses GPU memory info)
            # 3. No existing service running (to avoid conflicts)
            if not is_specific_request and is_gpu_available():
                is_running, existing_url = self._detect_existing_llm_service()
                should_auto_scale = False
                if not is_running:
                    should_auto_scale = True
                else:
                    # Existing LLM detected — skip auto-scaling by default.
                    # Only ask when running interactively (no --yes).
                    if skip_confirm:
                        # --yes: silently reuse the existing service, no additional scaling
                        should_auto_scale = False
                        console.print(
                            f"[dim]已有 LLM 服务 ({existing_url or 'unknown'})，跳过自动扩容。[/dim]"
                        )
                    else:
                        prompt_msg = (
                            f"[cyan]检测到已有 LLM 服务 ({existing_url}). 仍要继续自动扩容更多模型吗？[/cyan]"
                            if existing_url
                            else "[cyan]检测到已有 LLM 服务。仍要继续自动扩容更多模型吗？[/cyan]"
                        )
                        try:
                            from rich.prompt import Confirm

                            should_auto_scale = Confirm.ask(prompt_msg, default=False)
                        except ImportError:
                            should_auto_scale = False

                if should_auto_scale:
                    starting_port = self._find_free_llm_port(
                        self.llm_port, self._get_used_llm_ports()
                    )
                    llm_started = self._auto_start_llms(start_port=starting_port or self.llm_port)

            # Fallback / Standard Mode
            # If auto-scaling skipped or failed, use standard start logic
            if not llm_started:
                model = llm_model or self.llm_model if not use_finetuned else None
                llm_started = self._start_llm_service(model=model, use_finetuned=use_finetuned)

            if llm_started:
                console.print(
                    "[green]💡 Gateway 将自动使用本地 LLM 服务（通过 UnifiedInferenceClient 自动检测）[/green]"
                )
            else:
                console.print(
                    "[yellow]⚠️  本地 LLM 未启动，Gateway 将使用云端 API（如已配置）[/yellow]"
                )

        # Start Embedding service (needed for knowledge indexing, independent of LLM)
        if not no_embedding:
            self._start_embedding_service()
        else:
            console.print("[yellow]⚠️  Embedding 服务已禁用 (--no-embedding)[/yellow]")

        # Start Gateway
        if not self._start_gateway(port=self.gateway_port):
            return False

        # Register engines with Gateway's Control Plane
        self._register_engines_with_gateway()

        # Start Studio UI (use parent class method)
        console.print("[blue]⚙️ 启动 Studio 服务...[/blue]")
        success = super().start(
            port=frontend_port,
            host=host,
            dev=dev,
            backend_port=backend_port,
            auto_gateway=False,  # We manage gateway ourselves
            auto_llm=False,  # We manage LLM ourselves
            skip_confirm=skip_confirm,  # Pass through for auto-confirm in CI/CD
        )

        if success:
            # 获取实际端口（从配置文件读取）
            config = self.load_config()
            actual_port = config.get("port", frontend_port or 5173)
            actual_host = config.get("host", host or "0.0.0.0")
            backend_port = config.get("backend_port", self.backend_port)

            # 收集所有服务信息（按工作流程顺序）
            log_dir = get_user_paths().logs_dir
            service_info = []  # (服务名, 端口, 日志路径)

            # 1. LLM 引擎（可能有多个）
            if start_llm and self.llm_services:
                for i, svc in enumerate(self.llm_services):
                    label = "LLM 引擎" if i == 0 else f"LLM 引擎 #{i + 1}"
                    service_info.append((label, svc["port"], svc["log"]))
            elif start_llm and self.llm_service:
                # Fallback: service was reused/detected but not tracked in llm_services
                llm_log = log_dir / "llm_engine.log"
                service_info.append(("LLM 引擎", self.llm_port, llm_log))

            # 2. Embedding 服务
            if not no_embedding:
                embedding_log = log_dir / "embedding.log"
                service_info.append(
                    ("Embedding 服务", StudioPorts.EMBEDDING_DEFAULT, embedding_log)
                )

            # 3. Gateway
            if self.gateway_log_file.exists():
                service_info.append(("Gateway", self.gateway_port, self.gateway_log_file))

            # 4. Studio 后端
            if self.backend_log_file.exists():
                service_info.append(("Studio 后端", backend_port, self.backend_log_file))

            # 5. Studio 前端
            if self.log_file.exists():
                service_info.append(("Studio 前端", actual_port, self.log_file))

            # 统一显示服务信息和日志链接
            console.print("\n" + "=" * 70)
            console.print("[green]🎉 Chat 模式就绪！[/green]")
            console.print("=" * 70)

            # 显示访问地址
            console.print(f"[blue]🎨 Studio 前端: http://{actual_host}:{actual_port}[/blue]")
            console.print("[green]💬 打开顶部 Chat 标签即可体验[/green]")

            # 显示所有服务状态（按工作流程顺序）
            if service_info:
                console.print("\n[cyan]📡 运行中的服务：[/cyan]")
                max_name_len = max(len(name) for name, _, _ in service_info)
                for name, port, log_path in service_info:
                    console.print(
                        f"   {name:<{max_name_len}} | 端口: [yellow]{port:<5}[/yellow] | 日志: [dim]{log_path}[/dim]"
                    )

            console.print("=" * 70 + "\n")

        return success

    def stop(self, stop_gateway: bool = False, stop_llm: bool = False) -> bool:
        """Stop Studio Chat Mode services.

        Args:
            stop_gateway: If True, also stop gateway service.
            stop_llm: If True, also stop LLM and Embedding services.
        """
        frontend_backend = super().stop(stop_gateway=False, stop_llm=False)  # Don't stop via parent
        gateway = True
        llm = True
        embedding = True

        if stop_gateway:
            gateway = self._stop_gateway()

        if stop_llm:
            llm = self._stop_llm_service(force=True)
            embedding = self._stop_embedding_service(force=True)
        else:
            # Inform user that infrastructure is preserved
            console.print("[dim]ℹ️  保留 LLM/Embedding 服务运行 (使用 --all 停止所有)[/dim]")

        return frontend_backend and gateway and llm and embedding

    def status(self):
        """Display status of all Studio Chat Mode services."""
        super().status()  # Show Studio status first

        # Local LLM Service status - check via HTTP instead of self.llm_service
        llm_table = Table(title="本地 LLM 服务状态（sageLLM）")
        llm_table.add_column("属性", style="cyan", width=14)
        llm_table.add_column("值", style="white")

        # Scan for running LLMs on ports 8901-8910
        found_llms = []
        for port in range(8901, 8911):
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/v1/models", timeout=0.5)
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    if models:
                        model_name = models[0].get("id", "unknown")
                        found_llms.append({"port": port, "model": model_name})
            except Exception:
                pass

        if found_llms:
            for i, llm in enumerate(found_llms):
                if i > 0:
                    llm_table.add_section()
                llm_table.add_row("状态", "[green]运行中[/green]")
                llm_table.add_row("端口", str(llm["port"]))
                llm_table.add_row("模型", llm["model"])
                if i == 0:
                    llm_table.add_row("说明", "由 UnifiedInferenceClient 自动检测使用")
        else:
            llm_table.add_row("状态", "[red]未运行[/red]")
            llm_table.add_row("端口", str(StudioPorts.BENCHMARK_LLM))
            llm_table.add_row("提示", "默认启动本地服务 (除非指定 --no-llm)")

        console.print(llm_table)

        # Embedding Service status
        embedding_table = Table(title="Embedding 服务状态")
        embedding_table.add_column("属性", style="cyan", width=14)
        embedding_table.add_column("值", style="white")

        embedding_port = StudioPorts.EMBEDDING_DEFAULT
        try:
            resp = requests.get(f"http://127.0.0.1:{embedding_port}/v1/models", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                model_name = models[0].get("id", "unknown") if models else "unknown"
                embedding_table.add_row("状态", "[green]运行中[/green]")
                embedding_table.add_row("端口", str(embedding_port))
                embedding_table.add_row("模型", model_name)
            else:
                embedding_table.add_row("状态", "[red]未运行[/red]")
                embedding_table.add_row("端口", str(embedding_port))
        except Exception:
            embedding_table.add_row("状态", "[red]未运行[/red]")
            embedding_table.add_row("端口", str(embedding_port))
            embedding_table.add_row("提示", "将随 LLM 服务自动启动")

        console.print(embedding_table)

        # Gateway status
        table = Table(title="sage-gateway 状态")
        table.add_column("属性", style="cyan", width=14)
        table.add_column("值", style="white")

        pid = self._is_gateway_running()
        if pid:
            table.add_row("状态", "[green]运行中[/green]")
            table.add_row("PID", str(pid))
            url = f"http://127.0.0.1:{self.gateway_port}/health"
            try:
                response = requests.get(url, timeout=1)
                status = response.json().get("status", "unknown")
                table.add_row("健康检查", status)
            except requests.RequestException:
                table.add_row("健康检查", "[red]不可达[/red]")
            table.add_row("端口", str(self.gateway_port))
            table.add_row("日志", str(self.gateway_log_file))
        else:
            table.add_row("状态", "[red]未运行[/red]")
            table.add_row("端口", str(self.gateway_port))
            table.add_row("日志", str(self.gateway_log_file))

        console.print(table)

    def logs(self, follow: bool = False, gateway: bool = False, backend: bool = False):
        """Display logs from Studio services.

        Args:
            follow: Follow log output (like tail -f)
            gateway: Show Gateway logs
            backend: Show Studio backend logs
        """
        if gateway:
            log_file = self.gateway_log_file
            name = "gateway"
        elif backend:
            log_file = self.backend_log_file
            name = "Studio Backend"
        else:
            log_file = self.log_file
            name = "Studio Frontend"

        if not log_file.exists():
            console.print(f"[yellow]{name} 日志不存在: {log_file}[/yellow]")
            return

        if follow:
            console.print(f"[blue]跟踪 {name} 日志 (Ctrl+C 退出)...[/blue]")
            try:
                subprocess.run(["tail", "-f", str(log_file)])
            except KeyboardInterrupt:
                console.print("\n[blue]停止日志跟踪[/blue]")
        else:
            console.print(f"[blue]显示 {name} 日志: {log_file}[/blue]")
            try:
                with open(log_file) as handle:
                    for line in handle.readlines()[-50:]:
                        print(line.rstrip())
            except OSError as exc:
                console.print(f"[red]读取日志失败: {exc}")
