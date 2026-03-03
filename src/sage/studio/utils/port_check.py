"""Port availability check utilities for SAGE Studio"""

from rich.console import Console

# Import unified network utilities from sage-common
from sage.common.utils.system.network import (
    find_port_processes,
    is_port_occupied,
)

console = Console()


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a port is already in use.

    Args:
        port: Port number to check
        host: Host address (default: 0.0.0.0)

    Returns:
        True if port is in use, False otherwise

    Note:
        This is a wrapper around sage.common.utils.system.network.is_port_occupied
    """
    return is_port_occupied(host, port)


def get_process_using_port(port: int) -> dict | None:
    """Get information about the process using a specific port.

    Args:
        port: Port number to check

    Returns:
        Dictionary with process info (pid, name, cmdline) or None if not found

    Note:
        This is a wrapper around sage.common.utils.system.network.find_port_processes
    """
    try:
        import psutil

        processes = find_port_processes(port)
        if not processes:
            return None

        proc = processes[0]
        try:
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "cmdline": " ".join(proc.cmdline()),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {
                "pid": proc.pid,
                "name": "unknown",
                "cmdline": "unknown",
            }
    except Exception:
        return None


def check_port_available(port: int, host: str = "0.0.0.0", service_name: str = "Service") -> bool:
    """Check if a port is available and print detailed information if not.

    Args:
        port: Port number to check
        host: Host address
        service_name: Name of the service for display purposes

    Returns:
        True if port is available, False if in use
    """
    if not is_port_in_use(port, host):
        console.print(f"[green]✓[/green] 端口 {port} 可用")
        return True

    console.print(f"[red]✗[/red] 端口 {port} 已被占用")

    # Try to get process info
    proc_info = get_process_using_port(port)
    if proc_info:
        console.print("  [yellow]占用进程:[/yellow]")
        console.print(f"    PID: {proc_info['pid']}")
        console.print(f"    名称: {proc_info['name']}")
        if proc_info["cmdline"] != "unknown":
            cmdline = proc_info["cmdline"]
            if len(cmdline) > 100:
                cmdline = cmdline[:97] + "..."
            console.print(f"    命令: {cmdline}")

        console.print("\n  [cyan]💡 解决方案:[/cyan]")
        console.print(f"    • 停止占用进程: kill {proc_info['pid']}")
        console.print("    • 或使用其他端口: sage studio start --port <other_port>")
    else:
        console.print("  [yellow]无法获取占用进程信息[/yellow]")
        console.print("\n  [cyan]💡 解决方案:[/cyan]")
        console.print(f"    • 检查端口占用: lsof -i :{port}")
        console.print("    • 或使用其他端口: sage studio start --port <other_port>")

    return False


def check_multiple_ports(ports: dict[str, int], host: str = "0.0.0.0") -> tuple[bool, list[str]]:
    """Check multiple ports and return availability status.

    Args:
        ports: Dictionary mapping service names to port numbers
        host: Host address

    Returns:
        Tuple of (all_available, list_of_unavailable_services)
    """
    console.print("[blue]🔍 检查端口可用性...[/blue]\n")

    unavailable = []
    for service_name, port in ports.items():
        if not check_port_available(port, host, service_name):
            unavailable.append(service_name)

    if unavailable:
        console.print(f"\n[red]❌ {len(unavailable)} 个端口不可用[/red]")
        return False, unavailable
    else:
        console.print("\n[green]✅ 所有端口检查通过[/green]")
        return True, []
