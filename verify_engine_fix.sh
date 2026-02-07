#!/bin/bash
# 验证引擎启动和健康检查修复

set -e

echo "===== 验证引擎修复脚本 ====="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 检查服务是否运行
echo "🔍 步骤 1: 检查服务状态..."
if ! pgrep -f "sage-llm gateway" > /dev/null; then
    echo -e "${RED}❌ Gateway 未运行${NC}"
    echo "请先启动: sage studio start"
    exit 1
fi
echo -e "${GREEN}✅ Gateway 运行中${NC}"

# 2. 检查引擎进程
echo ""
echo "🔍 步骤 2: 检查引擎进程..."
if ! pgrep -f "sage-llm serve-engine" > /dev/null; then
    echo -e "${RED}❌ 引擎进程未找到${NC}"
    echo "引擎可能还在启动中，等待30秒..."
    sleep 30
    if ! pgrep -f "sage-llm serve-engine" > /dev/null; then
        echo -e "${RED}❌ 引擎启动失败${NC}"
        echo "检查日志: tail -f /tmp/sage-studio-engine.log"
        exit 1
    fi
fi
echo -e "${GREEN}✅ 引擎进程运行中${NC}"

# 3. 检查引擎健康端点
echo ""
echo "🔍 步骤 3: 检查引擎健康端点..."
HEALTH_RESPONSE=$(curl -s http://localhost:9001/health 2>&1 || echo "FAILED")

if [[ "$HEALTH_RESPONSE" == "FAILED" ]] || [[ -z "$HEALTH_RESPONSE" ]]; then
    echo -e "${YELLOW}⚠️  引擎健康端点还未响应，可能还在加载模型...${NC}"
    echo "等待最多60秒..."
    
    for i in {1..12}; do
        sleep 5
        HEALTH_RESPONSE=$(curl -s http://localhost:9001/health 2>&1 || echo "")
        if [[ -n "$HEALTH_RESPONSE" ]] && echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
            echo -e "${GREEN}✅ 引擎健康端点响应正常${NC}"
            break
        fi
        echo "   等待中... ($((i*5))s)"
    done
    
    if [[ -z "$HEALTH_RESPONSE" ]] || ! echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
        echo -e "${RED}❌ 引擎健康检查超时${NC}"
        echo "检查日志: tail -f /tmp/sage-studio-engine.log"
        exit 1
    fi
else
    echo -e "${GREEN}✅ 引擎健康端点响应正常${NC}"
fi

echo "引擎响应: $HEALTH_RESPONSE"

# 4. 检查 Control Plane 引擎注册状态
echo ""
echo "🔍 步骤 4: 检查 Control Plane 引擎状态..."
ENGINE_STATUS=$(curl -s http://localhost:8001/v1/management/engines 2>&1)

if [[ -z "$ENGINE_STATUS" ]]; then
    echo -e "${RED}❌ 无法连接到 Control Plane 管理API${NC}"
    exit 1
fi

# 解析引擎状态
ENGINE_COUNT=$(echo "$ENGINE_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['total'])" 2>/dev/null || echo "0")
HEALTHY_COUNT=$(echo "$ENGINE_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['healthy'])" 2>/dev/null || echo "0")

echo "注册的引擎数量: $ENGINE_COUNT"
echo "健康的引擎数量: $HEALTHY_COUNT"

if [[ "$ENGINE_COUNT" == "0" ]]; then
    echo -e "${RED}❌ 没有注册的引擎${NC}"
    echo "引擎可能未成功注册到 Control Plane"
    exit 1
fi

echo -e "${GREEN}✅ 引擎已注册到 Control Plane${NC}"

if [[ "$HEALTHY_COUNT" == "0" ]]; then
    echo -e "${YELLOW}⚠️  引擎未标记为健康，等待健康检查周期...${NC}"
    echo "健康检查每10秒运行一次，等待20秒..."
    sleep 20
    
    ENGINE_STATUS=$(curl -s http://localhost:8001/v1/management/engines 2>&1)
    HEALTHY_COUNT=$(echo "$ENGINE_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['healthy'])" 2>/dev/null || echo "0")
    
    if [[ "$HEALTHY_COUNT" == "0" ]]; then
        echo -e "${RED}❌ 引擎健康检查失败${NC}"
        echo "Control Plane 无法访问引擎健康端点"
        echo ""
        echo "调试信息:"
        echo "$ENGINE_STATUS" | python3 -m json.tool 2>/dev/null || echo "$ENGINE_STATUS"
        exit 1
    fi
fi

echo -e "${GREEN}✅ 引擎状态健康${NC}"

# 5. 测试聊天功能
echo ""
echo "🔍 步骤 5: 测试聊天功能..."

CHAT_RESPONSE=$(curl -s -X POST http://localhost:8889/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' 2>&1)

if echo "$CHAT_RESPONSE" | grep -q "error\|failed\|500"; then
    echo -e "${RED}❌ 聊天功能测试失败${NC}"
    echo "响应: $CHAT_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ 聊天功能正常${NC}"
echo "响应预览: $(echo "$CHAT_RESPONSE" | head -c 100)..."

# 全部通过
echo ""
echo "==========================================="
echo -e "${GREEN}🎉 所有测试通过！引擎修复生效。${NC}"
echo "==========================================="
echo ""
echo "摘要:"
echo "  - 引擎进程: 运行中"
echo "  - 引擎健康端点: 正常"
echo "  - Control Plane 注册: 成功"
echo "  - 引擎健康状态: 健康"
echo "  - 聊天功能: 正常"
echo ""
echo "您现在可以通过 Studio 界面进行聊天测试。"
echo "访问: http://localhost:5173"
