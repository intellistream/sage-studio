"""
SAGE Studio 管理器 - 从 studio/cli.py 提取的业务逻辑
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil
import requests
from rich.console import Console
from rich.table import Table

from sage.studio.config.ports import StudioPorts
from sage.common.config.user_paths import get_user_paths

console = Console()


class StudioManager:
    """Studio 管理器"""

    def __init__(self):
        # application/studio_manager.py -> studio 模块目录
        self.studio_package_dir = Path(__file__).resolve().parent.parent
        self.project_root = self.studio_package_dir.parent.parent.parent
        self.frontend_dir = self.studio_package_dir / "frontend"
        self.backend_dir = self.studio_package_dir / "config" / "backend"

        # Use XDG paths via sage-common
        user_paths = get_user_paths()

        # State (PIDs, Logs)
        self.pid_file = user_paths.state_dir / "studio.pid"
        self.backend_pid_file = user_paths.state_dir / "studio_backend.pid"
        self.gateway_pid_file = user_paths.state_dir / "gateway.pid"

        self.log_file = user_paths.logs_dir / "studio.log"
        self.backend_log_file = user_paths.logs_dir / "studio_backend.log"
        self.gateway_log_file = user_paths.logs_dir / "gateway.log"

        # Config
        self.config_file = user_paths.config_dir / "studio.config.json"

        # Cache (Build artifacts)
        self.studio_cache_dir = user_paths.cache_dir / "studio"
        self.node_modules_dir = self.studio_cache_dir / "node_modules"
        self.vite_cache_dir = self.studio_cache_dir / ".vite"
        self.npm_cache_dir = self.studio_cache_dir / "npm"
        self.dist_dir = self.studio_cache_dir / "dist"

        # React + Vite 默认端口是 5173
        self.default_port = StudioPorts.FRONTEND
        # 支持环境变量覆盖后端端口（避免冲突）
        self.backend_port = int(os.environ.get("STUDIO_BACKEND_PORT", str(StudioPorts.BACKEND)))
        # Allow env override for gateway port; fallback logic handled in _start_gateway
        self.gateway_port = int(os.environ.get("SAGE_GATEWAY_PORT", str(StudioPorts.GATEWAY)))
        self.default_host = "0.0.0.0"  # 修改为监听所有网络接口

        # 确保所有目录存在
        self.ensure_sage_directories()

    def ensure_sage_directories(self):
        """确保所有 .sage 相关目录存在"""
        directories = [
            self.studio_cache_dir,
            self.vite_cache_dir,
            self.npm_cache_dir,
            self.dist_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _get_node_modules_root(self) -> Path | None:
        """Locate the effective node_modules directory."""

        if self.node_modules_dir.exists():
            return self.node_modules_dir

        fallback = self.frontend_dir / "node_modules"
        if fallback.exists():
            return fallback

        return None

    def load_config(self) -> dict:
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                # Self-heal: if backend_port is gateway port or old conflicting default 8080
                _bp = data.get("backend_port")
                if _bp == self.gateway_port or _bp == 8080:
                    data["backend_port"] = self.backend_port
                    self.save_config(data)
                return data
            except Exception:
                pass
        return {
            "port": self.default_port,
            "backend_port": self.backend_port,
            "host": self.default_host,
            "dev_mode": False,
        }

    def save_config(self, config: dict):
        """保存配置"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            console.print(f"[red]保存配置失败: {e}[/red]")

    def _get_listener_pid_on_port(self, port: int) -> int | None:
        """获取监听指定端口的进程 PID。"""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if not hasattr(conn, "laddr") or not conn.laddr:
                    continue
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN and conn.pid:
                    return conn.pid
        except Exception:
            return None
        return None

    def _is_frontend_process(self, pid: int) -> bool:
        """判断 PID 是否属于 Studio 前端进程。"""
        try:
            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline()).lower()
            name = proc.name().lower()
            cwd = ""
            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cwd = ""

            frontend_dir = str(self.frontend_dir)
            if cwd and Path(cwd) == self.frontend_dir:
                return True

            frontend_markers = (
                "npm run dev",
                "npm run preview",
                "vite",
                "spa_server.py",
            )
            if any(marker in cmdline for marker in frontend_markers):
                if "studio" in cmdline or (cwd and frontend_dir in cwd):
                    return True

            if name in {"npm", "node"} and (cwd and frontend_dir in cwd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        return False

    def _is_gateway_process(self, pid: int) -> bool:
        """判断 PID 是否属于 SAGE Gateway 进程。"""
        try:
            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline()).lower()
            return (
                "sagellm-gateway" in cmdline
                or "sagellm_gateway" in cmdline
                or "sage.llm.gateway" in cmdline
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def is_running(self) -> int | None:
        """检查 Studio 前端是否运行中

        Returns:
            int: 进程 PID
            -1: 服务在运行但无法确定 PID（外部启动）
            None: 服务未运行
        """
        # 方法1: 检查 PID 文件
        if self.pid_file.exists():
            try:
                with open(self.pid_file) as f:
                    pid = int(f.read().strip())

                if psutil.pid_exists(pid) and self._is_frontend_process(pid):
                    return pid
                else:
                    # PID 文件存在但进程不存在，清理文件
                    self.pid_file.unlink()
            except Exception:
                pass

        # 方法2: 通过端口检查（检测外部启动的服务）
        config = self.load_config()
        port = config.get("port", self.default_port)
        try:
            response = requests.get(
                f"http://localhost:{port}/",
                timeout=1,
                proxies={"http": None, "https": None},
            )
            # Vite dev server 或 preview server 会返回 HTML
            if response.status_code == 200:
                listener_pid = self._get_listener_pid_on_port(port)
                if listener_pid and self._is_frontend_process(listener_pid):
                    return listener_pid

                body = response.text[:2048].lower()
                if "<title>sage studio" in body:
                    return -1  # 运行中但无 PID 文件
        except Exception:
            pass

        return None

    def is_backend_running(self) -> int | None:
        """检查 Studio 后端API是否运行中

        Returns:
            int: 进程 PID
            -1: 服务在运行但无法确定 PID（外部启动）
            None: 服务未运行
        """
        # 方法1: 检查 PID 文件
        if self.backend_pid_file.exists():
            try:
                with open(self.backend_pid_file) as f:
                    pid = int(f.read().strip())

                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    # 检查是否是Python进程且包含新的 uvicorn app 入口
                    cmdline = " ".join(proc.cmdline())
                    if "python" in proc.name().lower() and (
                        "sage.studio.api.app:app" in cmdline
                        or "sage.studio.api.app" in cmdline
                        or ("uvicorn" in cmdline and "sage.studio.api" in cmdline)
                    ):
                        return pid

                # PID 文件存在但进程不存在，清理文件
                self.backend_pid_file.unlink()
            except Exception:
                pass

        # 方法2: 通过端口健康检查（检测外部启动的服务）
        config = self.load_config()
        backend_port = config.get("backend_port", self.backend_port)
        # Guard: skip if backend_port was accidentally saved as the gateway port
        if backend_port == self.gateway_port:
            return None
        try:
            response = requests.get(f"http://localhost:{backend_port}/health", timeout=1)
            if response.status_code == 200:
                # Verify this is the Studio backend, not the gateway or another service
                try:
                    data = response.json()
                    if data.get("service") == "sage-studio":
                        return -1  # 运行中但无 PID 文件
                except Exception:
                    pass
        except Exception:
            pass

        return None

    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return False  # 可以绑定，说明端口空闲
            except OSError:
                return True  # 无法绑定，说明端口被占用

    def _kill_process_on_port(self, port: int) -> bool:
        """杀死占用指定端口的进程"""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if hasattr(conn, "laddr") and conn.laddr and conn.laddr.port == port:
                    if conn.pid:
                        try:
                            proc = psutil.Process(conn.pid)
                            console.print(f"[dim]   杀死进程 {conn.pid} ({proc.name()})[/dim]")
                            proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            return True
        except Exception as e:
            console.print(f"[dim]   无法杀死端口 {port} 上的进程: {e}[/dim]")
            return False

    def is_gateway_running(self) -> int | None:
        """检查 Gateway 是否运行中

        Returns:
            int: 进程 PID
            -1: 服务在运行但无法确定 PID（外部启动）
            None: 服务未运行
        """
        # 方法1: 检查 Studio 自己的 PID 文件
        if self.gateway_pid_file.exists():
            try:
                with open(self.gateway_pid_file) as f:
                    pid = int(f.read().strip())

                if psutil.pid_exists(pid) and self._is_gateway_process(pid):
                    return pid

                # PID 文件存在但进程不存在，清理文件
                self.gateway_pid_file.unlink()
            except Exception:
                pass

        # 方法2: 通过端口检查（健康检查）
        try:
            response = requests.get(
                f"http://localhost:{self.gateway_port}/health",
                timeout=1,
                proxies={"http": None, "https": None}  # 禁用代理
            )
            if response.status_code == 200:
                # Gateway 在运行但没有 PID 文件，尝试找到进程
                listener_pid = self._get_listener_pid_on_port(self.gateway_port)
                if listener_pid and self._is_gateway_process(listener_pid):
                    return listener_pid

                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        cmdline = " ".join(proc.cmdline())
                        if "sagellm-gateway" in cmdline or "sagellm_gateway" in cmdline:
                            return proc.pid
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return -1  # 运行中但找不到 PID
        except Exception:
            pass

        return None

    def start_gateway(self, host: str | None = None, port: int | None = None) -> bool:
        """启动 Gateway 服务"""
        host = host or self.default_host
        port = port or self.gateway_port

        # 检查是否已经运行
        existing_pid = self.is_gateway_running()
        if existing_pid:
            if existing_pid == -1:
                console.print("[green]✅ Gateway 已在运行中（外部启动）[/green]")
            else:
                console.print(f"[green]✅ Gateway 已在运行中 (PID: {existing_pid})[/green]")
            return True

        # 并发启动保护：端口已占用时先短暂等待，避免误判 "Address already in use"
        if self._is_port_in_use(port):
            console.print(f"[yellow]⚠️  Gateway 端口 {port} 已被占用，正在确认是否已有实例启动...[/yellow]")
            for _ in range(10):
                time.sleep(0.5)
                existing_pid = self.is_gateway_running()
                if existing_pid:
                    if existing_pid == -1:
                        console.print("[green]✅ 检测到 Gateway 已由其他进程启动[/green]")
                    else:
                        console.print(f"[green]✅ 检测到 Gateway 已由其他进程启动 (PID: {existing_pid})[/green]")
                    return True

            console.print(
                f"[red]❌ 端口 {port} 被占用，但未探测到可用 Gateway 健康检查[/red]"
            )
            console.print("[yellow]   请检查占用进程或设置 SAGE_GATEWAY_PORT 后重试[/yellow]")
            return False

        console.print(f"[blue]🚀 启动 Gateway 服务 ({host}:{port})...[/blue]")

        try:
            # 使用 sagellm-gateway 命令（来自 isagellm-gateway 包）
            cmd = [
                "sagellm-gateway",
                "--host",
                host,
                "--port",
                str(port),
            ]

            # 后台启动
            with open(self.gateway_log_file, "w") as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # 保存 PID
            with open(self.gateway_pid_file, "w") as f:
                f.write(str(process.pid))

            # 等待服务启动（最多10秒）
            for _ in range(20):
                time.sleep(0.5)
                if self.is_gateway_running():
                    console.print(f"[green]✅ Gateway 启动成功 (PID: {process.pid})[/green]")
                    console.print(f"   日志: {self.gateway_log_file}")
                    return True

                # 并发场景：当前进程退出，但端口上已有其他 Gateway 实例
                if process.poll() is not None:
                    existing_pid = self.is_gateway_running()
                    if existing_pid:
                        console.print("[green]✅ Gateway 已由并发启动的其他进程成功接管[/green]")
                        return True
                    break

            console.print("[yellow]⚠️  Gateway 启动命令执行成功，但未能在10秒内探测到服务[/yellow]")
            console.print(f"   请检查日志: {self.gateway_log_file}")
            return False

        except Exception as e:
            console.print(f"[red]❌ Gateway 启动失败: {e}[/red]")
            return False

    def stop_gateway(self) -> bool:
        """停止 Gateway 服务"""
        pid = self.is_gateway_running()
        if not pid:
            return False

        if pid == -1:
            console.print("[yellow]⚠️  Gateway 在运行但无法确定 PID，请手动停止[/yellow]")
            return False

        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
            console.print(f"[green]✅ Gateway 已停止 (PID: {pid})[/green]")

            # 清理 PID 文件
            if self.gateway_pid_file.exists():
                self.gateway_pid_file.unlink()

            return True
        except psutil.TimeoutExpired:
            proc.kill()
            console.print(f"[yellow]⚠️  Gateway 强制停止 (PID: {pid})[/yellow]")
            if self.gateway_pid_file.exists():
                self.gateway_pid_file.unlink()
            return True
        except Exception as e:
            console.print(f"[red]❌ 停止 Gateway 失败: {e}[/red]")
            return False

    def is_llm_running(self) -> int | None:
        """检查 LLM 服务（Control Plane Gateway）是否运行中

        Returns:
            int: 进程 PID，如果未运行返回 None
        """
        # 方法1: 通过端口检查（探测 LLM Gateway）
        llm_ports = [8001, 8901]  # LLM_DEFAULT, BENCHMARK_LLM

        for port in llm_ports:
            try:
                response = requests.get(
                    f"http://localhost:{port}/v1/models",
                    timeout=1,
                    proxies={"http": None, "https": None}
                )
                if response.status_code == 200:
                    # Control Plane Gateway 可能尚未注册引擎，models 为空也视为运行中
                    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                        try:
                            cmdline = " ".join(proc.cmdline())
                            if (
                                "sage-llm gateway" in cmdline
                                or "sagellm_gateway" in cmdline
                                or "sagellm_gateway.server" in cmdline
                            ):
                                return proc.pid
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    return -1  # 运行中但找不到 PID
            except Exception:
                continue

        return None

    def start_llm_service(self, port: int = 8001) -> bool:
        """启动 LLM 推理服务（仅启动引擎，Gateway由start_gateway()单独启动）。

        Args:
            port: Gateway 端口（用于引擎注册）

        Returns:
            bool: 是否启动成功
        """
        # 直接启动默认引擎（Gateway已由start_gateway()启动）
        console.print(f"[blue]🚀 启动 LLM 引擎（将注册到 Gateway {port}）...[/blue]")
        return self._start_default_engine(port)

    def _select_model_by_memory(self, requested_model: str) -> str:
        """根据可用内存自动选择合适的模型。

        如果系统内存不足以运行请求的模型，自动降级到更小的模型。

        Args:
            requested_model: 用户请求的模型名称

        Returns:
            实际适合当前内存的模型名称
        """
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024**3)

        # 模型近似内存需求 (GB)
        model_requirements: dict[str, float] = {
            "Qwen/Qwen2.5-0.5B-Instruct": 2.0,
            "Qwen/Qwen2.5-1.5B-Instruct": 6.0,
            "Qwen/Qwen2.5-3B-Instruct": 10.0,
            "Qwen/Qwen2.5-7B-Instruct": 18.0,
        }

        required = model_requirements.get(requested_model, 6.0)

        if available_gb >= required:
            return requested_model

        console.print(
            f"[yellow]⚠️  内存不足 (可用: {available_gb:.1f}GB, 需要: {required:.1f}GB)[/yellow]"
        )

        # 按需求从小到大尝试
        for model, req in sorted(model_requirements.items(), key=lambda x: x[1]):
            if available_gb >= req:
                console.print(f"[yellow]→  自动选择更小的模型: {model}[/yellow]")
                return model

        console.print("[yellow]→  使用最小模型: Qwen/Qwen2.5-0.5B-Instruct[/yellow]")
        return "Qwen/Qwen2.5-0.5B-Instruct"

    def _start_default_engine(self, gateway_port: int = 8889) -> bool:
        """启动默认 LLM 引擎并注册到 Gateway Control Plane

        Args:
            gateway_port: Gateway 端口（用于注册）

        Returns:
            bool: 是否启动成功
        """
        # 从环境变量或使用默认模型，再根据内存自动降级
        requested_model = os.getenv("SAGE_DEFAULT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        default_model = self._select_model_by_memory(requested_model)

        if default_model != requested_model:
            console.print(f"[blue]ℹ️  原请求模型: {requested_model}[/blue]")

        console.print(f"[blue]🔧 启动默认 LLM 引擎: {default_model}...[/blue]")
        console.print("   (使用 sageLLM CPU Backend，轻量且高效)")
        
        try:
            # 使用 sage-llm serve-engine 命令启动引擎
            # 端口使用 9001，避免与 Gateway 冲突
            engine_port = 9001
            
            # 🔧 FIX: 检查端口是否被占用（防御性编程）
            if self._is_port_in_use(engine_port):
                console.print(f"[yellow]⚠️  端口 {engine_port} 已被占用，尝试停止旧引擎...[/yellow]")
                if not self._kill_process_on_port(engine_port):
                    console.print(f"[red]❌ 无法清理端口 {engine_port}[/red]")
                    return False
                # 等待端口释放
                time.sleep(2)
            
            # ✨ NEW: 使用 sageLLM Core API 直接启动 CPU backend
            engine_log = Path("/tmp/sage-studio-engine.log")
            console.print("   [dim]使用 sageLLM Core CPU backend...[/dim]")
            
            # 创建启动脚本（使用 sageLLM Core API）
            engine_script = self._create_sagellm_cpu_engine_script(default_model, engine_port, engine_log)
            
            # 后台启动引擎
            with open(engine_log, "w") as f:
                subprocess.Popen(
                    [sys.executable, str(engine_script)],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            
            # 等待引擎启动并注册到 Gateway
            # CPU 模型加载较慢（0.5B ~10s, 1.5B ~30s），给 120s
            max_wait = 120
            engine_id = f"studio-engine-{default_model.replace('/', '-')}"
            register_url = f"http://localhost:{gateway_port}/v1/management/engines/register"
            deregister_url = f"http://localhost:{gateway_port}/v1/management/engines/{engine_id}"

            console.print(f"   等待引擎就绪并注册到 Gateway (端口 {gateway_port})...")

            # 先清理旧的同名注册（避免 stale ERROR 状态干扰）
            try:
                requests.delete(deregister_url, timeout=2, proxies={"http": None, "https": None})
            except Exception:
                pass

            engine_healthy = False
            for i in range(max_wait):
                time.sleep(1)

                # 每 3 秒检查一次引擎健康
                if (i + 1) % 3 != 0:
                    continue

                try:
                    engine_health = requests.get(
                        f"http://localhost:{engine_port}/health",
                        timeout=2,
                        proxies={"http": None, "https": None},
                    )
                    if engine_health.status_code != 200:
                        if (i + 1) % 15 == 0:
                            console.print(f"[yellow]   引擎加载中... ({i + 1}s)[/yellow]")
                        continue
                except requests.ConnectionError:
                    if (i + 1) % 15 == 0:
                        console.print(f"[yellow]   引擎加载中... ({i + 1}s)[/yellow]")
                    continue
                except Exception:
                    continue

                # 引擎就绪，尝试注册到 Gateway
                if not engine_healthy:
                    console.print(f"   [green]✓[/green] 引擎就绪 (耗时 {i + 1}s)")
                    engine_healthy = True

                register_payload = {
                    "engine_id": engine_id,
                    "model_id": default_model,
                    "host": "localhost",
                    "port": engine_port,
                    "engine_kind": "llm",
                    "metadata": {"source": "studio_startup", "model": default_model},
                }

                try:
                    register_response = requests.post(
                        register_url,
                        json=register_payload,
                        timeout=5,
                        proxies={"http": None, "https": None},
                    )
                    if register_response.status_code in [200, 201]:
                        console.print(f"[green]✅ 引擎已注册到 Gateway: {engine_id}[/green]")
                        console.print(f"   引擎端口: {engine_port}, Gateway端口: {gateway_port}")
                        return True
                    else:
                        console.print(
                            f"[yellow]   注册响应: {register_response.status_code} - "
                            f"{register_response.text[:100]}[/yellow]"
                        )
                except Exception as e:
                    console.print(f"[yellow]   注册请求失败: {e}[/yellow]")

            # 超时处理：引擎已就绪但注册失败 → 仍算部分成功
            if engine_healthy:
                console.print("[yellow]⚠️  引擎已就绪但 Gateway 注册失败[/yellow]")
                console.print(f"   引擎仍可在 http://localhost:{engine_port} 使用")
                return True

            console.print("[yellow]⚠️  引擎启动超时，可能仍在后台加载[/yellow]")
            console.print(f"   请检查日志: {engine_log}")
            return False
            
        except Exception as e:
            console.print(f"[red]❌ 启动默认引擎失败: {e}[/red]")
            console.print("[yellow]💡 您可以手动启动引擎:[/yellow]")
            console.print(f"   python -c 'from sagellm_core import LLMEngine, LLMEngineConfig; ...'")
            return False

    def _create_sagellm_cpu_engine_script(self, model: str, port: int, log_file: Path) -> Path:
        """创建 sageLLM CPU engine 启动脚本
        
        Args:
            model: 模型路径
            port: 服务端口
            log_file: 日志文件路径
            
        Returns:
            脚本文件路径
        """
        user_paths = get_user_paths()
        script_path = user_paths.cache_dir / "studio" / "start_cpu_engine.py"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成启动脚本（基于用户验证的 test_qwen_1_5b_cpu.py + FastAPI 服务器）
        script_content = f'''#!/usr/bin/env python3
"""sageLLM CPU Engine for SAGE Studio - HTTP Server

Auto-generated script to start CPU-based LLM engine with OpenAI-compatible API.
"""
import asyncio
import sys
from pathlib import Path
from typing import List, Optional, Any

try:
    from sagellm_protocol.types import Request as SageLLMRequest
    from sagellm_core import LLMEngine, LLMEngineConfig
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    print(f"Error: Missing dependencies: {{e}}", file=sys.stderr)
    print("Install: pip install sagellm-core sagellm-protocol fastapi uvicorn", file=sys.stderr)
    sys.exit(1)


# OpenAI-compatible API models
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False

class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage


# Global engine instance
engine: Optional[LLMEngine] = None
model_name = "{model}"


async def initialize_engine():
    """Initialize the LLM engine."""
    global engine
    
    print(f"🚀 Starting sageLLM CPU Engine...")
    print(f"   Model: {{model_name}}")
    print(f"   Backend: CPU")
    
    try:
        config = LLMEngineConfig(
            model_path=model_name,
            backend_type="cpu",
            max_new_tokens=512,
            dtype="bfloat16",
            trust_remote_code=True,
        )
        
        engine = LLMEngine(config)
        await engine.start()
        
        print(f"✅ Engine initialized successfully")
        
    except Exception as e:
        print(f"❌ Engine initialization failed: {{e}}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


# FastAPI app
app = FastAPI(title="sageLLM CPU Engine", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    await initialize_engine()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {{"status": "ok", "model": model_name, "backend": "cpu"}}


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    return {{
        "object": "list",
        "data": [
            {{
                "id": model_name,
                "object": "model",
                "owned_by": "sage-studio",
                "permission": []
            }}
        ]
    }}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Chat completions endpoint (OpenAI-compatible) with streaming support."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        import time as time_module
        import uuid
        import json
        from fastapi.responses import StreamingResponse
        from sagellm_protocol.types import ChatMessage as SageChatMessage
        
        request_id = f"chatcmpl-{{int(time_module.time())}}"
        
        # Reduce max_tokens for faster response on CPU
        max_tokens = min(request.max_tokens or 50, 50)
        
        # Convert to sagellm ChatMessage list — engine handles chat template
        sage_messages = [
            SageChatMessage(role=msg.role, content=msg.content)
            for msg in request.messages
        ]
        
        # Streaming response
        if request.stream:
            async def generate_stream():
                llm_request = SageLLMRequest(
                    request_id=str(uuid.uuid4()),
                    trace_id=str(uuid.uuid4()),
                    model=model_name,
                    messages=sage_messages,
                    max_tokens=max_tokens,
                    temperature=request.temperature or 0.7,
                    stream=True,
                )
                
                try:
                    async for chunk in engine.stream(llm_request):
                        # StreamEventDelta and StreamEventEnd both have .content
                        # Only yield delta events (event="delta"), skip end to avoid duplication
                        text = getattr(chunk, 'content', None) if getattr(chunk, 'event', None) == 'delta' else None
                        if text:
                            chunk_data = {{
                                "id": request_id,
                                "object": "chat.completion.chunk",
                                "created": int(time_module.time()),
                                "model": model_name,
                                "choices": [{{
                                    "index": 0,
                                    "delta": {{"content": text}},
                                    "finish_reason": None
                                }}]
                            }}
                            yield f"data: {{json.dumps(chunk_data)}}\\n\\n"
                    
                    # Send final chunk
                    final_chunk = {{
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time_module.time()),
                        "model": model_name,
                        "choices": [{{
                            "index": 0,
                            "delta": {{}},
                            "finish_reason": "stop"
                        }}]
                    }}
                    yield f"data: {{json.dumps(final_chunk)}}\\n\\n"
                    yield "data: [DONE]\\n\\n"
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    error_data = {{"error": str(e)}}
                    yield f"data: {{json.dumps(error_data)}}\\n\\n"
            
            return StreamingResponse(generate_stream(), media_type="text/event-stream")
        
        # Non-streaming response
        llm_request = SageLLMRequest(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            model=model_name,
            messages=sage_messages,
            max_tokens=max_tokens,
            temperature=request.temperature or 0.7,
            stream=False,
        )
        
        response = await engine.execute(llm_request)
        output_text = response.output_text
        
        # Format OpenAI-compatible response
        return ChatCompletionResponse(
            id=request_id,
            created=int(time_module.time()),
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=output_text.strip()),
                    finish_reason="stop"
                )
            ],
            usage=Usage(
                prompt_tokens=len(output_text.split()),
                completion_tokens=len(output_text.split()),
                total_tokens=len(output_text.split()) * 2
            )
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = {port}
    print(f"   Starting HTTP server on http://0.0.0.0:{{port}}")
    print(f"   Press Ctrl+C to stop")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
'''
        
        with open(script_path, "w") as f:
            f.write(script_content)
        
        script_path.chmod(0o755)
        return script_path

    def stop_llm_service(self) -> bool:
        """停止 LLM 服务"""
        pid = self.is_llm_running()
        if not pid:
            console.print("[yellow]LLM 服务未运行[/yellow]")
            return False

        if pid == -1:
            console.print("[yellow]⚠️  LLM 服务在运行但无法确定 PID，请手动停止[/yellow]")
            return False

        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=10)
            console.print(f"[green]✅ LLM 服务已停止 (PID: {pid})[/green]")
            return True
        except psutil.TimeoutExpired:
            proc.kill()
            console.print(f"[yellow]⚠️  LLM 服务强制停止 (PID: {pid})[/yellow]")
            return True
        except Exception as e:
            console.print(f"[red]❌ 停止 LLM 服务失败: {e}[/red]")
            return False

    def check_dependencies(self) -> bool:
        """检查依赖"""
        MIN_NODE_VERSION = 20  # Vite 7.x 需要 Node.js 20.19+，推荐 22+

        # 检查 Node.js
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                node_version = result.stdout.strip()
                # 解析版本号（例如 v12.22.9 -> 12）
                version_str = node_version.lstrip("v").split(".")[0]
                try:
                    major_version = int(version_str)
                except ValueError:
                    major_version = 0

                if major_version < MIN_NODE_VERSION:
                    console.print(
                        f"[red]Node.js 版本过低: {node_version}（需要 v{MIN_NODE_VERSION}+）[/red]"
                    )
                    console.print("[yellow]💡 请升级 Node.js:[/yellow]")
                    console.print("   conda install -y nodejs=22 -c conda-forge")
                    console.print("   # 或通过 nvm 安装: nvm install 22 && nvm use 22")
                    return False
                console.print(f"[green]Node.js: {node_version}[/green]")
            else:
                console.print("[red]Node.js 未找到[/red]")
                console.print("[yellow]💡 安装方法:[/yellow]")
                console.print("   conda install -y nodejs=20 -c conda-forge")
                console.print("   # 或 apt install nodejs npm")
                return False
        except FileNotFoundError:
            console.print("[red]Node.js 未安装[/red]")
            console.print("[yellow]💡 安装方法:[/yellow]")
            console.print("   conda install -y nodejs=20 -c conda-forge")
            console.print("   # 或 apt install nodejs npm")
            return False

        # 检查 npm
        try:
            result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                npm_version = result.stdout.strip()
                console.print(f"[green]npm: {npm_version}[/green]")
            else:
                console.print("[red]npm 未找到[/red]")
                console.print("[yellow]💡 npm 通常随 Node.js 一起安装[/yellow]")
                return False
        except (FileNotFoundError, subprocess.CalledProcessError):
            console.print("[red]npm 未安装[/red]")
            console.print("[yellow]💡 npm 通常随 Node.js 一起安装[/yellow]")
            return False

        return True

    def clean_scattered_files(self) -> bool:
        """清理散乱的临时文件和缓存"""
        console.print("[blue]清理散乱的临时文件...[/blue]")

        # 清理项目目录中的临时文件（React + Vite）
        cleanup_patterns = [
            self.studio_package_dir / ".vite",
            self.studio_package_dir / "dist",
            self.frontend_dir / ".vite",
            self.frontend_dir / "dist",
            self.frontend_dir / "node_modules/.vite",  # Vite 缓存
        ]

        cleaned = False
        for pattern in cleanup_patterns:
            if pattern.exists():
                import shutil

                if pattern.is_dir():
                    shutil.rmtree(pattern)
                    console.print(f"[green]✓ 已清理: {pattern}[/green]")
                    cleaned = True
                elif pattern.is_file():
                    pattern.unlink()
                    console.print(f"[green]✓ 已清理: {pattern}[/green]")
                    cleaned = True

        if not cleaned:
            console.print("[green]✓ 无需清理散乱文件[/green]")

        return True

    def ensure_node_modules_link(self) -> bool:
        """确保 node_modules 符号链接正确设置"""
        project_modules = self.frontend_dir / "node_modules"

        # 如果项目目录中有实际的 node_modules，删除它
        if project_modules.exists() and not project_modules.is_symlink():
            console.print("[blue]清理项目目录中的 node_modules...[/blue]")
            import shutil

            shutil.rmtree(project_modules)

        # 如果已经是符号链接，检查是否指向正确位置
        if project_modules.is_symlink():
            if project_modules.resolve() == self.node_modules_dir:
                console.print("[green]✓ node_modules 符号链接已正确设置[/green]")
                return True
            else:
                console.print("[blue]更新 node_modules 符号链接...[/blue]")
                project_modules.unlink()

        # 创建符号链接
        if self.node_modules_dir.exists():
            project_modules.symlink_to(self.node_modules_dir)
            console.print("[green]✓ 已创建 node_modules 符号链接[/green]")
            return True
        else:
            console.print("[yellow]警告: 目标 node_modules 不存在[/yellow]")
            return False

    def _ensure_frontend_dependency_integrity(
        self, auto_fix: bool = True, skip_confirm: bool = False
    ) -> bool:
        """Detect and optionally repair broken critical frontend dependencies."""

        modules_root = self._get_node_modules_root()
        if modules_root is None:
            return True  # Nothing to check yet

        critical_packages = [
            {
                "name": "lines-and-columns",
                "version": "1.2.4",
                "required": ["build", "build/index.js"],
                "reason": "PostCSS SourceMap helper (Vite dev server)",
            },
            {
                "name": "typescript",
                "version": "^5.2.2",
                "required": ["bin/tsc"],
                "reason": "TypeScript compiler for build",
            },
            {
                "name": "vite",
                "version": "^5.0.8",
                "required": ["bin/vite.js", "dist/node/cli.js"],
                "reason": "Vite build tool",
            },
        ]

        broken: list[tuple[dict, list[str]]] = []

        for pkg in critical_packages:
            pkg_dir = modules_root / pkg["name"]
            missing: list[str] = []

            if not pkg_dir.exists():
                missing.append("package directory")
            else:
                for rel_path in pkg["required"]:
                    if not (pkg_dir / rel_path).exists():
                        missing.append(rel_path)

            if missing:
                broken.append((pkg, missing))

        if not broken:
            return True

        console.print("[yellow]⚠️  检测到前端依赖缺少关键文件，Vite 可能无法启动[/yellow]")
        for pkg, missing in broken:
            missing_display = ", ".join(missing)
            console.print(
                f"   • {pkg['name']}: 缺少 {missing_display} ({pkg.get('reason', '必需文件')})"
            )

        if not auto_fix:
            console.print(
                "[yellow]自动修复已禁用，请运行 'sage studio install' 或在"
                f" {self.frontend_dir} 执行: npm cache clean --force && "
                "npm install --no-save <package>@<version>[/yellow]"
            )
            return False

        for pkg, _missing in broken:
            if not self._repair_node_package(pkg):
                return False

        return self._ensure_frontend_dependency_integrity(auto_fix=False)

    def _repair_node_package(self, package_meta: dict) -> bool:
        """Attempt to self-heal a corrupted npm package installation."""

        package_name = package_meta["name"]
        version = package_meta.get("version")
        spec = f"{package_name}@{version}" if version else package_name

        modules_root = self._get_node_modules_root()
        if modules_root is None:
            console.print("[red]node_modules 尚未安装，无法修复依赖[/red]")
            return False

        console.print(f"[blue]🧹 修复前端依赖 {spec}...[/blue]")

        targets = {
            modules_root / package_name,
            (self.frontend_dir / "node_modules") / package_name,
        }

        for target in targets:
            if target.exists() or target.is_symlink():
                try:
                    if target.is_symlink() or target.is_file():
                        target.unlink()
                    else:
                        shutil.rmtree(target)
                    console.print(f"   [green]✓[/green] 已清理 {target}")
                except Exception as exc:  # pragma: no cover - best effort cleanup
                    console.print(f"[red]清理 {target} 失败: {exc}[/red]")
                    return False

        env = os.environ.copy()
        env["npm_config_cache"] = str(self.npm_cache_dir)

        def run_npm(args: list[str], label: str) -> bool:
            try:
                subprocess.run(
                    ["npm", *args],
                    cwd=self.frontend_dir,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return True
            except subprocess.CalledProcessError as exc:  # pragma: no cover - runtime failure
                console.print(f"[red]npm {label} 失败 (exit {exc.returncode})[/red]")
                if exc.stdout:
                    console.print(exc.stdout.strip())
                if exc.stderr:
                    console.print(exc.stderr.strip())
                return False

        console.print("   [blue]刷新 npm 缓存...[/blue]")
        if not run_npm(["cache", "clean", "--force"], "cache clean"):
            return False

        console.print("   [blue]重新安装依赖文件...[/blue]")
        install_args = ["install", "--no-save", spec]
        if not run_npm(install_args, f"install {spec}"):
            return False

        # 仅在 .sage/studio/node_modules 已存在时尝试创建符号链接，
        # 避免误删项目目录中的实际依赖目录
        if self.node_modules_dir.exists():
            self.ensure_node_modules_link()
        console.print(f"[green]✅ {spec} 修复完成[/green]")
        return True

    def install_dependencies(
        self,
        command: str = "install",
        extra_args: list[str] | None = None,
    ) -> bool:
        """安装依赖"""
        if not self.frontend_dir.exists():
            console.print(f"[red]前端目录不存在: {self.frontend_dir}[/red]")
            return False

        package_json = self.frontend_dir / "package.json"
        if not package_json.exists():
            console.print(f"[red]package.json 不存在: {package_json}[/red]")
            return False

        console.print(f"[blue]正在执行 npm {command} ...[/blue]")

        try:
            # 设置 npm 缓存目录
            env = os.environ.copy()
            env["npm_config_cache"] = str(self.npm_cache_dir)

            # 安装依赖到项目目录
            cmd = ["npm", command]
            if extra_args:
                cmd.extend(extra_args)

            subprocess.run(
                cmd,
                cwd=self.frontend_dir,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            # 处理 node_modules 的位置
            project_modules = self.frontend_dir / "node_modules"

            if project_modules.exists():
                console.print("[blue]移动 node_modules 到 .sage 目录...[/blue]")

                # 如果目标目录已存在，先删除
                if self.node_modules_dir.exists():
                    import shutil

                    shutil.rmtree(self.node_modules_dir)

                # 移动 node_modules
                project_modules.rename(self.node_modules_dir)
                console.print("[green]node_modules 已移动到 .sage/studio/[/green]")

            # 无论如何都要创建符号链接（如果不存在的话）
            if not project_modules.exists():
                if self.node_modules_dir.exists():
                    project_modules.symlink_to(self.node_modules_dir)
                    console.print("[green]已创建 node_modules 符号链接[/green]")
                else:
                    console.print(
                        "[yellow]警告: 目标 node_modules 不存在，无法创建符号链接[/yellow]"
                    )

            console.print("[green]依赖安装成功[/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]依赖安装失败: {e}[/red]")
            if e.stdout:
                console.print(f"stdout: {e.stdout}")
            if e.stderr:
                console.print(f"stderr: {e.stderr}")
            return False

    def install(self) -> bool:
        """安装 Studio 依赖（React + Vite）"""
        console.print("[blue]📦 安装 SAGE Studio 依赖...[/blue]")

        # 清理散乱的临时文件
        self.clean_scattered_files()

        # 检查基础依赖
        if not self.check_dependencies():
            console.print("[red]❌ 依赖检查失败[/red]")
            return False

        # 安装所有依赖
        if not self.install_dependencies():
            console.print("[red]❌ 依赖安装失败[/red]")
            return False

        if not self._ensure_frontend_dependency_integrity(auto_fix=True):
            console.print("[red]❌ 依赖完整性检查失败[/red]")
            return False

        # 检查 TypeScript 编译
        self.check_typescript_compilation()

        # 确保 node_modules 符号链接正确
        self.ensure_node_modules_link()

        console.print("[green]✅ Studio 安装完成[/green]")
        return True

    def run_npm_command(self, npm_args: list[str]) -> bool:
        """在 Studio 前端目录中运行任意 npm 命令。"""
        if not npm_args:
            console.print("[red]请提供要执行的 npm 子命令，例如: install[/red]")
            return False

        if not self.frontend_dir.exists():
            console.print(f"[red]前端目录不存在: {self.frontend_dir}[/red]")
            return False

        if not self.check_dependencies():
            console.print("[red]依赖检查失败，无法执行 npm 命令[/red]")
            return False

        command = npm_args[0]
        extra_args = npm_args[1:]

        if command in {"install", "ci"}:
            return self.install_dependencies(command=command, extra_args=extra_args)

        env = os.environ.copy()
        env["npm_config_cache"] = str(self.npm_cache_dir)

        console.print(f"[blue]运行 npm {' '.join(npm_args)}... 按 Ctrl+C 可中断[/blue]")
        try:
            subprocess.run(
                ["npm", *npm_args],
                cwd=self.frontend_dir,
                env=env,
                check=True,
            )
            console.print("[green]npm 命令执行完成[/green]")
            return True
        except subprocess.CalledProcessError as exc:
            console.print(f"[red]npm 命令失败 (退出码 {exc.returncode})[/red]")
            return False
        except KeyboardInterrupt:
            console.print("[yellow]npm 命令已被用户中断[/yellow]")
            return False

    def setup_vite_config(self) -> bool:
        """设置 Vite 配置（如果需要）"""
        console.print("[blue]检查 Vite 配置...[/blue]")

        try:
            vite_config_path = self.frontend_dir / "vite.config.ts"

            if not vite_config_path.exists():
                console.print("[yellow]vite.config.ts 不存在，使用默认配置[/yellow]")
                return True

            console.print("[green]✓ Vite 配置已就绪[/green]")
            return True

        except Exception as e:
            console.print(f"[red]配置检查失败: {e}[/red]")
            return False

    def check_typescript_compilation(self) -> bool:
        """检查 TypeScript 编译是否正常"""
        console.print("[blue]检查 TypeScript 编译...[/blue]")

        try:
            # 运行 TypeScript 编译检查
            result = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                cwd=self.frontend_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                console.print("[green]✓ TypeScript 编译检查通过[/green]")
                return True
            else:
                console.print("[yellow]⚠️ TypeScript 编译警告/错误:[/yellow]")
                if result.stdout:
                    console.print(result.stdout)
                if result.stderr:
                    console.print(result.stderr)
                # 编译错误不阻止安装，只是警告
                return True

        except Exception as e:
            console.print(f"[yellow]TypeScript 检查跳过: {e}[/yellow]")
            return True

    def create_spa_server_script(self, port: int, host: str) -> Path:
        """创建用于 SPA 的自定义服务器脚本"""
        server_script = self.studio_cache_dir / "spa_server.py"

        server_code = f'''#!/usr/bin/env python3
"""
SAGE Studio SPA 服务器
支持 React 单页应用的路由重定向
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """支持 SPA 路由的 HTTP 处理器"""

    def __init__(self, *args, directory=None, **kwargs):
        self.directory = directory
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """处理 GET 请求，支持 SPA 路由回退"""
        # 获取请求的文件路径
        file_path = Path(self.directory) / self.path.lstrip('/')

        # 如果是文件且存在，直接返回
        if file_path.is_file():
            super().do_GET()
            return

        # 如果是目录且包含 index.html，返回 index.html
        if file_path.is_dir():
            index_file = file_path / "index.html"
            if index_file.exists():
                self.path = str(index_file.relative_to(Path(self.directory)))
                super().do_GET()
                return

        # 对于 SPA 路由（不存在的路径），返回根目录的 index.html
        root_index = Path(self.directory) / "index.html"
        if root_index.exists():
            self.path = "/index.html"
            super().do_GET()
        else:
            # 如果连 index.html 都不存在，返回 404
            self.send_error(404, "File not found")

    def end_headers(self):
        """添加 CORS 头"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

def main():
    PORT = {port}
    HOST = "{host}"
    DIRECTORY = "{str(self.dist_dir)}"

    print(f"启动 SAGE Studio SPA 服务器...")
    print(f"地址: http://{{HOST}}:{{PORT}}")
    print(f"目录: {{DIRECTORY}}")
    print("按 Ctrl+C 停止服务器")

    # 更改工作目录
    os.chdir(DIRECTORY)

    # 创建处理器，传入目录参数
    handler = lambda *args, **kwargs: SPAHandler(*args, directory=DIRECTORY, **kwargs)

    try:
        with socketserver.TCPServer((HOST, PORT), handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\n服务器已停止")
    except Exception as e:
        print(f"服务器错误: {{e}}")
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

        # 写入服务器脚本
        with open(server_script, "w") as f:
            f.write(server_code)

        # 设置执行权限
        server_script.chmod(0o755)

        console.print(f"[blue]已创建自定义 SPA 服务器: {server_script}[/blue]")
        return server_script

    def build(self) -> bool:
        """构建 Studio"""
        if not self.frontend_dir.exists():
            console.print(f"[red]前端目录不存在: {self.frontend_dir}[/red]")
            return False

        package_json = self.frontend_dir / "package.json"
        if not package_json.exists():
            console.print(f"[red]package.json 不存在: {package_json}[/red]")
            return False

        console.print("[blue]正在构建 Studio...[/blue]")

        try:
            # 设置构建环境变量
            env = os.environ.copy()
            env["npm_config_cache"] = str(self.npm_cache_dir)

            # 运行构建命令，使用 .sage 目录作为输出
            result = subprocess.run(
                ["npm", "run", "build", "--", f"--outDir={self.dist_dir}"],
                cwd=self.frontend_dir,
                capture_output=True,
                text=True,
                env=env,
            )

            if result.returncode == 0:
                console.print("[green]Studio 构建成功[/green]")

                # 检查构建输出
                if self.dist_dir.exists():
                    console.print(f"[blue]构建输出位置: {self.dist_dir}[/blue]")
                else:
                    console.print(f"[yellow]警告: 构建输出目录不存在: {self.dist_dir}[/yellow]")

                return True
            else:
                console.print("[red]Studio 构建失败[/red]")
                if result.stdout:
                    console.print("构建输出:")
                    console.print(result.stdout)
                if result.stderr:
                    console.print("错误信息:")
                    console.print(result.stderr)
                return False

        except Exception as e:
            console.print(f"[red]构建过程出错: {e}[/red]")
            return False

    def _print_backend_log_tail(self, lines: int = 20, prefix: str = "") -> None:
        """输出后端日志的最后几行"""
        try:
            if self.backend_log_file.exists():
                with open(self.backend_log_file, encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                    tail_lines = all_lines[-lines:] if len(all_lines) >= lines else all_lines
                    if tail_lines:
                        console.print(
                            f"[dim]{prefix}--- 后端日志 (最后 {len(tail_lines)} 行) ---[/dim]"
                        )
                        for line in tail_lines:
                            console.print(f"[dim]{prefix}{line.rstrip()}[/dim]")
                        console.print(f"[dim]{prefix}--- 日志结束 ---[/dim]")
        except Exception as e:
            console.print(f"[dim]{prefix}读取日志失败: {e}[/dim]")

    def _print_backend_log_incremental(self, last_pos: int = 0) -> int:
        """增量输出后端日志（从上次位置开始的新内容）

        Returns:
            当前日志文件位置，用于下次调用
        """
        try:
            if not self.backend_log_file.exists():
                return 0

            with open(self.backend_log_file, encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                new_content = f.read()
                current_pos = f.tell()

                if new_content.strip():
                    # 输出新增内容，每行添加前缀
                    for line in new_content.splitlines():
                        if line.strip():
                            console.print(f"[dim]   [后端] {line}[/dim]")

                return current_pos
        except Exception as e:
            console.print(f"[dim]   读取后端日志失败: {e}[/dim]")
            return last_pos

    def start_backend(self, port: int | None = None) -> bool:
        """启动后端API服务"""
        # 检查是否已运行
        running_pid = self.is_backend_running()
        if running_pid:
            if running_pid == -1:
                console.print("[green]✅ 检测到后端API已在运行（外部启动），直接复用[/green]")
            else:
                console.print(f"[yellow]后端API已经在运行 (PID: {running_pid})[/yellow]")
            return True

        # 配置参数
        config = self.load_config()
        backend_port = port or config.get("backend_port", self.backend_port)

        # 🆕 智能端口选择：如果默认端口被占用，自动尝试其他端口
        # Exclude gateway port to prevent accidentally binding on it
        _gateway_port = self.gateway_port
        _candidates = [backend_port, StudioPorts.BACKEND, 8765, 8766, 8081, 8082, 8083]
        alternative_ports = [p for p in _candidates if p != _gateway_port]
        selected_port = None
        
        for try_port in alternative_ports:
            if not self._is_port_in_use(try_port):
                selected_port = try_port
                if try_port != backend_port:
                    console.print(f"[yellow]端口 {backend_port} 被占用，自动切换到端口 {try_port}[/yellow]")
                break
        
        if selected_port is None:
            console.print(f"[red]❌ 无法找到可用端口（尝试了: {alternative_ports}）[/red]")
            console.print("[yellow]💡 提示：可以设置环境变量 STUDIO_BACKEND_PORT 指定端口[/yellow]")
            return False
        
        backend_port = selected_port

        # 更新配置
        config["backend_port"] = backend_port
        self.save_config(config)

        console.print(f"[blue]正在启动后端API (端口: {backend_port})...[/blue]")

        try:
            # 启动后端进程
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "sage.studio.api.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(backend_port),
                "--log-level",
                "info",
            ]
            log_handle = open(self.backend_log_file, "w")
            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,  # 阻止子进程读取 stdin
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            # 注意：不关闭 log_handle，让子进程继承并管理它

            # 保存 PID
            with open(self.backend_pid_file, "w") as f:
                f.write(str(process.pid))

            # 等待后端启动
            console.print("[blue]等待后端API启动...[/blue]")
            startup_success = False

            # 创建一个不使用代理的 session（本地服务不需要代理）
            session = requests.Session()
            session.trust_env = False  # 忽略环境变量中的代理设置

            # CI 环境首次启动可能较慢，增加等待时间
            # 设置较长的超时时间，确保服务有足够时间启动
            max_wait = 120  # 最多等待120秒（2分钟）
            last_log_pos = 0  # 记录上次读取日志的位置

            for i in range(max_wait):
                # 首先检查进程是否还存在
                if not psutil.pid_exists(process.pid):
                    console.print("[red]❌ 后端API进程已退出[/red]")
                    # 输出完整日志帮助调试
                    self._print_backend_log_tail(20, prefix="[后端日志] ")
                    return False

                try:
                    # 使用 localhost 而不是 0.0.0.0，避免代理问题
                    health_url = f"http://localhost:{backend_port}/health"
                    response = session.get(health_url, timeout=2)
                    if response.status_code == 200:
                        startup_success = True
                        console.print(f"[green]✅ 后端API启动成功 (耗时 {i + 1} 秒)[/green]")
                        break
                except requests.RequestException:
                    pass

                # 每 5 秒输出一次等待状态和新增的日志
                if (i + 1) % 5 == 0:
                    console.print(f"[blue]   等待后端响应... ({i + 1}/{max_wait}秒)[/blue]")
                    # 实时输出后端日志的新增内容
                    last_log_pos = self._print_backend_log_incremental(last_log_pos)

                time.sleep(1)

            if not startup_success:
                # 最后再检查一次健康状态
                try:
                    response = session.get(f"http://localhost:{backend_port}/health", timeout=5)
                    if response.status_code == 200:
                        console.print("[green]✅ 后端API启动成功[/green]")
                        return True
                except requests.RequestException:
                    pass

                # 检查端口是否在监听（更可靠的检查方式）
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                port_open = sock.connect_ex(("localhost", backend_port)) == 0
                sock.close()

                if port_open:
                    console.print("[yellow]⚠️ 后端API端口已监听，但健康检查未响应[/yellow]")
                    console.print(
                        f"[yellow]   服务可能仍在初始化，请访问 http://localhost:{backend_port}/health 检查[/yellow]"
                    )
                    return True  # 端口已监听，认为启动成功
                elif psutil.pid_exists(process.pid):
                    console.print("[yellow]⚠️ 后端API进程存在但端口未监听[/yellow]")
                    console.print("[yellow]   进程可能启动失败，请检查日志[/yellow]")
                    # 输出后端日志帮助调试
                    console.print("[yellow]   === 后端日志（最后50行）===[/yellow]")
                    self._print_backend_log_tail(lines=50, prefix="   ")
                    return False  # 进程存在但端口未监听，认为启动失败
                else:
                    console.print("[red]❌ 后端API进程已退出[/red]")
                    # 输出后端日志帮助调试
                    console.print("[red]   === 后端日志（最后50行）===[/red]")
                    self._print_backend_log_tail(lines=50, prefix="   ")
                    return False
            return True

        except Exception as e:
            console.print(f"[red]后端API启动失败: {e}[/red]")
            return False

    def stop_backend(self) -> bool:
        """停止后端API服务"""
        running_pid = self.is_backend_running()
        if not running_pid:
            console.print("[yellow]后端API未运行[/yellow]")
            return True

        # When no PID is available (externally launched), fall back to port kill.
        if running_pid == -1:
            _cfg = self.load_config()
            _port = _cfg.get("backend_port", self.backend_port)
            result = self._kill_process_on_port(_port)
            if self.backend_pid_file.exists():
                self.backend_pid_file.unlink()
            if result:
                console.print("[green]✅ 后端API已停止[/green]")
            return result

        try:
            # 优雅停止
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(running_pid)], check=True)
            else:
                os.killpg(os.getpgid(running_pid), signal.SIGTERM)

                # 等待进程结束（增加等待时间和更详细的检查）
                console.print("[blue]等待后端API进程停止...[/blue]")
                max_wait = 15  # 增加到15秒
                for i in range(max_wait):
                    if not psutil.pid_exists(running_pid):
                        console.print(f"[green]后端API进程已停止 (等待 {i}秒)[/green]")
                        break
                    time.sleep(1)
                else:
                    # 超时后强制停止
                    console.print("[yellow]进程未在预期时间内停止，强制终止...[/yellow]")
                    if psutil.pid_exists(running_pid):
                        os.killpg(os.getpgid(running_pid), signal.SIGKILL)
                        time.sleep(1)  # 等待强制终止完成

            # 清理 PID 文件
            if self.backend_pid_file.exists():
                self.backend_pid_file.unlink()

            # 再次确认进程已停止
            time.sleep(0.5)  # 额外等待确保进程完全清理
            if psutil.pid_exists(running_pid):
                console.print("[yellow]⚠️ 后端API进程可能仍在运行[/yellow]")

            console.print("[green]✅ 后端API已停止[/green]")
            return True

        except Exception as e:
            console.print(f"[red]后端API停止失败: {e}[/red]")
            return False

    def start(
        self,
        port: int | None = None,
        host: str | None = None,
        dev: bool = True,
        backend_port: int | None = None,
        auto_gateway: bool = True,  # 新增：是否自动启动 gateway
        auto_llm: bool = True,  # 新增：是否自动启动 LLM 服务
        auto_install: bool = True,  # 新增：是否自动安装依赖
        auto_build: bool = True,  # 新增：是否自动构建（生产模式）
        skip_confirm: bool = False,  # 新增：跳过确认（用于 restart）
    ) -> bool:
        """启动 Studio（前端和后端）"""
        # 检查并启动 Gateway（如果需要 Chat 模式）
        if auto_gateway:
            gateway_pid = self.is_gateway_running()
            if not gateway_pid:
                console.print("[blue]🔍 检测到 Gateway 未运行，正在启动...[/blue]")
                if not self.start_gateway(host=host):
                    console.print("[yellow]⚠️  Gateway 启动失败，Chat 模式可能无法正常使用[/yellow]")
                    console.print(
                        f"[yellow]   您可以稍后手动启动: sage-gateway --host 0.0.0.0 --port {StudioPorts.GATEWAY}[/yellow]"
                    )
            else:
                console.print(f"[green]✅ Gateway 已在运行中 (PID: {gateway_pid})[/green]")

        # 检查并启动 LLM 服务（如果需要 Chat 模式）
        if auto_llm:
            llm_pid = self.is_llm_running()
            if not llm_pid:
                console.print("[blue]🔍 检测到 LLM 服务未运行，正在启动...[/blue]")
                # 传入Gateway端口，让引擎注册到正确的Control Plane
                if not self.start_llm_service(port=self.gateway_port):
                    console.print("[yellow]⚠️  LLM 服务启动失败，Chat 模式可能无法使用[/yellow]")
                    console.print(
                        f"[yellow]   您可以稍后手动启动: sage-llm serve-engine --port 9001[/yellow]"
                    )
            else:
                if llm_pid == -1:
                    console.print("[green]✅ LLM 服务已在运行中（外部启动）[/green]")
                else:
                    console.print(f"[green]✅ LLM 服务已在运行中 (PID: {llm_pid})[/green]")

        # 启动后端API服务（独立运行，因为需要完整的 SAGE 框架能力）
        # Studio 后端不仅提供认证，还需要：
        # - Pipeline Builder & Operators Registry
        # - Jobs Management & Execution
        # - Dataset Management & File Upload
        # 这些都是 SAGE 框架层面的功能，不应该合并到 sageLLM Gateway
        backend_startup_success = self.start_backend(port=backend_port)
        if not backend_startup_success:
            console.print("[yellow]⚠️  后端API启动失败，某些功能可能无法使用[/yellow]")
            console.print("[yellow]   注意：Studio 需要独立的后端来管理 SAGE pipelines 和组件[/yellow]")
            console.print("[yellow]   如果端口冲突，可以设置环境变量: STUDIO_BACKEND_PORT=8081[/yellow]")

        # 🆕 智能端口冲突解决 (Smart Port Conflict Resolution)
        # 解决场景：配置文件中保存了旧端口 (如 5173)，但该端口被其他服务占用 (如 Prod 环境)，
        # 而当前代码的默认端口已更新 (如 5179)。此时应自动切换到新默认端口。
        if port is None:
            config = self.load_config()
            config_port = config.get("port", self.default_port)

            # 如果配置端口 != 默认端口 (说明可能是旧配置)
            if config_port != self.default_port:
                # 检查配置端口是否被占用
                if self._is_port_in_use(config_port):
                    # 检查是否是我们的 PID (如果是我们自己，就不算冲突)
                    pid_exists = False
                    if self.pid_file.exists():
                        try:
                            with open(self.pid_file) as f:
                                pid = int(f.read().strip())
                            if psutil.pid_exists(pid):
                                pid_exists = True
                        except Exception:
                            pass

                    if not pid_exists:
                        # 端口被占用且不是我们的 PID -> 冲突
                        # 检查默认端口是否空闲
                        if not self._is_port_in_use(self.default_port):
                            console.print(
                                f"[yellow]⚠️  检测到配置端口 {config_port} 被占用 (可能是旧配置)，自动切换到默认端口 {self.default_port}[/yellow]"
                            )
                            # 更新配置文件
                            config["port"] = self.default_port
                            self.save_config(config)

        # 检查前端是否已运行
        running_pid = self.is_running()
        if running_pid:
            if running_pid == -1:
                console.print("[yellow]⚠️  检测到 Studio 端口被占用 (孤儿进程)[/yellow]")
                console.print("[dim]   请运行 'sage studio stop' 来清理它[/dim]")
            else:
                console.print(f"[yellow]Studio前端已经在运行中 (PID: {running_pid})[/yellow]")
            return True

        if not self.check_dependencies():
            console.print("[red]依赖检查失败[/red]")
            return False

        # 检查并安装 npm 依赖
        node_modules = self.frontend_dir / "node_modules"
        if not node_modules.exists():
            if auto_install:
                console.print("[blue]📦 检测到未安装前端依赖[/blue]")

                # 交互式确认（除非 skip_confirm=True）
                should_install = skip_confirm  # 如果跳过确认，直接安装

                if not skip_confirm:
                    console.print("[yellow]是否立即安装？这可能需要几分钟时间...[/yellow]")
                    try:
                        from rich.prompt import Confirm

                        should_install = Confirm.ask("[cyan]开始安装依赖?[/cyan]", default=True)
                    except ImportError:
                        # 如果没有 rich.prompt，直接安装
                        should_install = True

                if should_install:
                    console.print("[blue]开始安装依赖...[/blue]")
                    if not self.install_dependencies():
                        console.print("[red]依赖安装失败[/red]")
                        return False
                else:
                    console.print("[yellow]跳过安装，请稍后手动运行: sage studio install[/yellow]")
                    return False
            else:
                console.print("[yellow]未安装依赖，请先运行: sage studio install[/yellow]")
                return False

        if not self._ensure_frontend_dependency_integrity(
            auto_fix=auto_install, skip_confirm=skip_confirm
        ):
            console.print("[red]前端依赖损坏，已停止启动流程[/red]")
            return False

        # 使用提供的参数或配置文件中的默认值
        config = self.load_config()
        port = port or config.get("port", self.default_port)
        host = host or config.get("host", self.default_host)

        # 保存新配置
        config.update({"port": port, "host": host, "dev_mode": dev})
        self.save_config(config)

        # 从配置读取当前后端端口（start_backend 可能在端口冲突时自动改写配置）
        effective_backend_port = int(config.get("backend_port", self.backend_port))

        console.print(f"[blue]启动 Studio前端 在 {host}:{port}[/blue]")

        try:
            # 根据模式选择启动命令
            if dev:
                # 开发模式：使用 Vite dev server
                console.print("[blue]启动开发模式（Vite）...[/blue]")
                cmd = [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    host,
                    "--port",
                    str(port),
                ]
            else:
                # 生产模式：使用 Vite preview 或 serve
                # 首先确保有构建输出
                if not self.dist_dir.exists() or not list(self.dist_dir.glob("*")):
                    if auto_build:
                        console.print("[blue]🏗️  检测到无构建输出[/blue]")

                        # 交互式确认（除非 skip_confirm=True）
                        should_build = skip_confirm  # 如果跳过确认，直接构建

                        if not skip_confirm:
                            console.print("[yellow]是否立即构建？这可能需要几分钟时间...[/yellow]")
                            try:
                                from rich.prompt import Confirm

                                should_build = Confirm.ask("[cyan]开始构建?[/cyan]", default=True)
                            except ImportError:
                                # 如果没有 rich.prompt，直接构建
                                should_build = True

                        if should_build:
                            console.print("[blue]开始构建...[/blue]")
                            if not self.build():
                                console.print("[red]构建失败，无法启动生产模式[/red]")
                                return False
                        else:
                            console.print(
                                "[yellow]跳过构建，请稍后手动运行: sage studio build[/yellow]"
                            )
                            return False
                    else:
                        console.print("[yellow]未构建，请先运行: sage studio build[/yellow]")
                        return False

                console.print("[blue]启动生产服务器（Vite Preview）...[/blue]")

                # 使用 Vite preview，指定从 .sage/studio/dist 读取构建产物
                cmd = [
                    "npm",
                    "run",
                    "preview",
                    "--",
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "--outDir",
                    str(self.dist_dir),  # 指定构建输出目录
                ]

            # 准备环境变量
            env = os.environ.copy()
            env["npm_config_cache"] = str(self.npm_cache_dir)
            # 传递后端端口给 Vite proxy（开发模式下 /api 需要）
            env["VITE_BACKEND_PORT"] = str(effective_backend_port)
            env["STUDIO_BACKEND_PORT"] = str(effective_backend_port)
            # 传递 Gateway 端口给 Vite (用于 proxy target)
            env["VITE_GATEWAY_PORT"] = str(self.gateway_port)
            # 传递 PORT 给 Vite (虽然 CLI 参数也会覆盖，但保持一致更好)
            env["PORT"] = str(port)

            # 启动进程 - 使用独立的日志文件句柄
            # 关键修复: 使用 with 语句确保文件句柄正确管理，并设置 stdin=DEVNULL
            # 防止 npm/Vite 进程尝试读取终端输入导致卡顿
            log_handle = open(self.log_file, "w")
            process = subprocess.Popen(
                cmd,
                cwd=self.frontend_dir,
                env=env,  # 传递环境变量
                stdin=subprocess.DEVNULL,  # 关键：阻止子进程读取 stdin
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,  # 在新会话中运行,避免信号问题
            )
            # 注意：不关闭 log_handle，让子进程继承并管理它
            # 子进程退出时会自动关闭

            # 保存 PID
            with open(self.pid_file, "w") as f:
                f.write(str(process.pid))

            console.print(f"[green]Studio 启动成功 (PID: {process.pid})[/green]")

            return True

        except Exception as e:
            console.print(f"[red]启动失败: {e}[/red]")
            return False

    def stop(self, stop_gateway: bool = False, stop_llm: bool = False) -> bool:
        """停止 Studio（前端）

        Args:
            stop_gateway: 是否同时停止 Gateway（默认不停止，因为可能被其他服务使用）
            stop_llm: 是否同时停止 LLM 服务（默认不停止，因为可能被其他服务使用）
        """
        frontend_pid = self.is_running()

        stopped_services = []

        # 停止前端
        if frontend_pid and frontend_pid != -1:
            try:
                # 发送终止信号
                os.killpg(os.getpgid(frontend_pid), signal.SIGTERM)

                # 等待进程结束
                for _i in range(10):
                    if not psutil.pid_exists(frontend_pid):
                        break
                    time.sleep(1)

                # 如果进程仍然存在，强制杀死
                if psutil.pid_exists(frontend_pid):
                    os.killpg(os.getpgid(frontend_pid), signal.SIGKILL)

                # 清理 PID 文件
                if self.pid_file.exists():
                    self.pid_file.unlink()

                # 清理临时服务器脚本
                spa_server_script = self.studio_cache_dir / "spa_server.py"
                if spa_server_script.exists():
                    spa_server_script.unlink()

                stopped_services.append("前端")
            except Exception as e:
                console.print(f"[red]前端停止失败: {e}[/red]")

        # 补充检查：通过端口清理孤儿进程 (Orphaned Process Cleanup)
        # 即使 PID 文件不存在或已处理，端口可能仍被占用 (如 frontend_pid == -1 或僵尸进程)
        config = self.load_config()
        port = config.get("port", self.default_port)
        if self._is_port_in_use(port):
            console.print(f"[yellow]检测到端口 {port} 仍被占用，尝试清理孤儿进程...[/yellow]")
            if self._kill_process_on_port(port):
                stopped_services.append(f"前端(端口{port})")
                # 再次确保 PID 文件被清理
                if self.pid_file.exists():
                    self.pid_file.unlink()

        # 停止 Studio 后端
        backend_pid = self.is_backend_running()
        if backend_pid and backend_pid != -1:
            # Normal case: PID is known, stop gracefully via PID.
            if self.stop_backend():
                stopped_services.append("后端API")
        elif backend_pid == -1:
            # Backend is reachable via HTTP health check but has no PID file
            # (e.g. started externally or PID file was lost).  Fall back to
            # killing by port so restart always starts with a clean slate.
            _cfg = self.load_config()
            _backend_port = _cfg.get("backend_port", self.backend_port)
            console.print(f"[yellow]检测到后端API在端口 {_backend_port} 运行（无PID文件），尝试通过端口清理...[/yellow]")
            if self._kill_process_on_port(_backend_port):
                if self.backend_pid_file.exists():
                    self.backend_pid_file.unlink()
                stopped_services.append("后端API")

        # 可选：停止 Gateway
        if stop_gateway:
            gateway_pid = self.is_gateway_running()
            if gateway_pid and gateway_pid != -1:
                if self.stop_gateway():
                    stopped_services.append("Gateway")

        # 可选：停止 LLM 服务
        if stop_llm:
            llm_pid = self.is_llm_running()
            if llm_pid and llm_pid != -1:
                if self.stop_llm_service():
                    stopped_services.append("LLM服务")

        if stopped_services:
            console.print(f"[green]Studio {' 和 '.join(stopped_services)} 已停止[/green]")
            return True
        else:
            console.print("[yellow]Studio 未运行或停止失败[/yellow]")
            return False

    def clean_frontend_cache(self) -> bool:
        """清理前端构建缓存

        清理以下目录以确保使用最新代码：
        - dist/ (构建产物)
        - .vite/ (Vite 缓存)
        - node_modules/.vite/ (Vite 节点缓存)

        Returns:
            bool: 是否成功清理
        """
        import shutil

        cleaned_dirs = []
        errors = []

        # 定义要清理的目录（相对于 frontend_dir）
        cache_dirs = [
            self.frontend_dir / "dist",
            self.frontend_dir / ".vite",
            self.frontend_dir / "node_modules" / ".vite",
        ]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    shutil.rmtree(cache_dir)
                    cleaned_dirs.append(cache_dir.name)
                    console.print(
                        f"[green]  ✓ 清理: {cache_dir.relative_to(self.frontend_dir)}[/green]"
                    )
                except Exception as e:
                    errors.append(f"{cache_dir.name}: {e}")
                    console.print(f"[yellow]  ⚠ 清理失败: {cache_dir.name} - {e}[/yellow]")

        if cleaned_dirs:
            console.print(f"[green]✅ 已清理 {len(cleaned_dirs)} 个缓存目录[/green]")
            return True
        elif errors:
            console.print("[red]❌ 清理过程中出现错误[/red]")
            return False
        else:
            console.print("[blue]ℹ️  未发现需要清理的缓存[/blue]")
            return False

    def clean(self) -> bool:
        """清理 Studio 缓存和临时文件（兼容旧命令）

        这是 clean_frontend_cache 的别名，用于命令行接口。
        """
        return self.clean_frontend_cache()

    def status(self):
        """显示状态"""
        frontend_pid = self.is_running()
        gateway_pid = self.is_gateway_running()
        config = self.load_config()

        # 创建前端状态表格
        frontend_table = Table(title="SAGE Studio 前端状态")
        frontend_table.add_column("属性", style="cyan", width=12)
        frontend_table.add_column("值", style="white")

        if frontend_pid:
            if frontend_pid == -1:
                frontend_table.add_row("状态", "[yellow]运行中（PID未知）[/yellow]")
            else:
                try:
                    process = psutil.Process(frontend_pid)
                    frontend_table.add_row("状态", "[green]运行中[/green]")
                    frontend_table.add_row("PID", str(frontend_pid))
                    frontend_table.add_row(
                        "启动时间",
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(process.create_time())),
                    )
                    frontend_table.add_row("CPU %", f"{process.cpu_percent():.1f}%")
                    frontend_table.add_row(
                        "内存", f"{process.memory_info().rss / 1024 / 1024:.1f} MB"
                    )
                except psutil.NoSuchProcess:
                    frontend_table.add_row("状态", "[red]进程不存在[/red]")
        else:
            frontend_table.add_row("状态", "[red]未运行[/red]")

        frontend_table.add_row("端口", str(config.get("port", self.default_port)))
        frontend_table.add_row("主机", config.get("host", self.default_host))
        frontend_table.add_row("开发模式", "是" if config.get("dev_mode") else "否")
        frontend_table.add_row("配置文件", str(self.config_file))
        frontend_table.add_row("日志文件", str(self.log_file))

        console.print(frontend_table)

        # 创建 Gateway 状态表格（后端 API 已合并到 Gateway）
        gateway_table = Table(title="SAGE Gateway 状态")
        gateway_table.add_column("属性", style="cyan", width=12)
        gateway_table.add_column("值", style="white")

        if gateway_pid:
            if gateway_pid == -1:
                gateway_table.add_row("状态", "[yellow]运行中（PID未知）[/yellow]")
            else:
                gateway_table.add_row("状态", "[green]运行中[/green]")
                gateway_table.add_row("PID", str(gateway_pid))
            gateway_table.add_row("端口", str(self.gateway_port))
            gateway_table.add_row("API", f"http://localhost:{self.gateway_port}/v1")
        else:
            gateway_table.add_row("状态", "[red]未运行[/red]")
            gateway_table.add_row("端口", str(self.gateway_port))
            gateway_table.add_row(
                "启动命令", f"sage-gateway --host 0.0.0.0 --port {StudioPorts.GATEWAY}"
            )

        gateway_table.add_row("PID文件", str(self.gateway_pid_file))
        gateway_table.add_row("日志文件", str(self.gateway_log_file))

        console.print(gateway_table)

        # 检查端口是否可访问（不使用代理）
        if frontend_pid:
            try:
                session = requests.Session()
                session.trust_env = False  # 忽略环境代理
                url = f"http://localhost:{config.get('port', self.default_port)}"
                response = session.get(url, timeout=5)
                if response.status_code == 200:
                    console.print(f"[green]✅ 前端服务可访问: {url}[/green]")
                else:
                    console.print(f"[yellow]⚠️ 前端服务响应异常: {response.status_code}[/yellow]")
            except requests.RequestException as e:
                console.print(f"[red]❌ 前端服务不可访问: {e}[/red]")

        # 检查 Gateway 是否可访问（后端 API 通过 Gateway 提供）
        if gateway_pid:
            try:
                session = requests.Session()
                session.trust_env = False  # 忽略环境代理
                gateway_url = f"http://localhost:{self.gateway_port}/health"
                response = session.get(gateway_url, timeout=5)
                if response.status_code == 200:
                    console.print(f"[green]✅ Gateway可访问: {gateway_url}[/green]")
                    gateway_api_probe = f"http://localhost:{self.gateway_port}/api/llm/status"
                    api_probe = session.get(gateway_api_probe, timeout=3)
                    if api_probe.status_code == 200:
                        console.print(
                            "[dim]   (后端 API 已合并到 Gateway: /api/chat, /api/config 等)[/dim]"
                        )
                    else:
                        backend_api = f"http://localhost:{self.backend_port}"
                        console.print(
                            "[dim]   (当前模式: Studio API 由独立后端提供, "
                            f"请访问 {backend_api}/api/* )[/dim]"
                        )
                        try:
                            backend_health = session.get(f"{backend_api}/health", timeout=3)
                            if backend_health.status_code == 200:
                                console.print(
                                    f"[green]✅ Studio后端可访问: {backend_api}/health[/green]"
                                )
                            else:
                                console.print(
                                    "[yellow]⚠️ Studio后端响应异常: "
                                    f"{backend_health.status_code}[/yellow]"
                                )
                        except requests.RequestException as backend_exc:
                            console.print(f"[red]❌ Studio后端不可访问: {backend_exc}[/red]")
                else:
                    console.print(f"[yellow]⚠️ Gateway响应异常: {response.status_code}[/yellow]")
            except requests.RequestException as e:
                console.print(f"[red]❌ Gateway不可访问: {e}[/red]")

    def logs(self, follow: bool = False, backend: bool = False):
        """显示日志"""
        # 选择要查看的日志文件
        if backend:
            log_file = self.backend_log_file
            service_name = "后端API"
        else:
            log_file = self.log_file
            service_name = "前端"

        if not log_file.exists():
            console.print(f"[yellow]{service_name}日志文件不存在[/yellow]")
            return

        if follow:
            console.print(f"[blue]跟踪{service_name}日志 (按 Ctrl+C 退出): {log_file}[/blue]")
            try:
                subprocess.run(["tail", "-f", str(log_file)])
            except KeyboardInterrupt:
                console.print(f"\n[blue]停止跟踪{service_name}日志[/blue]")
        else:
            console.print(f"[blue]显示{service_name}日志: {log_file}[/blue]")
            try:
                with open(log_file) as f:
                    lines = f.readlines()
                    # 显示最后50行
                    for line in lines[-50:]:
                        print(line.rstrip())
            except Exception as e:
                console.print(f"[red]读取{service_name}日志失败: {e}[/red]")

    def open_browser(self):
        """在浏览器中打开 Studio"""
        config = self.load_config()
        url = f"http://{config.get('host', self.default_host)}:{config.get('port', self.default_port)}"

        try:
            import webbrowser

            webbrowser.open(url)
            console.print(f"[green]已在浏览器中打开: {url}[/green]")
        except Exception as e:
            console.print(f"[red]打开浏览器失败: {e}[/red]")
            console.print(f"[blue]请手动访问: {url}[/blue]")
