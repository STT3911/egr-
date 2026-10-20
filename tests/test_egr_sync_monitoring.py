"""Coverage, reconciliation gaps and legacy dates must not be conflated."""
import json
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def dashboard():
    return json.loads((ROOT / "grafana/dashboards/egr-sources.json").read_text(encoding="utf-8"))


def alert_sql():
    source = (ROOT / "grafana/provisioning/alerting/rules.yml").read_text(encoding="utf-8")
    block = source.split("              rawSql: |\n", 1)[1].split("          - refId: C", 1)[0]
    return textwrap.dedent(block).strip()


def test_processing_lag_uses_scanned_coverage_not_full_reconciliation():
    panel = next(p for p in dashboard()["panels"] if p["id"] == 3)
    sql = panel["targets"][0]["rawSql"]
    assert "scanned_through" in sql and "last_completed_day" in sql
    assert sql.index("scanned_through") < sql.index("last_completed_day")
    assert "Europe/Minsk" in sql and " - 1 - scanned_day" in sql
    assert "WHEN scanned_day IS NULL THEN NULL" in sql
    assert panel["fieldConfig"]["defaults"]["unit"] == "none"
    assert "обработки" in panel["title"]


def test_missing_checkpoint_does_not_look_like_zero_unresolved_rows():
    panels = {p["id"]: p for p in dashboard()["panels"]}
    for panel_id in (7, 8):
        sql = panels[panel_id]["targets"][0]["rawSql"]
        assert "WHEN progress IS NULL THEN NULL" in sql
        assert "jsonb_object_keys" in sql


def test_processed_and_fully_reconciled_dates_are_both_visible():
    panels = {p["id"]: p for p in dashboard()["panels"]}
    assert "scanned_through" in panels[5]["targets"][0]["rawSql"]
    assert "last_completed_day" in panels[6]["targets"][0]["rawSql"]
    assert "scanned_through" not in panels[6]["targets"][0]["rawSql"]
    assert "transition_conflicts" in panels[7]["targets"][0]["rawSql"]
    assert "history_conflicts" in panels[8]["targets"][0]["rawSql"]


def test_dashboard_ids_and_panel_positions_do_not_overlap():
    panels = dashboard()["panels"]
    assert len({p["id"] for p in panels}) == len(panels) == 9
    for i, a in enumerate(panels):
        a = a["gridPos"]
        assert 0 <= a["x"] < a["x"] + a["w"] <= 24
        for b in panels[i + 1:]:
            b = b["gridPos"]
            assert (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                    or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def test_alert_distinguishes_a_stalled_pipeline_from_quarantined_rows():
    sql = alert_sql()
    assert "scanned_day IS NULL" in sql
    assert "Europe/Minsk" in sql and " - 1 - scanned_day > 3" in sql
    assert "SELECT 11, 'warning'" in sql and "WHERE unresolved_transitions > 0" in sql
    assert "SELECT 12, 'warning'" in sql and "WHERE unresolved_histories > 0" in sql
    assert "s.value::date > 3" not in sql
    assert "FROM issues" in sql


def test_other_source_alerts_and_no_data_safety_remain_enabled():
    sql = alert_sql()
    assert "WHERE processed_at IS NULL" in sql and "HAVING count(*) > 50000" in sql
    assert "WHERE enabled AND (age_hours IS NULL OR age_hours > 168)" in sql
    assert "FROM bankrot_health" in sql
    assert "latest_status IN ('failed', 'missing')" in sql
    assert "дата полной сверки не подтверждена" in sql
    rules = (ROOT / "grafana/provisioning/alerting/rules.yml").read_text(encoding="utf-8")
    assert "execErrState: Alerting" in rules
