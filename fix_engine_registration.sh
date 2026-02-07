#!/bin/bash
# 修复引擎注册问题的临时脚本

echo "=== 引擎注册修复脚本 ==="

# 1. 重启Studio（会启动Gateway和引擎）
echo "1. 重新启动Studio..."
cd /home/shuhao/sage-studio
sage studio start --yes &

# 2. 等待服务启动
echo "2. 等待服务启动（60秒）..."
sleep 60

# 3. 检查Gateway状态
echo "3. 检查Gateway状态..."
curl -s http://localhost:8889/health | jq '.'

# 4. 检查引擎状态
echo "4. 检查引擎状态（9001）..."
curl -s http://localhost:9001/health | jq '.'

# 5. 重启Gateway以使用正确的引擎端口
echo "5. 配置Gateway使用正确的引擎端口..."
# 杀死Gateway
pkill -f "sagellm-gateway"
sleep 2

# 以正确的配置启动Gateway（指向9001端口的引擎）
SAGE_LLM_ENGINE_URL=http://localhost:9001 sagellm-gateway --host 0.0.0.0 --port 8889 > ~/.local/state/sage/logs/gateway.log 2>&1 &

echo "6. 等待Gateway重启..."
sleep 10

# 7. 测试聊天
echo "7. 测试聊天功能..."
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/guest | jq -r '.access_token')
curl -s -X POST http://localhost:8080/api/chat/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"messages":[{"role":"user","content":"你好"}],"model":"Qwen/Qwen2.5-0.5B-Instruct","session_id":"test","stream":false}' | head -200

echo ""
echo "=== 修复complete！请刷新浏览器并测试聊天 ==="
