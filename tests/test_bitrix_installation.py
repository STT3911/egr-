"""Installation regressions. All Bitrix calls and database writes are mocked."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from app.bitrix import admin, install
from app.bitrix.models import AppSettings
from app.bitrix.security import BITRIX_FRAME_POLICY, application_origin, portal_domain

PROD = "https://company.tenders.by"
DEV = "https://test.tendex.by"
PORTAL = "autocrm.bitrix24.by"
PATH = install.WEBHOOK_HANDLER_PATH


def mock_rest(monkeypatch, bindings, *, fail_method=None, unbind_result=None):
    calls = []
    real_client = httpx.AsyncClient

    def handle(request):
        method = request.url.path.split("/")[-1].removesuffix(".json")
        payload = json.loads(request.content)
        assert request.url.host == PORTAL
        calls.append((method, payload))
        if method == fail_method:
            return httpx.Response(200, json={"error": "ACCESS_DENIED"})
        result = bindings if method == "event.get" else True
        if method == "event.unbind":
            result = unbind_result if unbind_result is not None else {"count": 1}
        return httpx.Response(200, json={"result": result})

    monkeypatch.setattr(install.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(install.settings, "APP_URL", PROD)
    return calls


def bindings_at(origin):
    return [{"event": event, "handler": origin + PATH, "auth_type": "0", "offline": 0}
            for event in install.COMPANY_EVENTS]


def test_register_prod_before_removing_exact_dev_handlers(monkeypatch):
    unrelated = {"event": "ONCRMCOMPANYADD", "handler": DEV + "/other", "offline": 0}
    calls = mock_rest(monkeypatch, bindings_at(DEV) + [unrelated])
    asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert [m for m, _ in calls] == ["event.get", "event.bind", "event.bind", "event.unbind", "event.unbind"]
    assert all(p["handler"] == PROD + PATH for m, p in calls if m == "event.bind")
    assert all(p["handler"] == DEV + PATH and p["auth_type"] == "0" for m, p in calls if m == "event.unbind")


def test_already_registered_handlers_are_idempotent(monkeypatch):
    calls = mock_rest(monkeypatch, bindings_at(PROD))
    asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert [m for m, _ in calls] == ["event.get"]


def test_failed_replacement_keeps_old_handlers(monkeypatch):
    calls = mock_rest(monkeypatch, bindings_at(DEV), fail_method="event.bind")
    with pytest.raises(RuntimeError, match="ACCESS_DENIED"):
        asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert "event.unbind" not in [m for m, _ in calls]


def test_dev_install_does_not_remove_prod(monkeypatch):
    calls = mock_rest(monkeypatch, bindings_at(PROD))
    monkeypatch.setattr(install.settings, "APP_URL", DEV)
    asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert [m for m, _ in calls] == ["event.get", "event.bind", "event.bind"]
    assert all(p["handler"] == DEV + PATH for m, p in calls if m == "event.bind")


def test_offline_handlers_are_not_changed(monkeypatch):
    offline = [dict(b, offline=1) for b in bindings_at(DEV) + bindings_at(PROD)]
    calls = mock_rest(monkeypatch, offline)
    asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert [m for m, _ in calls] == ["event.get", "event.bind", "event.bind"]


@pytest.mark.parametrize("result", [True, {}, {"count": -1}, {"count": "1"}])
def test_invalid_unbind_confirmation_fails(monkeypatch, result):
    mock_rest(monkeypatch, bindings_at(DEV), unbind_result=result)
    with pytest.raises(RuntimeError, match="event.unbind"):
        asyncio.run(install._bind_company_events(PORTAL, "test-token"))


@pytest.mark.parametrize("bindings", [{}, [None], ["invalid"]])
def test_invalid_binding_list_fails(monkeypatch, bindings):
    calls = mock_rest(monkeypatch, bindings)
    with pytest.raises(RuntimeError, match="invalid handler list"):
        asyncio.run(install._bind_company_events(PORTAL, "test-token"))
    assert [m for m, _ in calls] == ["event.get"]


@pytest.fixture
def local_app(monkeypatch):
    db = Mock(commit=AsyncMock())
    monkeypatch.setattr(install.settings, "APP_URL", PROD)
    monkeypatch.setattr(install, "find_settings", AsyncMock(return_value=None))
    monkeypatch.setattr(install, "next_settings_id", AsyncMock(return_value=10))
    monkeypatch.setattr(admin, "_check_is_admin_on_the_fly", AsyncMock(return_value=True))
    monkeypatch.setattr(install, "_bind_company_events", AsyncMock())
    app = FastAPI()
    app.include_router(install.router, prefix="/bitrix")
    app.include_router(admin.router, prefix="/bitrix/admin")
    app.dependency_overrides[install.get_db] = lambda: db
    return TestClient(app, base_url=PROD), db


def installation_params():
    return {"DOMAIN": PORTAL, "AUTH_ID": "test-access", "REFRESH_ID": "test-refresh", "member_id": "test-member"}


@pytest.mark.parametrize("path", ["/bitrix/install", "/bitrix/install/"])
def test_install_finishes_only_after_confirmed_events(local_app, path):
    client, db = local_app
    response = client.post(path, data=installation_params(), follow_redirects=False)
    assert "location" not in response.headers
    assert response.status_code == 200
    assert response.text.count('src="https://api.bitrix24.com/api/v1/"') == 1
    assert response.text.index('src="https://api.bitrix24.com/api/v1/"') < response.text.index("BX24.installFinish()")
    assert "window.location" not in response.text
    assert "setTimeout" not in response.text
    db.commit.assert_awaited_once()
    assert db.add.call_args.args[0].bitrix_domain == PORTAL
    install._bind_company_events.assert_awaited_once_with(PORTAL, "test-access")


def test_bind_failure_is_not_install_success(local_app):
    client, _ = local_app
    install._bind_company_events.side_effect = RuntimeError("registration failed")
    response = client.post("/bitrix/install", data=installation_params())
    assert response.status_code == 502
    assert "BX24.installFinish()" not in response.text


def test_cross_environment_install_cannot_write_tokens(local_app):
    client, db = local_app
    response = client.post(DEV + "/bitrix/install", data=installation_params())
    assert response.status_code == 400
    db.commit.assert_not_awaited()
    install._bind_company_events.assert_not_awaited()


def test_non_admin_cannot_install(local_app):
    client, db = local_app
    admin._check_is_admin_on_the_fly.return_value = False
    assert client.post("/bitrix/install", data=installation_params()).status_code == 403
    db.commit.assert_not_awaited()


def test_missing_params_are_not_logged_with_tokens(local_app, caplog):
    client, db = local_app
    assert client.post("/bitrix/install", data={"AUTH_ID": "do-not-log-me"}).status_code == 400
    assert "do-not-log-me" not in caplog.text
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("path", ["/bitrix/admin", "/bitrix/admin/"])
def test_admin_initialization_sets_portal_domain(local_app, monkeypatch, path):
    client, db = local_app
    monkeypatch.setattr(admin, "find_settings", AsyncMock(return_value=None))
    monkeypatch.setattr(admin, "next_settings_id", AsyncMock(return_value=11))
    bitrix = Mock(get_requisite_presets=AsyncMock(return_value=[]), get_company_userfields=AsyncMock(return_value=[]))
    monkeypatch.setattr(admin, "BitrixClient", Mock(return_value=bitrix))
    response = client.post(path, data=installation_params(), follow_redirects=False)
    assert "location" not in response.headers
    assert response.status_code == 200
    assert db.add.call_args.args[0].bitrix_domain == PORTAL
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("path", ["/bitrix/admin", "/bitrix/admin/", "/bitrix/install", "/bitrix/install/"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_landing_aliases_still_require_auth_without_redirect(local_app, path, method):
    client, db = local_app
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers
    db.commit.assert_not_awaited()
    admin._check_is_admin_on_the_fly.assert_not_awaited()


def test_save_failure_is_not_reported_as_success(local_app):
    client, db = local_app
    db.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=AppSettings(id=1, bitrix_domain=PORTAL))))
    install._bind_company_events.side_effect = RuntimeError("registration failed")
    assert client.post("/bitrix/admin/save", data=installation_params()).status_code == 502


@pytest.mark.parametrize("value", ["localhost", "127.0.0.1", "autocrm.bitrix24.by.evil.test", "https://autocrm.bitrix24.by", "autocrm.bitrix24.by/path"])
def test_portal_domain_rejects_non_portals(value):
    with pytest.raises(ValueError):
        portal_domain(value)


def test_portal_domain_normalization():
    assert portal_domain(" AUTOCRM.BITRIX24.BY ") == PORTAL


@pytest.mark.parametrize("value", ["http://company.tenders.by", PROD + "/bitrix", PROD + "?a=b", "https://user:password@company.tenders.by"])
def test_app_origin_rejects_invalid_settings(value):
    with pytest.raises(ValueError):
        application_origin(value)


@pytest.mark.parametrize("path,is_bitrix", [("/bitrix/install", True), ("/bitrix/admin/", True), ("/bitrix", True), ("/bitrix-other", False), ("/api/v1/health", False)])
def test_embedding_policy_is_scoped(path, is_bitrix):
    from app.main import security_headers_middleware
    request = Request({"type": "http", "scheme": "https", "server": ("company.tenders.by", 443), "path": path, "headers": [], "query_string": b""})
    response = asyncio.run(security_headers_middleware(request, AsyncMock(return_value=Response())))
    if is_bitrix:
        assert "x-frame-options" not in response.headers
        assert response.headers["content-security-policy"] == BITRIX_FRAME_POLICY
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
    else:
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert "content-security-policy" not in response.headers


def test_nginx_dev_and_prod_use_scoped_frame_policy():
    config = Path("nginx/conf.d/company.tenders.by.conf").read_text(encoding="utf-8")
    assert '~^/bitrix(/|$) "' + BITRIX_FRAME_POLICY + '";' in config
    assert config.count("add_header Content-Security-Policy $tendex_frame_ancestors always;") == 2
