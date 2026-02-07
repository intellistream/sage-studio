#!/bin/bash
# 测试 Studio restart 修复

echo "=== 测试 Studio Restart 修复 ==="
echo ""

echo "1. 检查当前端口占用情况..."
echo "端口 9001 (LLM):"
lsof -i :9001 | head -2 || echo "  空闲"
echo "端口 5173 (Frontend):"
lsof -i :5173 | head -2 || echo "  空闲"
echo "端口 8889 (Gateway):"
lsof -i :8889 | head -2 || echo "  空闲"
echo ""

echo "2. 停止所有 Studio 相关服务..."
sage studio stop --all
sleep 2
echo ""

echo "3. 清理僵尸进程（如果存在）..."
pkill -9 -f "sage-llm serve-engine" 2>/dev/null
sleep 1
echo ""

echo "4. 验证端口已释放..."
if lsof -i :9001 | grep -q LISTEN; then
    echo "  ❌ 端口 9001 仍被占用"
    lsof -i :9001
    exit 1
else
    echo "  ✅ 端口 9001 已释放"
fi
echo ""

echo "5. 测试 restart 命令..."
sage studio restart --yes
echo ""

echo "6. 等待 10 秒后检查服务状态..."
sleep 10
sage studio status
echo ""

echo "7. 检查 LLM 引擎日志..."
if [ -f /tmp/sage-studio-engine.log ]; then
    echo "最后 20 行日志:"
    tail -20 /tmp/sage-studio-engine.log
else
    echo "  日志文件不存在"
fi

echo ""
echo "=== 测试完成 ==="
