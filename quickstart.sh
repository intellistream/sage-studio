#!/usr/bin/env bash
# SAGE Studio Quick Start Script
# 快速安装和启动 SAGE Studio 开发环境

set -e  # Exit on error

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    SAGE Studio Quick Start Installation${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo ""

# ========================================
# 1. 检查 Python 环境
# ========================================
info "检查 Python 环境..."

if ! command -v python3 &> /dev/null; then
    error "Python 3 未找到，请先安装 Python 3.10 或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    error "Python 版本 $PYTHON_VERSION 过低，需要 Python 3.10+"
    exit 1
fi

success "Python $PYTHON_VERSION 已安装"

# ========================================
# 2. 检查/创建虚拟环境
# ========================================
info "检查 Python 虚拟环境..."

# 检查是否在 conda 环境或虚拟环境中
if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
    success "已在 Conda 环境中: $CONDA_DEFAULT_ENV"
    PYTHON_ENV_ACTIVE=true
elif [[ -n "$VIRTUAL_ENV" ]]; then
    success "已在虚拟环境中: $(basename $VIRTUAL_ENV)"
    PYTHON_ENV_ACTIVE=true
elif [[ -d "venv" ]] || [[ -d ".venv" ]]; then
    success "检测到虚拟环境目录"
    if [[ -d "venv" ]]; then
        info "激活虚拟环境..."
        source venv/bin/activate
    elif [[ -d ".venv" ]]; then
        info "激活虚拟环境..."
        source .venv/bin/activate
    fi
    PYTHON_ENV_ACTIVE=true
else
    warning "未检测到虚拟环境或 Conda 环境"
    read -p "是否创建新的虚拟环境? (Y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        info "创建虚拟环境..."
        python3 -m venv venv
        success "虚拟环境已创建: venv/"
        
        info "激活虚拟环境..."
        source venv/bin/activate
        success "虚拟环境已激活"
        PYTHON_ENV_ACTIVE=true
    else
        warning "跳过虚拟环境创建。建议手动创建并激活虚拟环境。"
        PYTHON_ENV_ACTIVE=false
    fi
fi

# ========================================
# 3. 安装 Python 依赖
# ========================================
info "安装 Python 依赖..."

# 升级 pip
python3 -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# 安装开发模式
if python3 -m pip install -e ".[dev]" > /tmp/sage-studio-install.log 2>&1; then
    success "Python 依赖安装成功"
else
    error "Python 依赖安装失败，查看日志: /tmp/sage-studio-install.log"
    exit 1
fi

# ========================================
# 4. 检查 Node.js 环境
# ========================================
info "检查 Node.js 环境..."

if ! command -v node &> /dev/null; then
    warning "Node.js 未找到"
    echo "  请访问 https://nodejs.org/ 安装 Node.js 18+ (推荐 LTS 版本)"
    echo "  或使用 nvm: nvm install --lts"
    NODE_AVAILABLE=false
else
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    
    if [[ $NODE_MAJOR -lt 18 ]]; then
        warning "Node.js 版本 $NODE_VERSION 过低，推荐 18+"
        NODE_AVAILABLE=false
    else
        success "Node.js $NODE_VERSION 已安装"
        NODE_AVAILABLE=true
    fi
fi

# ========================================
# 5. 安装前端依赖
# ========================================
if [[ "$NODE_AVAILABLE" == true ]]; then
    info "安装前端依赖..."
    
    FRONTEND_DIR="$SCRIPT_DIR/src/sage/studio/frontend"
    
    if [[ -d "$FRONTEND_DIR" ]]; then
        cd "$FRONTEND_DIR"
        
        if command -v npm &> /dev/null; then
            if npm install > /tmp/sage-studio-npm-install.log 2>&1; then
                success "前端依赖安装成功"
            else
                error "前端依赖安装失败，查看日志: /tmp/sage-studio-npm-install.log"
                exit 1
            fi
        else
            error "npm 未找到，请确保 Node.js 正确安装"
            exit 1
        fi
        
        cd "$SCRIPT_DIR"
    else
        warning "前端目录未找到: $FRONTEND_DIR"
    fi
else
    warning "跳过前端依赖安装（Node.js 不可用）"
fi

# ========================================
# 6. 检查 SAGE 核心依赖
# ========================================
info "检查 SAGE 核心依赖..."

SAGE_KERNEL_OK=false
SAGE_MIDDLEWARE_OK=false
SAGE_LIBS_OK=false

if python3 -c "import sage.kernel" 2>/dev/null; then
    success "sage-kernel 已安装"
    SAGE_KERNEL_OK=true
else
    warning "sage-kernel 未找到或版本不兼容"
fi

if python3 -c "import sage.middleware" 2>/dev/null; then
    success "sage-middleware 已安装"
    SAGE_MIDDLEWARE_OK=true
else
    warning "sage-middleware 未找到或版本不兼容"
fi

if python3 -c "import sage.libs" 2>/dev/null; then
    success "sage-libs 已安装"
    SAGE_LIBS_OK=true
else
    warning "sage-libs 未找到或版本不兼容"
fi

# ========================================
# 7. 验证安装
# ========================================
info "验证 SAGE Studio 安装..."

if python3 -c "from sage.studio.studio_manager import StudioManager" 2>/dev/null; then
    success "SAGE Studio 核心模块安装成功！"
    STUDIO_OK=true
else
    warning "SAGE Studio 导入失败"
    STUDIO_OK=false
    
    # 详细诊断
    echo ""
    error "安装验证未完全通过，可能的原因："
    
    if [[ "$SAGE_KERNEL_OK" == false ]] || [[ "$SAGE_MIDDLEWARE_OK" == false ]] || [[ "$SAGE_LIBS_OK" == false ]]; then
        echo "  • SAGE 核心依赖缺失或版本不匹配"
        echo "  • 建议运行: pip install --upgrade isage-kernel isage-middleware isage-libs"
    fi
    
    echo "  • 或者从源码安装 SAGE 核心包（开发模式）"
    echo "  • 详细错误信息可运行: python -c 'from sage.studio.studio_manager import StudioManager'"
    echo ""
fi

# ========================================
# 8. 显示下一步操作
# ========================================
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}    Installation Complete! 🎉${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "下一步操作:"
echo ""
echo "  1. 启动 Studio (开发模式):"
echo -e "     ${BLUE}sage studio start --dev${NC}"
echo ""
echo "  2. 或手动启动服务:"
echo -e "     ${BLUE}# 终端 1 - 后端${NC}"
echo "     cd src/sage/studio/config/backend"
echo "     python api.py"
echo ""
echo -e "     ${BLUE}# 终端 2 - 前端${NC}"
echo "     cd src/sage/studio/frontend"
echo "     npm run dev"
echo ""
echo "  3. 访问应用:"
echo "     前端: http://localhost:5173"
echo "     后端: http://localhost:8080"
echo "     API 文档: http://localhost:8080/docs"
echo ""
echo "  4. 运行测试:"
echo -e "     ${BLUE}pytest tests/unit/ -v${NC}"
echo ""
echo "  5. 查看更多帮助:"
echo -e "     ${BLUE}sage studio --help${NC}"
echo ""

if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
    info "注意: 你当前在 Conda 环境中 ($CONDA_DEFAULT_ENV)，重新打开终端时需要激活:"
    echo -e "  ${BLUE}conda activate $CONDA_DEFAULT_ENV${NC}"
    echo ""
elif [[ -n "$VIRTUAL_ENV" ]]; then
    info "注意: 你当前在虚拟环境中，重新打开终端时需要激活:"
    echo -e "  ${BLUE}source venv/bin/activate${NC}"
    echo ""
fi

success "Happy coding! 🚀"
