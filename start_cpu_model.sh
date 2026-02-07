#!/bin/bash
# SAGE Studio CPU 模型快速启动脚本

set -e

echo "===================================="
echo "  SAGE Studio CPU 模型启动脚本"
echo "===================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查是否安装了 SAGE
if ! command -v sage &> /dev/null; then
    echo -e "${RED}错误: SAGE 未安装或未在 PATH 中${NC}"
    echo "请先安装 SAGE: https://github.com/intellistream/SAGE"
    exit 1
fi

# 检查端口 8901 是否被占用
if lsof -Pi :8901 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}警告: 端口 8901 已被占用${NC}"
    echo "正在检查是否已有模型运行..."
    
    # 尝试获取模型信息
    if curl -s http://localhost:8901/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 检测到运行中的模型服务${NC}"
        echo ""
        echo "您可以在 Studio 中选择已运行的模型。"
        exit 0
    else
        echo -e "${RED}端口被占用但无法访问服务，请手动检查${NC}"
        exit 1
    fi
fi

# 模型选项
echo "请选择要启动的模型："
echo ""
echo "  1) Qwen/Qwen2.5-0.5B-Instruct  (推荐⭐ - 最快，~2GB RAM)"
echo "  2) TinyLlama/TinyLlama-1.1B-Chat-v1.0  (轻量，~2.5GB RAM)"
echo "  3) Qwen/Qwen2.5-1.5B-Instruct  (平衡，~4GB RAM)"
echo "  4) Qwen/Qwen2.5-3B-Instruct  (更好质量，~8GB RAM)"
echo "  5) 自定义模型"
echo ""
read -p "请输入选项 [1-5，默认1]: " choice
choice=${choice:-1}

case $choice in
    1)
        MODEL="Qwen/Qwen2.5-0.5B-Instruct"
        ;;
    2)
        MODEL="TinyLlama/TinyLlama-1.1B-Chat-v1.0"
        ;;
    3)
        MODEL="Qwen/Qwen2.5-1.5B-Instruct"
        ;;
    4)
        MODEL="Qwen/Qwen2.5-3B-Instruct"
        ;;
    5)
        read -p "请输入模型名称（HuggingFace 格式）: " MODEL
        ;;
    *)
        echo -e "${RED}无效的选项，使用默认模型${NC}"
        MODEL="Qwen/Qwen2.5-0.5B-Instruct"
        ;;
esac

echo ""
echo -e "${GREEN}准备启动模型: $MODEL${NC}"
echo ""
echo "首次运行会自动从 HuggingFace 下载模型（约 2-10 分钟）"
echo "后续启动将直接使用缓存的模型文件"
echo ""
read -p "按 Enter 继续，或 Ctrl+C 取消..."

# 启动模型
echo ""
echo "正在启动模型..."
echo "命令: sage llm engine start $MODEL --engine-kind llm --port 8901"
echo ""

# 使用 nohup 在后台运行，输出重定向到日志文件
LOG_FILE="$HOME/.local/state/sage/logs/cpu_model_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname "$LOG_FILE")"

nohup sage llm engine start "$MODEL" --engine-kind llm --port 8901 > "$LOG_FILE" 2>&1 &
PID=$!

echo -e "${GREEN}✅ 模型启动中... (PID: $PID)${NC}"
echo "日志文件: $LOG_FILE"
echo ""
echo "等待服务就绪（约 10-30 秒）..."

# 等待服务启动（最多等待 60 秒）
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:8901/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 模型服务已就绪！${NC}"
        echo ""
        echo "================================================"
        echo "  模型信息:"
        echo "  - 模型: $MODEL"
        echo "  - 地址: http://localhost:8901/v1"
        echo "  - 状态: 运行中 (PID: $PID)"
        echo "================================================"
        echo ""
        echo "下一步："
        echo "  1. 刷新 SAGE Studio 页面 (http://localhost:5173)"
        echo "  2. 点击右上角的模型选择器"
        echo "  3. 选择 '$MODEL' 模型（会显示绿色状态指示灯）"
        echo "  4. 开始对话或创建 Pipeline"
        echo ""
        echo "停止模型: sage llm engine stop <engine-id>"
        echo "查看模型: sage llm engine list"
        echo ""
        exit 0
    fi
    
    # 检查进程是否还在运行
    if ! kill -0 $PID 2>/dev/null; then
        echo -e "${RED}❌ 模型启动失败${NC}"
        echo "请查看日志: $LOG_FILE"
        tail -20 "$LOG_FILE"
        exit 1
    fi
    
    sleep 2
    WAITED=$((WAITED + 2))
    echo -n "."
done

echo ""
echo -e "${YELLOW}⚠️  服务启动超时，但进程仍在运行${NC}"
echo "请稍后手动检查: curl http://localhost:8901/health"
echo "或查看日志: tail -f $LOG_FILE"
