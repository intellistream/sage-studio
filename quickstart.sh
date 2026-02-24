#!/bin/bash
# SAGE Studio Quickstart Script
# Sets up development environment

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Print banner
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${BLUE}   ____   ___   _____   ____   ${NC}"
echo -e "${BOLD}${BLUE}  / __/  / _ | / ___/  / __/   ${NC}"
echo -e "${BOLD}${BLUE} _\\ \\   / __ |/ (_ /  / _/     ${NC}"
echo -e "${BOLD}${BLUE}/___/  /_/ |_|\\___/  /___/     ${NC}"
echo -e "${BOLD}${BLUE}                                ${NC}"
echo -e "${BOLD}${BLUE}    Studio - Visual Workflow   ${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}SAGE Studio Quickstart Setup${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Detect project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Always bind installs to current Python interpreter
PYTHON_CMD="${PYTHON_CMD:-python}"
PIP_CMD="${PIP_CMD:-$PYTHON_CMD -m pip}"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    echo -e "${RED}✗ Python interpreter not found: $PYTHON_CMD${NC}"
    exit 1
fi

PYTHON_EXECUTABLE="$("$PYTHON_CMD" -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
if [ -z "$PYTHON_EXECUTABLE" ]; then
    echo -e "${RED}✗ Failed to resolve Python executable from: $PYTHON_CMD${NC}"
    exit 1
fi

echo -e "${BLUE}📂 Project root: ${NC}$PROJECT_ROOT"
echo -e "${BLUE}🐍 Python: ${NC}$PYTHON_EXECUTABLE"
echo ""

# Step 1: Install git hooks
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}${BOLD}Step 1: Installing Git Hooks${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
TEMPLATE_DIR="$PROJECT_ROOT/hooks"

if [ ! -d "$HOOKS_DIR" ]; then
    echo -e "${RED}✗ Git repository not initialized${NC}"
    echo -e "${YELLOW}Run: git init${NC}"
    exit 1
fi

# Install hooks
if [ -d "$TEMPLATE_DIR" ]; then
    for hook in pre-commit pre-push post-commit; do
        if [ -f "$TEMPLATE_DIR/$hook" ]; then
            cp "$TEMPLATE_DIR/$hook" "$HOOKS_DIR/$hook"
            chmod +x "$HOOKS_DIR/$hook"
            echo -e "${GREEN}✓ Installed $hook hook${NC}"
        fi
    done
else
    echo -e "${YELLOW}⚠ No hooks directory found, skipping...${NC}"
fi

echo ""

# Step 2: Install SAGE Studio
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}${BOLD}Step 2: Installing SAGE Studio${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "${BLUE}Installing sage-studio (editable) and all dependencies from PyPI...${NC}"
echo ""

# Uninstall any SAGE core packages that may have been installed as local editable
# installs (e.g. from SAGE/quickstart.sh --dev). We need PyPI versions here.
echo -e "${YELLOW}⚠ Removing any local editable SAGE installs (will reinstall from PyPI)...${NC}"
$PIP_CMD uninstall -y isage isage-common isage-platform isage-kernel isage-libs \
    isage-middleware isage-cli isage-tools 2>/dev/null || true
echo -e "${GREEN}✓ Cleared local SAGE editable installs${NC}"
echo ""

# Install studio itself in editable mode; all other dependencies (isage, isagellm,
# isage-agentic, etc.) are resolved from PyPI as declared in pyproject.toml.
$PIP_CMD install -e "$PROJECT_ROOT"

echo -e "${GREEN}✓ SAGE Studio installed${NC}"
echo ""

# Step 3: Verify installation
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}${BOLD}Step 3: Verifying Installation${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Fix namespace package issue (remove blocking __init__.py if exists)
SAGE_NAMESPACE_INIT="$("$PYTHON_CMD" -c 'import site; import os; print(os.path.join(site.getsitepackages()[0], "sage", "__init__.py"))' 2>/dev/null)"
if [ -f "$SAGE_NAMESPACE_INIT" ] && [ ! -s "$SAGE_NAMESPACE_INIT" ]; then
    echo -e "${YELLOW}⚠ Fixing namespace package issue...${NC}"
    rm -f "$SAGE_NAMESPACE_INIT"
    echo -e "${GREEN}✓ Namespace package fixed${NC}"
fi

if "$PYTHON_CMD" -c "from sage.studio.studio_manager import StudioManager; print('✓ SAGE Studio installed successfully')" 2>/dev/null; then
    echo -e "${GREEN}✓ Installation verified${NC}"
else
    echo -e "${RED}✗ Installation verification failed${NC}"
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo -e "  1. Check if SAGE core packages are installed: $PIP_CMD list | grep isage"
    echo -e "  2. Try reinstalling: $PIP_CMD install -e ."
    echo -e "  3. Check Python can import sage: $PYTHON_CMD -c 'import sage'"
    exit 1
fi

echo ""

# Success message
STUDIO_FRONTEND_PORT="${STUDIO_FRONTEND_PORT:-5173}"
STUDIO_BACKEND_PORT="${STUDIO_BACKEND_PORT:-8080}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}✓ Setup Complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo ""
echo -e "${BLUE}1. Start SAGE Studio:${NC}"
echo -e "   ${CYAN}sage studio start${NC}"
echo ""
echo -e "${BLUE}2. Open in browser:${NC}"
echo -e "   ${CYAN}http://localhost:${STUDIO_FRONTEND_PORT}${NC}"
echo ""
echo -e "${YELLOW}Note: Studio frontend runs on port ${STUDIO_FRONTEND_PORT}, backend on port ${STUDIO_BACKEND_PORT}${NC}"
echo -e "${YELLOW}      Use 'sage studio start --dev' for development mode${NC}"
echo -e "${YELLOW}      Use 'sage studio status' to check running status${NC}"
echo ""
