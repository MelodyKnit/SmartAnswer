"""模型角色切换、持久化原子性和主备调用顺序回归。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
from threading import Barrier, Event, RLock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.auth import AuthError, AuthService  # noqa: E402
from study_qb_assistant import bootstrap  # noqa: E402
from study_qb_assistant.bootstrap import build_base_model_provider  # noqa: E402
from study_qb_assistant.llm.management import LlmManagementService  # noqa: E402
from study_qb_assistant.llm.providers import MultiModelProvider, OpenAICompatibleProvider  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.questions.models import ModelAnswer, QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.storage.database import get_session_factory  # noqa: E402
from study_qb_assistant.storage.repositories.llm import LlmRepository  # noqa: E402
from study_qb_assistant.storage.repositories.settings import SettingsRepository  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_runtime_database(monkeypatch):
    """显式路径不能被开发者的外部数据库环境配置覆盖。"""
    monkeypatch.delenv("STQB_DATABASE_URL", raising=False)


@pytest.fixture
def management(tmp_path):
    factory = get_session_factory(tmp_path / "models.sqlite3")
    repository = LlmRepository(factory, SettingsRepository(factory))
    return LlmManagementService(repository, RLock())


def add_model(management, name, *, role="backup", priority=100, status="active"):
    return management.create_model(
        name=name, base_url="https://models.example/v1", model=name,
        role=role, priority=priority, status=status,
    )


def roles(management):
    return {item["name"]: item["role"] for item in management.list_models()}


def test_first_model_becomes_primary_and_new_primary_demotes_previous(management):
    first = add_model(management, "first", priority=900)
    second = add_model(management, "second", role="primary", priority=500)

    assert first["role"] == second["role"] == "primary"
    assert roles(management) == {"first": "backup", "second": "primary"}
    assert management.get_model(first["model_id"])["priority"] == 900


def test_promoting_backup_ignores_primary_priority_and_preserves_backup_order(management):
    first = add_model(management, "first", priority=30)
    promoted = add_model(management, "promoted", priority=9999)
    add_model(management, "early-backup", priority=1)
    add_model(management, "disabled-backup", priority=0, status="inactive")

    management.update_model(promoted["model_id"], {"role": "primary"})

    assert roles(management)["first"] == "backup"
    assert [item.model for item in management.active_models()] == [
        "promoted", "early-backup", "first",
    ]
    management.update_model(first["model_id"], {"priority": 0})
    assert management.list_models()[0]["model_id"] == promoted["model_id"]


def test_inactive_primary_is_skipped_without_changing_its_role(management):
    main = add_model(management, "main", priority=0)
    add_model(management, "late", priority=80)
    add_model(management, "early", priority=10)

    management.update_model(main["model_id"], {"status": "inactive"})

    assert roles(management)["main"] == "primary"
    assert [item.model for item in management.active_models()] == ["early", "late"]
    management.update_model(main["model_id"], {"status": "active"})
    assert [item.model for item in management.active_models()] == ["main", "early", "late"]


def test_demoting_or_deleting_primary_promotes_best_active_backup(management):
    main = add_model(management, "main")
    add_model(management, "inactive", priority=0, status="inactive")
    best = add_model(management, "best", priority=5)
    add_model(management, "later", priority=10)

    management.update_model(main["model_id"], {"role": "backup"})
    assert roles(management)["best"] == "primary"
    management.delete_model(best["model_id"])
    assert roles(management)["later"] == "primary"
    for model in management.list_models():
        management.delete_model(model["model_id"])
    assert management.list_models() == []


def test_only_primary_cannot_be_demoted_and_failed_edit_changes_nothing(management):
    main = add_model(management, "main")

    with pytest.raises(AuthError) as exc:
        management.update_model(main["model_id"], {"role": "backup", "name": "changed"})

    assert exc.value.code == "PRIMARY_MODEL_REQUIRED"
    assert roles(management) == {"main": "primary"}


def test_legacy_disabled_request_still_disables_model(management):
    main = add_model(management, "main")
    disabled = add_model(management, "disabled", role="disabled", status="active")
    assert disabled["role"] == "backup"
    assert disabled["status"] == "inactive"

    management.update_model(main["model_id"], {"role": "disabled", "status": "active"})

    assert management.get_model(main["model_id"])["status"] == "inactive"
    assert roles(management)["main"] == "primary"
    assert management.active_models() == []


@pytest.mark.parametrize("values", [{"role": "other"}, {"priority": -1}, {"priority": 10000}])
def test_invalid_edit_does_not_change_primary(management, values):
    main = add_model(management, "main")
    with pytest.raises(AuthError) as exc:
        management.update_model(main["model_id"], values)
    assert exc.value.code == "INVALID_INPUT"
    assert roles(management) == {"main": "primary"}


def test_restart_repairs_duplicate_primaries_and_preserves_disabled_models(management):
    add_model(management, "first", priority=30)
    add_model(management, "second", priority=5)
    add_model(management, "disabled", priority=0)
    factory = management.repository.session_factory
    with factory() as session:
        session.execute(text("UPDATE llm_models SET role = 'primary'"))
        session.execute(text("UPDATE llm_models SET role = 'disabled' WHERE name = 'disabled'"))
        session.commit()

    restarted = LlmManagementService(management.repository, RLock())

    assert roles(restarted) == {"first": "backup", "second": "primary", "disabled": "backup"}
    assert [item.model for item in restarted.active_models()] == ["second", "first"]
    # 兼容处理重复执行不应再改变管理员选定的唯一主用。
    assert roles(LlmManagementService(management.repository, RLock())) == roles(restarted)


def test_restart_assigns_primary_when_legacy_models_have_only_backups(management):
    add_model(management, "inactive", priority=0, status="inactive")
    add_model(management, "active", priority=80)
    with management.repository.session_factory() as session:
        session.execute(text("UPDATE llm_models SET role = 'backup'"))
        session.commit()

    restarted = LlmManagementService(management.repository, RLock())

    assert roles(restarted) == {"active": "primary", "inactive": "backup"}


def test_promotion_rolls_back_all_role_changes_when_save_fails(management):
    add_model(management, "main")
    backup = add_model(management, "backup")
    record = management.repository.get_llm_model(backup["model_id"])
    broken = replace(record, role="primary", base_url=None)

    with pytest.raises(IntegrityError):
        management.repository.save_llm_model(broken)

    assert roles(management) == {"main": "primary", "backup": "backup"}


def test_editing_name_does_not_restore_stale_primary_role(management, monkeypatch):
    main = add_model(management, "main")
    backup = add_model(management, "backup")
    repository = management.repository
    other = LlmManagementService(
        LlmRepository(repository.session_factory, repository.settings), RLock(),
    )
    save = repository.save_llm_model

    def save_after_switch(record, **kwargs):
        other.update_model(backup["model_id"], {"role": "primary", "priority": 20})
        other.update_model(main["model_id"], {"priority": 0})
        return save(record, **kwargs)

    monkeypatch.setattr(repository, "save_llm_model", save_after_switch)

    updated = management.update_model(main["model_id"], {"name": "renamed"})

    assert updated["name"] == "renamed"
    assert updated["role"] == "backup"
    assert updated["priority"] == 0
    assert roles(management) == {"renamed": "backup", "backup": "primary"}


def test_edit_does_not_recreate_a_concurrently_deleted_model(management, monkeypatch):
    main = add_model(management, "main")
    add_model(management, "backup")
    repository = management.repository
    other = LlmManagementService(
        LlmRepository(repository.session_factory, repository.settings), RLock(),
    )
    save = repository.save_llm_model

    def save_after_delete(record, **kwargs):
        other.delete_model(main["model_id"])
        return save(record, **kwargs)

    monkeypatch.setattr(repository, "save_llm_model", save_after_delete)

    with pytest.raises(AuthError) as exc:
        management.update_model(main["model_id"], {"name": "renamed"})

    assert exc.value.code == "MODEL_NOT_FOUND"
    assert roles(management) == {"backup": "primary"}


def test_slow_refresh_cannot_restore_provider_from_before_primary_switch(management, monkeypatch):
    add_model(management, "main")
    backup = add_model(management, "backup")
    service = AnswerService(LocalQuestionIndex(()))
    service.model_management_service = management
    snapshot_ready, release_snapshot, switched = Event(), Event(), Event()

    def build_stack(*_args, **_kwargs):
        provider = build_base_model_provider(management)
        if not snapshot_ready.is_set():
            snapshot_ready.set()
            assert release_snapshot.wait(timeout=10)
        return provider, None

    def switch_and_refresh():
        management.update_model(backup["model_id"], {"role": "primary"})
        bootstrap.refresh_answer_service(service)
        switched.set()

    monkeypatch.setattr(bootstrap, "build_provider_stack", build_stack)
    with ThreadPoolExecutor(max_workers=2) as executor:
        old_refresh = executor.submit(bootstrap.refresh_answer_service, service)
        try:
            assert snapshot_ready.wait(timeout=10)
            new_refresh = executor.submit(switch_and_refresh)
            # 让较新的切换有机会完成；旧快照随后才恢复执行。
            switched.wait(timeout=0.2)
        finally:
            release_snapshot.set()
        old_refresh.result(timeout=10)
        new_refresh.result(timeout=10)

    assert roles(management) == {"main": "backup", "backup": "primary"}
    assert isinstance(service.model_provider, MultiModelProvider)
    assert service.model_provider.primary.model == "backup"


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_creates_or_promotions_keep_one_primary(management, existing):
    first = add_model(management, "first")
    second = add_model(management, "second")
    records = [management.repository.get_llm_model(item["model_id"]) for item in (first, second)]
    if not existing:
        for item in (first, second):
            management.delete_model(item["model_id"])
    barrier = Barrier(2)

    def promote(record):
        barrier.wait(timeout=10)
        return management.repository.save_llm_model(replace(record, role="primary"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(promote, records))

    configured = management.list_models()
    assert len(configured) == 2
    assert sum(item["role"] == "primary" for item in configured) == 1


@pytest.mark.parametrize("method", [
    "answer", "answer_with_evidence", "verify_answer", "verify_answer_with_evidence",
])
def test_failover_attempts_main_then_backups_and_next_call_starts_at_main(
    management, monkeypatch, method,
):
    add_model(management, "main", priority=9999)
    add_model(management, "last", priority=20)
    add_model(management, "first-backup", priority=10)
    provider = build_base_model_provider(management)
    assert isinstance(provider, MultiModelProvider)
    calls = []
    answer = ModelAnswer("A", "answer", None, 0.9)

    def respond(member, *_args):
        calls.append(member.model)
        if member.model != "last":
            raise RuntimeError("provider unavailable")
        return answer

    monkeypatch.setattr(OpenAICompatibleProvider, method, respond)
    query = QuestionQuery(title="Sample question")
    args = {
        "answer": (query,),
        "answer_with_evidence": (query, ()),
        "verify_answer": (query, answer),
        "verify_answer_with_evidence": (query, (), answer),
    }[method]

    for _ in range(2):
        assert getattr(provider, method)(*args) is answer

    assert calls == ["main", "first-backup", "last"] * 2


def test_healthy_primary_does_not_call_backups_and_all_failures_propagate(management, monkeypatch):
    add_model(management, "main", priority=9999)
    add_model(management, "backup", priority=0)
    provider = build_base_model_provider(management)
    calls = []

    def respond(member, _query):
        calls.append(member.model)
        return ModelAnswer("A", "answer", None, 0.9)

    monkeypatch.setattr(OpenAICompatibleProvider, "answer", respond)
    provider.answer(QuestionQuery(title="Sample question"))
    assert calls == ["main"]

    def fail(member, _query):
        raise RuntimeError(member.model)

    monkeypatch.setattr(OpenAICompatibleProvider, "answer", fail)
    with pytest.raises(RuntimeError, match="backup"):
        provider.answer(QuestionQuery(title="Sample question"))


def test_api_switch_refreshes_running_provider_and_preserves_auth_contract(tmp_path):
    database = tmp_path / "api.sqlite3"
    platform = PlatformServices(database)
    platform.settings.set_llm_runtime_config({"web_search_provider": "none", "web_search_configs": "[]"})
    auth = AuthService(database)
    service = AnswerService(LocalQuestionIndex(()))
    service.runtime_settings_service = platform.settings
    service.model_management_service = platform.llm
    app = create_app(service, auth_service=auth, platform_services=platform, require_auth=True)
    with TestClient(app) as client:
        denied = client.post("/api/v1/llm-models", json={})
        assert denied.status_code == 401
        client.post("/api/v1/auth/register", json={"username": "owner", "password": "test-pass-123"})
        login = client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "test-pass-123"},
        )
        headers = {"Authorization": "Bearer " + login.json()["token"]}

        def create(name, **fields):
            response = client.post(
                "/api/v1/llm-models", headers=headers,
                json={"name": name, "base_url": "https://models.example/v1", "model": name, **fields},
            )
            assert response.status_code == 200
            return response.json()["model"]

        main = create("main", priority=40)
        invalid = client.patch(
            f"/api/v1/llm-models/{main['model_id']}", headers=headers, json={"role": "backup"},
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "PRIMARY_MODEL_REQUIRED"
        backup = create("backup", priority=900)
        promoted = client.patch(
            f"/api/v1/llm-models/{backup['model_id']}", headers=headers,
            json={"role": "primary"},
        )
        assert promoted.status_code == 200
        assert isinstance(service.model_provider, MultiModelProvider)
        assert [member.model for member in service.model_provider.members] == ["backup", "main"]
        listed = client.get("/api/v1/llm-models", headers=headers).json()["models"]
        assert [item["role"] for item in listed] == ["primary", "backup"]
        assert all(not item["api_key"] for item in listed)
        stopped = client.patch(
            f"/api/v1/llm-models/{backup['model_id']}", headers=headers,
            json={"status": "inactive"},
        )
        assert stopped.status_code == 200
        assert service.model_provider.model == "main"
        deleted = client.delete(f"/api/v1/llm-models/{backup['model_id']}", headers=headers)
        assert deleted.status_code == 200
        assert client.get("/api/v1/llm-models", headers=headers).json()["models"][0]["role"] == "primary"
