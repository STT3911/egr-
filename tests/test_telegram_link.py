from app.services.telegram_link import _merge_event_types


def test_merge_event_types_preserves_all_events_semantics() -> None:
    assert _merge_event_types([], ["bankruptcy"]) == []
    assert _merge_event_types(["tax_debt"], []) == []


def test_merge_event_types_combines_specific_filters() -> None:
    assert _merge_event_types(
        ["tax_debt", "bankruptcy"],
        ["status_changed", "tax_debt"],
    ) == ["bankruptcy", "status_changed", "tax_debt"]
