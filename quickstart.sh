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

echo -e "${BLUE}📂 Project root: ${NC}$PROJECT_ROOT"
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
    for hook in pre-commit pre-push; do
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

# Detect development mode (check if dependency repos exist locally)
PARENT_DIR="$(dirname "$PROJECT_ROOT")"
DEV_MODE=false

echo -e "${BLUE}Checking for local development repositories...${NC}"

# Check for common dependency repos
if [ -d "$PARENT_DIR/sage-agentic/src" ] || [ -d "$PARENT_DIR/sage-sias" ] || [ -d "$PARENT_DIR/SAGE/packages" ]; then
    DEV_MODE=true
    echo -e "${YELLOW}✓ Found local development repositories${NC}"
    echo -e "${YELLOW}  Using development mode (pip install -e)${NC}"
else
    echo -e "${BLUE}  No local repos found, using PyPI packages${NC}"
fi

echo ""

# Install dependencies
if [ "$DEV_MODE" = true ]; then
    echo -e "${BLUE}Installing in development mode...${NC}"

    # Install sage-agentic if available
    if [ -d "$PARENT_DIR/sage-agentic" ]; then
        echo -e "${CYAN}  → Installing sage-agentic from local source${NC}"
        pip install -e "$PARENT_DIR/sage-agentic"
    fi

    # Install sage-sias if available
    if [ -d "$PARENT_DIR/sage-sias" ]; then
        echo -e "${CYAN}  → Installing sage-sias from local source${NC}"
        pip install -e "$PARENT_DIR/sage-sias"
    fi

    # Install SAGE if available
    if [ -d "$PARENT_DIR/SAGE/packages" ]; then
        echo -e "${CYAN}  → Installing SAGE packages from local source${NC}"
        cd "$PARENT_DIR/SAGE" && ./quickstart.sh --dev --yes || echo -e "${YELLOW}⚠ SAGE installation skipped${NC}"
        cd "$PROJECT_ROOT"
    fi

    # Install studio itself in dev mode
    echo -e "${CYAN}  → Installing sage-studio in development mode${NC}"
    pip install -e "$PROJECT_ROOT"
else
    echo -e "${BLUE}Installing from PyPI...${NC}"
    pip install -e "$PROJECT_ROOT"
fi

echo -e "${GREEN}✓ SAGE Studio installed${NC}"
echo ""

# Step 3: Verify installation
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}${BOLD}Step 3: Verifying Installation${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if python -c "from sage.studio.studio_manager import StudioManager; print('✓ SAGE Studio installed successfully')" 2>/dev/null; then
    echo -e "${GREEN}✓ Installation verified${NC}"
else
    echo -e "${RED}✗ Installation verification failed${NC}"
    exit 1
fi

echo ""

# Success message
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}✓ Setup Complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo ""
echo -e "${BLUE}1. Start SAGE Studio:${NC}"
echo -e "   ${CYAN}python -m sage.studio.config.backend.api${NC}"
echo ""
echo -e "${BLUE}2. Open in browser:${NC}"
echo -e "   ${CYAN}http://localhost:8889${NC}"
echo ""
echo -e "${YELLOW}Note: SAGE Studio backend runs on port 8889 (Gateway port)${NC}"
echo -e "${YELLOW}      Frontend will be served by the backend${NC}"
echo ""
