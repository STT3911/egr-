from app.services.licenses import license_timeline_dates, normalize_license_row


def test_reads_license_decision_and_official_termination_date():
    detail = {
        "isActual": True,
        "reLicenseStatus": {"code": "2"},
        "decisionDate": "2012-03-02T00:00:00",
        "decisionModificationDate": "2023-12-26T00:00:00",
        "suspensionDateStart": "2023-12-27T00:00:00",
        "reActivityType": {"dateEnd": "2024-01-01T00:00:00"},
    }
    assert license_timeline_dates(detail) == {
        "decision_date": "2012-03-02",
        "termination_date": "2023-12-27",
    }


def test_does_not_use_suspension_modification_or_history_as_termination():
    detail = {
        "isActual": True,
        "reLicenseStatus": {"code": "2"},
        "decisionModificationDate": "2023-12-26T00:00:00",
    }
    assert license_timeline_dates(detail) == {}
    detail["suspensionDateStart"] = "2023-12-27T00:00:00"
    assert license_timeline_dates({**detail, "reLicenseStatus": {"code": "3"}}) == {}
    assert license_timeline_dates({**detail, "isActual": False}) == {}
    assert license_timeline_dates({**detail, "decisionDate": "2024-01-01"}) == {
        "decision_date": "2024-01-01",
    }


def test_index_import_cannot_set_timeline_dates():
    row = {"id": 42, "_timeline": {"termination_date": "invalid"}}
    normalized = normalize_license_row(row, None)
    assert "_timeline" not in normalized["raw_json"]
