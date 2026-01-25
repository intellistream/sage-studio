#!/usr/bin/env python3
"""验证 Fine-tune 功能集成是否正常

Usage:
    python verify_finetune_integration.py
"""

import sys


def test_import():
    """测试导入"""
    print("=" * 60)
    print("1. 测试导入")
    print("=" * 60)

    try:
        from sage_libs.sage_finetune import (
            FinetuneManager,
            FinetuneStatus,
            FinetuneTask,
            finetune_manager,
        )
        print("✓ 所有组件导入成功")
        print(f"  - FinetuneManager: {FinetuneManager}")
        print(f"  - FinetuneStatus: {FinetuneStatus}")
        print(f"  - FinetuneTask: {FinetuneTask}")
        print(f"  - finetune_manager: {finetune_manager}")
        return True
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        return False


def test_manager_singleton():
    """测试单例模式"""
    print("\n" + "=" * 60)
    print("2. 测试单例模式")
    print("=" * 60)

    try:
        from sage_libs.sage_finetune import FinetuneManager, finetune_manager

        # 创建新实例应该返回同一个对象
        manager1 = FinetuneManager()
        manager2 = FinetuneManager()

        if manager1 is manager2 is finetune_manager:
            print("✓ 单例模式正常工作")
            print(f"  - manager1 == manager2: {manager1 is manager2}")
            print(f"  - manager1 == finetune_manager: {manager1 is finetune_manager}")
            return True
        else:
            print("✗ 单例模式失败：创建了多个实例")
            return False
    except Exception as e:
        print(f"✗ 单例测试失败: {e}")
        return False


def test_task_lifecycle():
    """测试任务生命周期"""
    print("\n" + "=" * 60)
    print("3. 测试任务生命周期")
    print("=" * 60)

    try:
        from sage_libs.sage_finetune import FinetuneStatus, finetune_manager

        # 创建任务
        task = finetune_manager.create_task(
            model_name="test-model",
            dataset_path="test.jsonl",
            config={"num_epochs": 3},
        )
        print(f"✓ 创建任务: {task.task_id}")
        print(f"  - 状态: {task.status}")
        print(f"  - 模型: {task.model_name}")

        # 获取任务
        retrieved_task = finetune_manager.get_task(task.task_id)
        if retrieved_task and retrieved_task.task_id == task.task_id:
            print(f"✓ 获取任务成功: {retrieved_task.task_id}")
        else:
            print("✗ 获取任务失败")
            return False

        # 列出任务
        tasks = finetune_manager.list_tasks()
        print(f"✓ 列出任务: 共 {len(tasks)} 个任务")

        # 添加日志
        finetune_manager.add_task_log(task.task_id, "测试日志")
        task = finetune_manager.get_task(task.task_id)
        if task.logs:
            print(f"✓ 添加日志成功: {len(task.logs)} 条日志")

        # 更新进度
        finetune_manager.update_task_progress(
            task.task_id, 50.0, {"loss": 0.5}
        )
        task = finetune_manager.get_task(task.task_id)
        print(f"✓ 更新进度: {task.progress}%")

        # 删除任务
        success = finetune_manager.delete_task(task.task_id)
        if success:
            print(f"✓ 删除任务成功: {task.task_id}")
        else:
            print("✗ 删除任务失败")
            return False

        return True
    except Exception as e:
        print(f"✗ 生命周期测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_status_enum():
    """测试状态枚举"""
    print("\n" + "=" * 60)
    print("4. 测试状态枚举")
    print("=" * 60)

    try:
        from sage_libs.sage_finetune import FinetuneStatus

        expected_statuses = [
            "pending",
            "preparing",
            "training",
            "completed",
            "failed",
            "cancelled",
            "queued",
        ]

        actual_statuses = [s.value for s in FinetuneStatus]

        if actual_statuses == expected_statuses:
            print("✓ 所有状态枚举正确")
            for status in FinetuneStatus:
                print(f"  - {status.name}: {status.value}")
            return True
        else:
            print("✗ 状态枚举不匹配")
            print(f"  期望: {expected_statuses}")
            print(f"  实际: {actual_statuses}")
            return False
    except Exception as e:
        print(f"✗ 状态枚举测试失败: {e}")
        return False


def test_api_integration():
    """测试 API 集成"""
    print("\n" + "=" * 60)
    print("5. 测试 API 集成")
    print("=" * 60)

    try:
        import sys
        from pathlib import Path

        # 添加 Studio src 到路径
        studio_src = Path(__file__).parent / "src"
        sys.path.insert(0, str(studio_src))

        from fastapi.testclient import TestClient
        from sage.studio.config.backend.api import app

        client = TestClient(app)

        # 测试列出任务
        response = client.get("/api/finetune/tasks")
        if response.status_code == 200:
            print(f"✓ GET /api/finetune/tasks: {response.status_code}")
            print(f"  - 返回任务数: {len(response.json())}")
        else:
            print(f"✗ GET /api/finetune/tasks 失败: {response.status_code}")
            return False

        # 测试创建任务
        create_response = client.post(
            "/api/finetune/create",
            json={
                "model_name": "Qwen/Qwen2.5-7B-Instruct",
                "dataset_file": "/tmp/test.jsonl",
                "num_epochs": 3,
            },
        )
        if create_response.status_code == 200:
            task = create_response.json()
            print(f"✓ POST /api/finetune/create: {create_response.status_code}")
            print(f"  - 创建任务: {task['task_id']}")
            print(f"  - 状态: {task['status']}")

            # 测试获取任务详情
            task_id = task["task_id"]
            detail_response = client.get(f"/api/finetune/tasks/{task_id}")
            if detail_response.status_code == 200:
                print(f"✓ GET /api/finetune/tasks/{task_id}: {detail_response.status_code}")
            else:
                print(f"✗ 获取任务详情失败: {detail_response.status_code}")
        else:
            print(f"✗ POST /api/finetune/create 失败: {create_response.status_code}")
            print(f"  - 错误: {create_response.text}")
            return False

        return True
    except Exception as e:
        print(f"✗ API 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "Fine-tune 功能集成验证" + " " * 24 + "║")
    print("╚" + "=" * 58 + "╝")

    results = []

    # 运行测试
    results.append(("导入测试", test_import()))
    results.append(("单例模式测试", test_manager_singleton()))
    results.append(("任务生命周期测试", test_task_lifecycle()))
    results.append(("状态枚举测试", test_status_enum()))
    results.append(("API 集成测试", test_api_integration()))

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status:8} - {name}")

    print("-" * 60)
    print(f"总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！Fine-tune 功能集成成功。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查日志。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
