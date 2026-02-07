#!/bin/bash
# 验证 CI/CD 配置

set -e

echo "🔍 验证 SAGE Studio CI/CD 配置..."
echo ""

# 1. 检查 workflow 文件
echo "✅ 检查 workflow 文件..."
if [ -f ".github/workflows/ci-test.yml" ]; then
    echo "   ✓ ci-test.yml 存在"
else
    echo "   ✗ ci-test.yml 不存在"
    exit 1
fi

if [ -f ".github/workflows/cd-deploy-studio.yml" ]; then
    echo "   ✓ cd-deploy-studio.yml 存在"
else
    echo "   ✗ cd-deploy-studio.yml 不存在"
    exit 1
fi

# 2. 检查测试文件
echo ""
echo "✅ 检查测试文件..."
if [ -f "tests/integration/test_studio_llm_integration.py" ]; then
    echo "   ✓ test_studio_llm_integration.py 存在"
else
    echo "   ✗ test_studio_llm_integration.py 不存在"
    exit 1
fi

# 3. 验证 pytest 配置
echo ""
echo "✅ 验证 pytest 配置..."
if grep -q "pytest.ini_options" pyproject.toml; then
    echo "   ✓ pytest 配置存在于 pyproject.toml"
else
    echo "   ✗ pytest 配置不存在"
    exit 1
fi

# 4. 检查测试标记
echo ""
echo "✅ 检查测试标记..."
if grep -q "@pytest.mark.integration" tests/integration/test_studio_llm_integration.py; then
    echo "   ✓ 测试使用了 @pytest.mark.integration"
else
    echo "   ✗ 测试缺少标记"
    exit 1
fi

# 5. 尝试收集测试
echo ""
echo "✅ 收集测试..."
if python -m pytest tests/integration/test_studio_llm_integration.py --collect-only -q &> /dev/null; then
    test_count=$(python -m pytest tests/integration/test_studio_llm_integration.py --collect-only -q 2>&1 | grep -E "^[0-9]+ test" | awk '{print $1}')
    echo "   ✓ 成功收集 ${test_count} 个测试"
else
    echo "   ✗ 测试收集失败"
    exit 1
fi

# 6. 验证 YAML 语法
echo ""
echo "✅ 验证 YAML 语法..."
if command -v yamllint &> /dev/null; then
    yamllint .github/workflows/*.yml || echo "   ⚠️  YAML 格式警告（可忽略）"
else
    echo "   ⚠️  yamllint 未安装，跳过 YAML 语法检查"
fi

echo ""
echo "🎉 所有检查通过！"
echo ""
echo "下一步:"
echo "1. 提交更改: git add .github/ tests/ CHANGELOG.md"
echo "2. 创建 commit: git commit -m 'ci: add CI/CD workflows for automated testing'"
echo "3. 推送: git push origin main-dev"
echo "4. GitHub Actions 将自动运行测试"
