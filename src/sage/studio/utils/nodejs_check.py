"""Node.js version check and auto-install utilities"""

import re
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

# Minimum required Node.js version
MIN_NODE_VERSION = (18, 0, 0)  # Node.js 18.x+


def parse_node_version(version_string: str) -> tuple[int, int, int] | None:
    """Parse Node.js version string (e.g., 'v18.12.0') into tuple (18, 12, 0)"""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version_string)
    if match:
        return tuple(map(int, match.groups()))
    return None


def check_node_version() -> tuple[bool, str | None]:
    """Check if Node.js is installed and meets minimum version requirement.

    Returns:
        (is_valid, version_string): True if version is sufficient, False otherwise
    """
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return False, None

        version_string = result.stdout.strip()
        version_tuple = parse_node_version(version_string)

        if version_tuple is None:
            console.print(f"[yellow]⚠️  无法解析 Node.js 版本: {version_string}[/yellow]")
            return False, version_string

        if version_tuple >= MIN_NODE_VERSION:
            return True, version_string
        else:
            return False, version_string

    except FileNotFoundError:
        return False, None
    except Exception as e:
        console.print(f"[yellow]⚠️  检查 Node.js 版本时出错: {e}[/yellow]")
        return False, None


def install_nodejs_via_nvm() -> bool:
    """Install Node.js using nvm (Node Version Manager)"""
    console.print("[blue]🔧 尝试使用 nvm 安装 Node.js...[/blue]")

    home = Path.home()
    nvm_dir = home / ".nvm"

    # Check if nvm is installed
    if not nvm_dir.exists():
        console.print("[yellow]⚠️  nvm 未安装，正在安装 nvm...[/yellow]")
        try:
            # Install nvm
            install_cmd = (
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
            )
            subprocess.run(install_cmd, shell=True, check=True, timeout=120)
            console.print("[green]✅ nvm 安装成功[/green]")
        except Exception as e:
            console.print(f"[red]❌ nvm 安装失败: {e}[/red]")
            return False

    # Install Node.js LTS using nvm
    try:
        # Source nvm and install Node.js
        install_cmd = f"""
        export NVM_DIR="{nvm_dir}"
        [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
        nvm install --lts
        nvm use --lts
        """
        subprocess.run(install_cmd, shell=True, check=True, timeout=300, executable="/bin/bash")
        console.print("[green]✅ Node.js 安装成功[/green]")

        # Verify installation
        is_valid, version = check_node_version()
        if is_valid:
            console.print(f"[green]✅ Node.js {version} 已安装并就绪[/green]")
            return True
        else:
            console.print("[yellow]⚠️  Node.js 安装完成，但可能需要重新启动 shell[/yellow]")
            console.print("[cyan]💡 请运行: source ~/.bashrc 或 source ~/.zshrc[/cyan]")
            return False

    except Exception as e:
        console.print(f"[red]❌ Node.js 安装失败: {e}[/red]")
        return False


def install_nodejs_via_apt() -> bool:
    """Install Node.js using apt (Debian/Ubuntu)"""
    console.print("[blue]🔧 尝试使用 apt 安装 Node.js...[/blue]")

    try:
        # Add NodeSource repository for Node.js 18.x
        console.print("[blue]添加 NodeSource 仓库...[/blue]")
        subprocess.run(
            "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -",
            shell=True,
            check=True,
            timeout=120,
        )

        # Install Node.js
        console.print("[blue]安装 Node.js...[/blue]")
        subprocess.run(["sudo", "apt-get", "install", "-y", "nodejs"], check=True, timeout=300)

        console.print("[green]✅ Node.js 安装成功[/green]")

        # Verify installation
        is_valid, version = check_node_version()
        if is_valid:
            console.print(f"[green]✅ Node.js {version} 已安装并就绪[/green]")
            return True
        else:
            return False

    except Exception as e:
        console.print(f"[red]❌ 使用 apt 安装 Node.js 失败: {e}[/red]")
        return False


def auto_install_nodejs() -> bool:
    """Automatically install Node.js using available package manager"""
    console.print("[yellow]⚠️  Node.js 版本过低或未安装[/yellow]")
    console.print(
        f"[cyan]最低要求版本: Node.js {MIN_NODE_VERSION[0]}.{MIN_NODE_VERSION[1]}.{MIN_NODE_VERSION[2]}[/cyan]"
    )

    # Ask for confirmation
    response = input("是否自动安装最新的 Node.js LTS 版本? (y/n): ").strip().lower()
    if response not in ("y", "yes", "是"):
        console.print("[yellow]⚠️  已取消安装，请手动安装 Node.js[/yellow]")
        console.print("[cyan]💡 手动安装指南:[/cyan]")
        console.print("  • 使用 nvm: https://github.com/nvm-sh/nvm")
        console.print(
            "  • 使用 apt (Ubuntu/Debian): curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
        )
        return False

    # Try nvm first (user-level, no sudo required)
    if install_nodejs_via_nvm():
        return True

    # Fall back to apt (requires sudo)
    console.print("[blue]尝试系统级安装 (需要 sudo 权限)...[/blue]")
    if install_nodejs_via_apt():
        return True

    # All methods failed
    console.print("[red]❌ 自动安装失败，请手动安装 Node.js[/red]")
    console.print("[cyan]💡 手动安装指南:[/cyan]")
    console.print("  • 官方网站: https://nodejs.org/")
    console.print("  • 使用 nvm: https://github.com/nvm-sh/nvm")
    return False
