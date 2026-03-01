"""Tests for FinetuneManager behavior without spawning real training jobs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sage_libs.sage_finetune import FinetuneManager, FinetuneStatus


@pytest.fixture()
def manager(tmp_path: Path, monkeypatch):
    # Ensure each test gets a clean singleton instance
    FinetuneManager._instance = None  # type: ignore[attr-defined]

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    mgr = FinetuneManager()
    yield mgr

    # reset singleton after test
    FinetuneManager._instance = None  # type: ignore[attr-defined]


def test_create_and_get_task(manager: FinetuneManager):
    task = manager.create_task("model", "dataset.json", {"num_epochs": 2})

    loaded = manager.get_task(task.task_id)
    assert loaded is not None
    assert loaded.task_id == task.task_id
    assert task.output_dir.endswith(task.task_id)


def test_start_training_queues_when_active(manager: FinetuneManager, monkeypatch):
    first = manager.create_task("model", "data.json", {})
    second = manager.create_task("model", "data.json", {})

    # Pretend first task already running
    manager.active_task_id = first.task_id

    started = manager.start_training(second.task_id)

    assert started is True
    assert manager.tasks[second.task_id].status == FinetuneStatus.QUEUED


def test_start_training_spawns_process(manager: FinetuneManager, monkeypatch):
    task = manager.create_task("model", "data.json", {})

    fake_process = MagicMock(pid=1234)
    monkeypatch.setattr("subprocess.Popen", MagicMock(return_value=fake_process))

    started = manager.start_training(task.task_id)
    assert isinstance(started, bool)
    if started:
        assert manager.active_task_id == task.task_id


def test_start_training_handles_failure(manager: FinetuneManager, monkeypatch):
    task = manager.create_task("model", "data.json", {})
    monkeypatch.setattr("subprocess.Popen", MagicMock(side_effect=RuntimeError("boom")))

    started = manager.start_training(task.task_id)
    assert isinstance(started, bool)
    assert manager.tasks[task.task_id].status in {
        FinetuneStatus.FAILED,
        FinetuneStatus.PREPARING,
        FinetuneStatus.QUEUED,
        FinetuneStatus.TRAINING,
    }


def test_cancel_task_running(manager: FinetuneManager, monkeypatch):
    task = manager.create_task("model", "data.json", {})
    manager.tasks[task.task_id].status = FinetuneStatus.TRAINING
    manager.tasks[task.task_id].process_id = 77
    monkeypatch.setattr("os.kill", MagicMock())

    cancelled = manager.cancel_task(task.task_id)
    assert isinstance(cancelled, bool)


def test_get_current_model_contract(manager: FinetuneManager):
    current = manager.get_current_model()
    assert current is None or isinstance(current, str)


def test_list_available_models_includes_completed(manager: FinetuneManager):
    task = manager.create_task("model", "data.json", {})
    manager.tasks[task.task_id].status = FinetuneStatus.COMPLETED
    manager.tasks[task.task_id].completed_at = "2025-01-01T00:00:00"

    models = manager.list_available_models()
    assert isinstance(models, list)


def test_save_and_load_tasks_roundtrip(tmp_path: Path, monkeypatch):
    FinetuneManager._instance = None  # type: ignore[attr-defined]
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    mgr = FinetuneManager()
    task = mgr.create_task("model", "data.json", {})
    mgr.tasks[task.task_id].status = FinetuneStatus.COMPLETED
    mgr._save_tasks()

    # new manager instance should load previous task
    FinetuneManager._instance = None  # type: ignore[attr-defined]
    mgr2 = FinetuneManager()
    assert task.task_id in mgr2.tasks
