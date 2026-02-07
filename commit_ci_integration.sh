#!/bin/bash
# 快速提交 CI/CD 集成更改

set -e

echo "🚀 准备提交 CI/CD 集成..."
echo ""

# 显示将要提交的文件
echo "📁 将要提交的文件:"
echo ""
git status --short \
    .github/workflows/ci-test.yml \
    .github/workflows/README.md \
    tests/integration/test_studio_llm_integration.py \
    CHANGELOG.md \
    verify_ci_setup.sh \
    CI_INTEGRATION_SUMMARY.md \
    2>/dev/null || echo "  (某些文件可能不存在)"

echo ""
echo "📝 提交信息:"
echo "  ci: add CI/CD workflows for automated testing"
echo ""
echo "详细说明:"
echo "  - Add CI test workflow with unit/integration/e2e tests"
echo "  - Add pytest integration tests for Studio LLM startup"
echo "  - Add workflow documentation and verification script"
echo "  - Update CHANGELOG.md"
echo ""

# 确认
read -p "确认提交？(y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 1
fi

# 添加文件
echo "📦 添加文件..."
git add \
    .github/workflows/ci-test.yml \
    .github/workflows/README.md \
    tests/integration/test_studio_llm_integration.py \
    CHANGELOG.md \
    verify_ci_setup.sh \
    CI_INTEGRATION_SUMMARY.md \
    2>/dev/null || true

# 提交
echo "💾 创建提交..."
git commit -m "ci: add CI/CD workflows for automated testing

- Add CI test workflow (.github/workflows/ci-test.yml)
  - Unit tests on Python 3.10 and 3.11
  - Integration tests with CPU backend
  - E2E tests for LLM integration
  - Code quality checks (Ruff, Mypy)

- Add integration test (tests/integration/test_studio_llm_integration.py)
  - Tests sageLLM CPU backend engine script generation
  - Validates script content and configuration
  - Checks Gateway detection logic
  - Supports environment variable configuration for CI

- Add documentation
  - Workflow usage guide (.github/workflows/README.md)
  - CI integration summary (CI_INTEGRATION_SUMMARY.md)
  - Configuration verification script (verify_ci_setup.sh)

- Update CHANGELOG.md with new features"

echo ""
echo "✅ 提交完成！"
echo ""
echo "下一步:"
echo "  git push origin main-dev"
echo ""
echo "推送后，GitHub Actions 将自动运行测试。"
echo "可以在以下位置查看："
echo "  https://github.com/intellistream/sage-studio/actions"
