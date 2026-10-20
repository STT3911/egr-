import json
from unittest.mock import Mock

import pytest

from scripts.court_cookie_bot import (
    Config, ControlError, Controller, Exporter, Telegram, parse_cookie, atomic_private_write,
    CourtAuthProbe, confirmed_auth_response,
)

COOKIE = "ASP.NET_SessionId=test-session; .ASPXAUTH=test-auth"


@pytest.fixture
def setup(tmp_path):
    config = Config("123:test", 123, -456, tmp_path / "court.cookie", tmp_path / "state.json")
    config.cookie.write_text("old")
    telegram = Mock()
    exporter = Mock()
    exporter.status.return_value = {"id": "fixed-id", "state": {
        "Status": "exited", "FinishedAt": "2026-09-30T00:00:00Z", "ExitCode": 2}}
    exporter.stop_report.return_value = {"reason": "auth_required", "progress": "unknown"}
    probe = Mock(check=Mock(return_value={"status": "not_confirmed"}))
    return Controller(config, telegram, exporter, clock=lambda: 1000, auth_probe=probe), telegram, exporter


def update(**patch):
    message = {"message_id": 100, "date": 990, "text": COOKIE,
               "chat": {"id": 123, "type": "private"}, "from": {"id": 123}}
    message.update(patch)
    return {"update_id": 100, "message": message}


def test_authorized_cookie_is_saved_then_existing_container_started(setup):
    controller, telegram, exporter = setup
    exporter.start.side_effect = lambda container: (
        pytest.fail("Wrong cookie") if controller.config.cookie.read_text().strip() != COOKIE else None)
    controller.handle(update())
    exporter.start.assert_called_once_with("fixed-id")
    telegram.request.assert_called_once_with("deleteMessage", {"chat_id": 123, "message_id": 100})
    assert COOKIE not in str(telegram.send.call_args_list)
    assert "test-auth" not in controller.config.state.read_text()
    controller.handle(update())
    exporter.start.assert_called_once()
    resumed = Controller(controller.config, telegram, exporter, clock=lambda: 1000)
    resumed.handle(update())
    exporter.start.assert_called_once()


@pytest.mark.parametrize("patch", [
    {"from": {"id": 999}}, {"chat": {"id": 999, "type": "private"}},
    {"chat": {"id": 123, "type": "group"}}, {"from": {"id": 123, "is_bot": True}},
    {"forward_origin": {"type": "user"}}, {"via_bot": {"id": 123}},
    {"sender_chat": {"id": 123}}, {"edit_date": 999},
])
def test_other_senders_groups_forwarded_messages_cannot_control_exporter(setup, patch):
    controller, telegram, exporter = setup
    controller.handle(update(**patch))
    assert controller.config.cookie.read_text() == "old"
    exporter.status.assert_not_called()
    exporter.start.assert_not_called()
    telegram.send.assert_not_called()


@pytest.mark.parametrize("state", ["running", "restarting", "paused", "removing", "dead"])
def test_never_overwrites_cookie_of_active_exporter(setup, state):
    controller, telegram, exporter = setup
    exporter.status.return_value["state"]["Status"] = state
    controller.handle(update())
    assert controller.config.cookie.read_text() == "old"
    exporter.start.assert_not_called()


@pytest.mark.parametrize("text", ["ASP.NET_SessionId=only-session", "Cookie: echo rm -rf /",
    COOKIE + "\nHost: other", COOKIE + "; Secure", COOKIE + "; broken", COOKIE * 1000],
    ids=["session-only", "command", "headers", "attributes", "fragment", "too-large"])
def test_invalid_cookie_never_reaches_docker(setup, text):
    controller, telegram, exporter = setup
    controller.handle(update(text=text))
    assert controller.config.cookie.read_text() == "old"
    exporter.status.assert_not_called()


def test_cookie_header_normalization():
    assert parse_cookie("cookie\n" + COOKIE).strip() == COOKIE
    assert parse_cookie("Cookie: " + COOKIE).strip() == COOKIE
    assert parse_cookie("/cookie " + COOKIE).strip() == COOKIE


@pytest.mark.parametrize("text", [COOKIE, "Cookie: " + COOKIE, "cookie\n" + COOKIE],
                         ids=["plain-text", "header", "copied-label"])
def test_plain_message_accepts_cookie_without_command_or_document(setup, text):
    controller, telegram, exporter = setup
    controller.handle(update(text=text))
    assert controller.config.cookie.read_text().strip() == COOKIE
    exporter.start.assert_called_once_with("fixed-id")
    telegram.cookie_document.assert_not_called()


def test_repeated_start_is_suppressed_across_restart(setup):
    controller, telegram, exporter = setup
    controller.handle(update(text="/start"))
    second = update(text="/start")
    second["update_id"] = 101
    resumed = Controller(controller.config, telegram, exporter, clock=lambda: 1010)
    resumed.handle(second)
    telegram.send.assert_called_once()
    assert "обычным текстовым" in telegram.send.call_args.args[1]
    resumed.clock = lambda: 1310
    third = update(text="/help")
    third["update_id"] = 102
    resumed.handle(third)
    assert telegram.send.call_count == 2


def test_stop_notice_and_queued_start_send_only_one_prompt(setup):
    controller, telegram, exporter = setup
    from dataclasses import replace
    controller.config = replace(controller.config, notify_chat_id=123)
    controller.check_stop()
    controller.handle(update(text="/start"))
    telegram.send.assert_called_once()
    assert "обычным текстом" in telegram.send.call_args.args[1]


def test_blank_stop_is_silent_and_restarts_after_cooldown_with_same_cookie(setup):
    controller, telegram, exporter = setup
    exporter.status.return_value["state"]["ExitCode"] = 1
    exporter.stop_report.return_value = {"reason": "blank_response", "progress": "151:14:61"}
    controller.check_stop()
    assert controller.state["retry_due"] == 1600
    telegram.send.assert_not_called()
    assert controller.config.cookie.read_text() == "old"
    resumed = Controller(controller.config, telegram, exporter, clock=lambda: 1599)
    resumed.check_stop()
    exporter.start.assert_not_called()
    resumed.clock = lambda: 1600
    resumed.check_stop()
    exporter.start.assert_called_once_with("fixed-id")
    resumed.check_stop()
    exporter.start.assert_called_once()
    telegram.send.assert_not_called()


def test_repeated_blank_stops_back_off_and_new_page_resets_delay(setup):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "blank_response", "progress": "151:14:61"}
    for n, delay in enumerate([600, 1200, 2400, 3600, 3600]):
        exporter.status.return_value["state"]["FinishedAt"] = str(n)
        controller.check_stop()
        assert controller.state["retry_due"] == 1000 + delay
    exporter.stop_report.return_value["progress"] = "151:14:62"
    exporter.status.return_value["state"]["FinishedAt"] = "new-page"
    controller.check_stop()
    assert controller.state["retry_due"] == 1600
    telegram.send.assert_not_called()


def test_auth_after_blank_cancels_restart_and_requests_cookie_only_once(setup):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "blank_response", "progress": "151:14:61"}
    controller.check_stop()
    exporter.status.return_value["state"]["FinishedAt"] = "auth-stop"
    exporter.stop_report.return_value = {"reason": "auth_required", "progress": "unknown"}
    controller.check_stop()
    controller.clock = lambda: 10000
    controller.check_stop()
    assert controller.state["retry_due"] is None
    exporter.start.assert_not_called()
    telegram.send.assert_called_once()
    assert "отклонил авторизацию" in telegram.send.call_args.args[1]


@pytest.mark.parametrize("reason", ["unrecognized_response", "unexpected_redirect", "unknown", "complete"])
def test_other_stops_do_not_request_cookie_or_restart(setup, reason):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": reason, "progress": "unknown"}
    controller.check_stop()
    controller.clock = lambda: 10000
    controller.check_stop()
    telegram.send.assert_not_called()
    exporter.start.assert_not_called()


def test_stop_reason_requires_both_auth_exit_and_auth_message(setup):
    controller, _, _ = setup
    exporter = Exporter(controller.config)
    exporter._run = Mock(return_value="Court session expired; refresh the local cookie file and resume\n")
    status = {"state": {"StartedAt": "2026-09-30T00:00:00Z", "ExitCode": 2}}
    assert exporter.stop_report(status)["reason"] == "auth_required"
    status["state"]["ExitCode"] = 1
    assert exporter.stop_report(status)["reason"] == "unknown"
    status["state"]["ExitCode"] = 2
    exporter._run.return_value = "usage: exporter; argument error\n"
    assert exporter.stop_report(status)["reason"] == "unknown"


def test_blank_stop_reason_recognizes_existing_exporter_logs_without_leaking_text(setup):
    controller, _, _ = setup
    exporter = Exporter(controller.config)
    exporter._run = Mock(return_value=(
        'Court export stopped: CourtResponseError; court=151; page=61\n'
        '{"reason":"blank_response","http_status":200,"response_bytes":2,"attempts":3}\n'
        'Court Telegram notification: sent\n'))
    status = {"state": {"StartedAt": "2026-09-30T00:00:00Z", "ExitCode": 1}}
    assert exporter.stop_report(status) == {"reason": "blank_response", "progress": "151:61"}


def test_controller_heartbeat_contains_timestamp_and_auth_route_without_secrets(setup):
    controller, _, _ = setup
    controller.heartbeat()
    assert json.loads((controller.config.cookie.parent / '.court-control-heartbeat.json').read_text()) == {
        'updated_at': 1000, 'auth_chat_id': -456}


@pytest.mark.parametrize("reason", ["blank_response", "unexpected_redirect", "unrecognized_response", "unknown"])
@pytest.mark.parametrize("already_delivered", [True, False])
def test_ordinary_failure_fallback_goes_only_to_default_chat_without_duplicates(setup, reason, already_delivered):
    from dataclasses import replace
    controller, telegram, exporter = setup
    controller.config = replace(controller.config, default_alert_chat_id=-789)
    exporter.status.return_value["state"]["ExitCode"] = 1
    exporter.stop_report.return_value = {"reason": reason, "progress": "151:14:61"}
    exporter.ordinary_alert_delivered.return_value = already_delivered
    controller.check_stop()
    controller.check_stop()
    if already_delivered:
        telegram.send.assert_not_called()
    else:
        telegram.send.assert_called_once()
        assert telegram.send.call_args.args[0] == -789
        assert "Пришлите" not in telegram.send.call_args.args[1]
    assert controller.state["ordinary_notified_stop"] == "fixed-id:2026-09-30T00:00:00Z"


def test_auth_does_not_use_ordinary_alert_fallback(setup):
    from dataclasses import replace
    controller, telegram, exporter = setup
    controller.config = replace(controller.config, default_alert_chat_id=-789)
    controller.check_stop()
    telegram.send.assert_called_once()
    assert telegram.send.call_args.args[0] == -456
    exporter.ordinary_alert_delivered.assert_not_called()


def test_ordinary_notification_marker_requires_successful_delivery(setup):
    from dataclasses import replace
    controller, telegram, exporter = setup
    controller.config = replace(controller.config, default_alert_chat_id=-789)
    exporter.stop_report.return_value = {"reason": "unknown", "progress": "unknown"}
    exporter.ordinary_alert_delivered.return_value = False
    telegram.send.side_effect = ControlError("No delivery")
    with pytest.raises(ControlError):
        controller.check_stop()
    assert "handled_stop" not in controller.state
    assert "ordinary_notified_stop" not in controller.state
    telegram.send.side_effect = None
    controller.check_stop()
    assert telegram.send.call_count == 2


def test_delivery_detection_uses_only_exact_marker_from_current_run(setup):
    controller, _, _ = setup
    exporter = Exporter(controller.config)
    exporter._run = Mock(return_value="Court Telegram notification: NOT delivered\n")
    status = {"state": {"StartedAt": "2026-10-02T00:00:00Z"}}
    assert exporter.ordinary_alert_delivered(status) is False
    exporter._run.return_value = "Court Telegram notification: sent\n"
    assert exporter.ordinary_alert_delivered(status) is True
    assert exporter._run.call_args.args[2] == status["state"]["StartedAt"]


def test_already_handled_redirect_is_rechecked_and_auth_goes_only_to_cookie_chat(setup):
    controller, telegram, exporter = setup
    exporter.status.return_value["state"]["ExitCode"] = 1
    exporter.stop_report.return_value = {"reason": "unexpected_redirect", "progress": "151:14:73"}
    controller.state["handled_stop"] = "fixed-id:2026-09-30T00:00:00Z"
    controller.auth_probe.check.return_value = {"status": "auth_required"}
    telegram.send.return_value = {"message_id": 987}
    controller.check_stop()
    controller.check_stop()
    telegram.send.assert_called_once()
    assert telegram.send.call_args.args[0] == -456
    assert controller.state["auth_notification_message_id"] == 987
    assert controller.state["auth_confirmed_stop"] == controller.state["handled_stop"]
    controller.auth_probe.check.assert_called_once()
    exporter.start.assert_not_called()
    assert controller.config.cookie.read_text() == "old"


@pytest.mark.parametrize("result", [{"status": "not_confirmed"}, {"status": "deferred", "retry_at": 1200}])
def test_unconfirmed_auth_or_shared_rate_pause_never_requests_cookie(setup, result):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "unexpected_redirect", "progress": "unknown"}
    controller.auth_probe.check.return_value = result
    controller.check_stop()
    controller.check_stop()
    telegram.send.assert_not_called()
    controller.auth_probe.check.assert_called_once()
    assert controller.state["next_auth_probe_at"] == (1200 if result["status"] == "deferred" else 4600)


def test_auth_probe_failure_is_rate_limited_without_sending_cookie_request(setup):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "unexpected_redirect", "progress": "unknown"}
    controller.auth_probe.check.side_effect = ControlError("unavailable")
    controller.check_stop()
    controller.check_stop()
    controller.auth_probe.check.assert_called_once()
    telegram.send.assert_not_called()


@pytest.mark.parametrize("change", ["container_running", "cookie_replaced", "different_stop"])
def test_auth_probe_discards_stale_result_after_run_or_cookie_changes(setup, change):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "unexpected_redirect", "progress": "unknown"}
    def check(now):
        if change == "container_running": exporter.status.return_value["state"]["Status"] = "running"
        if change == "different_stop": exporter.status.return_value["state"]["FinishedAt"] = "new-stop"
        if change == "cookie_replaced": controller.config.cookie.write_text("new cookie generation")
        return {"status": "auth_required"}
    controller.auth_probe.check.side_effect = check
    controller.check_stop()
    telegram.send.assert_not_called()
    assert "auth_confirmed_stop" not in controller.state


def test_confirmed_auth_delivery_failure_retries_without_another_http_request(setup):
    controller, telegram, exporter = setup
    exporter.stop_report.return_value = {"reason": "unexpected_redirect", "progress": "unknown"}
    controller.auth_probe.check.return_value = {"status": "auth_required"}
    telegram.send.side_effect = ControlError("No delivery")
    with pytest.raises(ControlError): controller.check_stop()
    assert "notified_stop" not in controller.state
    telegram.send.side_effect = None
    controller.check_stop()
    assert telegram.send.call_count == 2
    controller.auth_probe.check.assert_called_once()


@pytest.mark.parametrize("status,headers,body,expected", [
    (302, {"Location": "/Account/Login?ReturnUrl=secret"}, "", True),
    (302, {"Location": "/ru/account/login"}, "", True),
    (302, {"Location": "/maintenance?next=/Account/Login"}, "", False),
    (302, {"Location": "https://other.invalid/Account/Login"}, "", False),
    (401, {}, "", True), (403, {}, "", True),
    (200, {}, "\r\n", False), (503, {}, "", False),
    (200, {"REQUIRES_AUTH": "1"}, "", True),
    (200, {}, '<form action="/Account/Login">', True),
    (200, {}, '<form action="/search">', False),
])
def test_probe_only_confirms_recognized_auth_failure(status, headers, body, expected):
    assert confirmed_auth_response(status, headers, body) is expected


def test_host_probe_waits_for_shared_interval_without_reading_cookie_or_http(setup):
    controller, _, _ = setup
    rate = controller.config.cookie.parent / ".court-request-rate.txt"
    rate.write_text("980")
    probe = CourtAuthProbe(controller.config)
    probe.opener = Mock()
    assert probe.check(1000) == {"status": "deferred", "retry_at": 1010}
    probe.opener.open.assert_not_called()
    assert rate.read_text() == "980"


def test_cookie_probe_and_export_client_share_thirty_second_policy():
    from app.services.court_judgments import CourtJudgmentClient
    from scripts.court_cookie_bot import COURT_REQUEST_INTERVAL
    with CourtJudgmentClient("a=b") as client:
        assert COURT_REQUEST_INTERVAL == client.min_interval_seconds == 30


def test_host_probe_performs_one_read_never_overwrites_cookie_or_checkpoint(setup):
    from urllib.error import HTTPError
    controller, _, _ = setup
    controller.config.cookie.write_text(COOKIE)
    before = controller.config.cookie.read_bytes()
    probe = CourtAuthProbe(controller.config)
    probe.opener = Mock()
    probe.opener.open.side_effect = HTTPError("https://service.court.gov.by/", 302, "", {"Location": "/Account/Login"}, None)
    assert probe.check(1000) == {"status": "auth_required"}
    probe.opener.open.assert_called_once()
    assert probe.opener.open.call_args.kwargs["timeout"] == 8
    assert controller.config.cookie.read_bytes() == before
    assert not controller.config.state.exists()
    assert (controller.config.cookie.parent / ".court-request-rate.txt").read_text().strip() == "1000.000000"


def test_host_probe_checks_legacy_session_only_cookie_but_submissions_stay_strict(setup):
    from urllib.error import HTTPError
    controller, _, _ = setup
    cookie = "ASP.NET_SessionId=test-session"
    controller.config.cookie.write_text(cookie)
    with pytest.raises(ControlError):
        parse_cookie(cookie)
    probe = CourtAuthProbe(controller.config)
    probe.opener = Mock()
    probe.opener.open.side_effect = HTTPError("https://service.court.gov.by/", 302, "", {"Location": "/Account/Login"}, None)
    assert probe.check(1000) == {"status": "auth_required"}
    probe.opener.open.assert_called_once()
    assert controller.config.cookie.read_text() == cookie


def test_prompt_cooldown_does_not_block_cookie_submission(setup):
    controller, telegram, exporter = setup
    controller.handle(update(text="/start"))
    cookie_update = update()
    cookie_update["update_id"] = 101
    controller.handle(cookie_update)
    exporter.start.assert_called_once_with("fixed-id")


def test_ordinary_chat_is_not_deleted_or_applied_as_cookie(setup):
    controller, telegram, exporter = setup
    controller.handle(update(text="привет"))
    telegram.request.assert_not_called()
    exporter.status.assert_not_called()
    assert controller.config.cookie.read_text() == "old"


def test_old_message_is_not_applied(setup):
    controller, telegram, exporter = setup
    controller.handle(update(date=1))
    exporter.status.assert_not_called()
    assert controller.config.cookie.read_text() == "old"


def test_state_write_failure_prevents_side_effects(setup, monkeypatch):
    controller, telegram, exporter = setup
    monkeypatch.setattr(controller, "save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        controller.handle(update())
    exporter.status.assert_not_called()
    assert controller.config.cookie.read_text() == "old"


def test_failed_restart_does_not_reapply_cookie_and_deletion_failure_is_explicit(setup):
    controller, telegram, exporter = setup
    exporter.start.side_effect = RuntimeError("sensitive-value")
    telegram.request.side_effect = RuntimeError("sensitive-value")
    controller.handle(update())
    assert "sensitive-value" not in str(telegram.send.call_args_list)
    assert "вручную" in telegram.send.call_args.args[1]
    controller.handle(update())
    exporter.start.assert_called_once()


def test_cookie_document(setup):
    controller, telegram, exporter = setup
    telegram.cookie_document.return_value = COOKIE
    controller.handle(update(text="", document={"file_id": "test"}))
    exporter.start.assert_called_once()


def test_stop_alert_deduplicates_only_after_successful_delivery(setup):
    controller, telegram, exporter = setup
    telegram.send.side_effect = RuntimeError()
    with pytest.raises(RuntimeError):
        controller.check_stop()
    assert "notified_stop" not in controller.state
    telegram.send.side_effect = None
    controller.check_stop()
    controller.check_stop()
    assert telegram.send.call_count == 2
    assert telegram.send.call_args.args[0] == -456
    exporter.status.return_value["state"]["FinishedAt"] = "later"
    controller.check_stop()
    assert telegram.send.call_count == 3


def test_cookie_and_state_atomic_writes_leave_no_temporary_files(tmp_path):
    path = tmp_path / "court.cookie"
    atomic_private_write(path, COOKIE)
    assert path.read_text() == COOKIE
    assert list(tmp_path.iterdir()) == [path]


def test_docker_mount_must_match_config(setup):
    controller, _, _ = setup
    exporter = Exporter(controller.config)
    exporter._run = Mock(return_value=json.dumps({"id": "a", "state": {}, "mounts": []}))
    with pytest.raises(ControlError):
        exporter.status()


def test_telegram_errors_suppress_token_and_body():
    telegram = Telegram("fake-token-never-log")
    telegram.opener = Mock()
    telegram.opener.open.side_effect = RuntimeError("fake-token-never-log")
    with pytest.raises(ControlError) as error:
        telegram.request("sendMessage", {})
    assert "fake-token" not in str(error.value)


@pytest.mark.parametrize("document", [
    {"file_name": "x.exe", "file_size": 1}, {"file_name": "x.txt", "file_size": 20000},
    {"file_name": "x.txt"},
])
def test_document_limits_before_download(document):
    telegram = Telegram("fake")
    telegram.request = Mock()
    with pytest.raises(ControlError):
        telegram.cookie_document(document)
    telegram.request.assert_not_called()
