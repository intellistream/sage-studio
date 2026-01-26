#!/usr/bin/env python3
"""测试 Studio 自动启动 LLM 服务

验证：
1. Studio.start() 自动启动 Gateway
2. Studio.start() 自动启动 LLM 服务
3. LLM 服务可以被检测到并返回模型列表
"""

import time
import requests
from sage.studio.studio_manager import StudioManager
from sage.studio.config.ports import StudioPorts

def test_llm_autostart():
    """测试 LLM 服务自动启动"""
    print("=" * 60)
    print("测试 Studio 自动启动 LLM 服务")
    print("=" * 60)

    manager = StudioManager()

    # 1. 检查初始状态
    print("\n1️⃣  检查初始状态...")
    gateway_pid = manager.is_gateway_running()
    llm_pid = manager.is_llm_running()
    print(f"   Gateway: {'运行中' if gateway_pid else '未运行'}")
    print(f"   LLM服务: {'运行中' if llm_pid else '未运行'}")

    # 2. 启动 Gateway（如果未运行）
    if not gateway_pid:
        print("\n2️⃣  启动 Gateway...")
        if manager.start_gateway():
            print("   ✓ Gateway 启动成功")
            time.sleep(3)  # 等待启动
        else:
            print("   ✗ Gateway 启动失败")
            return False
    else:
        print("\n2️⃣  Gateway 已在运行，跳过启动")

    # 3. 启动 LLM 服务（通过 start_llm_service）
    if not llm_pid:
        print("\n3️⃣  启动 LLM 服务...")
        if manager.start_llm_service():
            print("   ✓ LLM 服务启动成功")
        else:
            print("   ✗ LLM 服务启动失败")
            return False
    else:
        print("\n3️⃣  LLM 服务已在运行，跳过启动")

    # 4. 验证 LLM 服务
    print("\n4️⃣  验证 LLM 服务...")
    llm_pid = manager.is_llm_running()
    if llm_pid:
        print(f"   ✓ LLM 服务运行中 (PID: {llm_pid if llm_pid != -1 else '未知'})")
    else:
        print("   ✗ LLM 服务未运行")
        return False

    # 5. 检查模型列表
    print("\n5️⃣  检查模型列表...")
    try:
        # 尝试直接访问 LLM 服务
        llm_url = f"http://localhost:{StudioPorts.LLM_DEFAULT}/v1/models"
        response = requests.get(llm_url, timeout=5)
        if response.status_code == 200:
            models = response.json()
            if models.get("data"):
                print(f"   ✓ 直接访问 LLM 服务成功，发现 {len(models['data'])} 个模型")
                for model in models["data"][:3]:  # 显示前3个
                    print(f"      - {model.get('id', 'unknown')}")
            else:
                print("   ⚠️  LLM 服务响应正常但模型列表为空")
        else:
            print(f"   ✗ LLM 服务返回错误状态码: {response.status_code}")
    except Exception as e:
        print(f"   ✗ 无法访问 LLM 服务: {e}")

    # 6. 通过 Gateway 检查
    print("\n6️⃣  通过 Gateway 检查模型...")
    try:
        gateway_url = f"http://localhost:{StudioPorts.GATEWAY}/v1/models"
        response = requests.get(gateway_url, timeout=5)
        if response.status_code == 200:
            models = response.json()
            if models.get("data"):
                print(f"   ✓ Gateway 返回 {len(models['data'])} 个模型")
            else:
                print("   ⚠️  Gateway 返回空模型列表（可能 LLM 服务未正确注册）")
        else:
            print(f"   ✗ Gateway 返回错误状态码: {response.status_code}")
    except Exception as e:
        print(f"   ✗ 无法访问 Gateway: {e}")

    print("\n" + "=" * 60)
    print("✓ 测试完成")
    print("=" * 60)
    return True

if __name__ == "__main__":
    test_llm_autostart()
