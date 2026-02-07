#!/usr/bin/env python3
"""
测试 Studio 模型切换功能

验证修复后的功能：
1. Studio 启动时自动启动默认 LLM 引擎
2. 模型切换真正生效（启动新引擎）
"""

import time
import requests
import subprocess
import sys


def test_llm_gateway_running():
    """测试 LLM Gateway 是否运行"""
    print("🔍 测试 1: 检查 LLM Gateway 是否运行...")
    try:
        response = requests.get("http://localhost:8001/v1/models", timeout=2)
        if response.status_code == 200:
            models = response.json().get("data", [])
            if models:
                print(f"✅ LLM Gateway 运行中，当前模型: {models[0].get('id')}")
                return True
            else:
                print("❌ LLM Gateway 运行但无引擎")
                return False
        else:
            print(f"❌ LLM Gateway 响应异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 LLM Gateway: {e}")
        return False


def test_studio_backend_running():
    """测试 Studio Backend 是否运行"""
    print("\n🔍 测试 2: 检查 Studio Backend 是否运行...")
    try:
        response = requests.get("http://localhost:8080/health", timeout=2)
        if response.status_code == 200:
            print("✅ Studio Backend 运行中")
            return True
        else:
            print(f"❌ Studio Backend 响应异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 Studio Backend: {e}")
        return False


def test_model_selection():
    """测试模型选择功能"""
    print("\n🔍 测试 3: 测试模型选择功能...")
    
    # 获取 guest token
    try:
        auth_response = requests.post("http://localhost:8080/api/auth/guest", timeout=5)
        if auth_response.status_code != 200:
            print(f"❌ 获取 guest token 失败: {auth_response.status_code}")
            return False
        
        token = auth_response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # 测试选择本地模型
        select_data = {
            "model_name": "Qwen/Qwen2.5-0.5B-Instruct",
            "base_url": "http://localhost:8001/v1"
        }
        
        print(f"   尝试切换到模型: {select_data['model_name']}")
        response = requests.post(
            "http://localhost:8080/api/llm/select",
            json=select_data,
            headers=headers,
            timeout=60  # 给足够时间启动引擎
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 模型选择成功: {result.get('message')}")
            if result.get('engine_started'):
                print("   ℹ️  新引擎已启动")
            return True
        else:
            print(f"❌ 模型选择失败: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 模型选择测试失败: {e}")
        return False


def test_chat_functionality():
    """测试聊天功能"""
    print("\n🔍 测试 4: 测试聊天功能...")
    
    try:
        # 获取 guest token
        auth_response = requests.post("http://localhost:8080/api/auth/guest", timeout=5)
        token = auth_response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # 发送测试消息
        chat_data = {
            "message": "Hello, this is a test.",
            "model": "sage-default"
        }
        
        print("   发送测试消息...")
        response = requests.post(
            "http://localhost:8080/api/chat/message",
            json=chat_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("content", "")
            print(f"✅ 聊天功能正常，收到回复: {content[:50]}...")
            return True
        else:
            print(f"❌ 聊天失败: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 聊天测试失败: {e}")
        return False


def main():
    """主测试流程"""
    print("=" * 60)
    print("SAGE Studio 模型切换功能测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1: LLM Gateway
    results.append(("LLM Gateway", test_llm_gateway_running()))
    
    # 测试 2: Studio Backend
    results.append(("Studio Backend", test_studio_backend_running()))
    
    # 测试 3: 模型选择
    results.append(("模型选择", test_model_selection()))
    
    # 等待引擎就绪
    print("\n⏳ 等待5秒让引擎完全就绪...")
    time.sleep(5)
    
    # 测试 4: 聊天功能
    results.append(("聊天功能", test_chat_functionality()))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:20s} {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！模型切换功能正常工作。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
