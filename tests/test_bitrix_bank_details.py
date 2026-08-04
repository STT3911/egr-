import asyncio
from types import SimpleNamespace

from app.bitrix.egr_client import EGRCompanyInfo
from app.bitrix.requisite_service import (
    RequisiteService,
    _bank_account_key,
    _bitrix_bank_fields,
)


def test_bitrix_bank_fields_keep_values_separate_and_stable() -> None:
    source = {
        "account_number": " BY32 AKBB 3012 0000 4246 3000 0000 ",
        "bank_code": "akbbby2x",
        "bank_name": 'ОАО "АСБ Беларусбанк"',
        "currency_code": "933",
        "source_contract_id": "36943a2a-3718-45ce-869d-09a8c48b13f1",
    }

    first = _bitrix_bank_fields(source, "590720390")
    second = _bitrix_bank_fields(dict(source), "590720390")

    assert first is not None
    assert first == second
    assert first["RQ_ACC_NUM"] == "BY32AKBB30120000424630000000"
    assert first["RQ_BIK"] == "AKBBBY2X"
    assert first["RQ_BIC"] == "AKBBBY2X"
    assert first["RQ_SWIFT"] == "AKBBBY2X"
    assert first["RQ_BANK_NAME"] == 'ОАО "АСБ Беларусбанк"'
    assert first["RQ_ACC_CURRENCY"] == "BYN"
    assert first["XML_ID"].startswith("tendex:gias:")
    assert "36943a2a-3718-45ce-869d-09a8c48b13f1" in first["COMMENTS"]


def test_bank_account_key_ignores_spaces_and_case() -> None:
    assert _bank_account_key(" by32 akbb ") == "BY32AKBB"


def test_sync_adds_only_missing_accounts_and_preserves_manual_details() -> None:
    class FakeBitrix:
        def __init__(self) -> None:
            self.created: list[tuple[int, int, dict]] = []

        async def get_bank_details(self, requisite_id: int):
            assert requisite_id == 77
            return [
                {
                    "ID": "10",
                    "RQ_ACC_NUM": "BY32 AKBB 3012 0000 4246 3000 0000",
                    "RQ_IBAN": None,
                    "ORIGINATOR_ID": None,
                }
            ]

        async def get_requisite_preset_country_id(self, preset_id: int):
            assert preset_id == 12
            return 4

        async def create_bank_detail(
            self, requisite_id: int, country_id: int, fields: dict
        ):
            self.created.append((requisite_id, country_id, fields))
            return 100 + len(self.created)

    bitrix = FakeBitrix()
    service = RequisiteService(bitrix, object())
    accounts = [
        {
            "account_number": "BY32AKBB30120000424630000000",
            "bank_code": "AKBBBY2X",
            "currency_name": "BYN",
        },
        {
            "account_number": "BY86BPSB30121003354579330000",
            "bank_code": "BPSBBY2X",
            "currency_name": "BYN",
        },
        {
            "account_number": "BY86 BPSB 3012 1003 3545 7933 0000",
            "bank_code": "BPSBBY2X",
            "currency_name": "BYN",
        },
    ]

    created = asyncio.run(
        service._sync_bank_details(
            requisite_id=77,
            preset_id=12,
            unp="590720390",
            accounts=accounts,
        )
    )

    assert created == 1
    assert len(bitrix.created) == 1
    requisite_id, country_id, fields = bitrix.created[0]
    assert requisite_id == 77
    assert country_id == 4
    assert fields["RQ_ACC_NUM"] == "BY86BPSB30121003354579330000"


def test_sync_aborts_when_existing_bank_details_cannot_be_read() -> None:
    class FailingBitrix:
        def __init__(self) -> None:
            self.created = False

        async def get_bank_details(self, requisite_id: int):
            raise RuntimeError("Bitrix unavailable")

        async def get_requisite_preset_country_id(self, preset_id: int):
            return 4

        async def create_bank_detail(self, *args, **kwargs):
            self.created = True
            return 1

    bitrix = FailingBitrix()
    service = RequisiteService(bitrix, object())

    created = asyncio.run(
        service._sync_bank_details(
            requisite_id=77,
            preset_id=12,
            unp="590720390",
            accounts=[{"account_number": "BY32AKBB30120000424630000000"}],
        )
    )

    assert created == 0
    assert bitrix.created is False


def test_existing_requisite_keeps_manual_fields_and_receives_missing_account() -> None:
    class FakeBitrix:
        def __init__(self) -> None:
            self.methods: list[str] = []
            self.created: list[dict] = []

        async def _load_settings(self):
            return SimpleNamespace(
                unp_field_code="UF_UNP",
                requisite_preset_id=12,
            )

        async def call(self, method: str, params: dict):
            self.methods.append(method)
            if method == "crm.company.get":
                return {
                    "ID": "42",
                    "TITLE": "Название, исправленное менеджером",
                    "UF_UNP": "590720390",
                    "PHONE": [{"VALUE": "+375291234567"}],
                    "EMAIL": [],
                    "WEB": [],
                }
            if method == "crm.requisite.list":
                return [{"ID": "77", "PRESET_ID": "12", "RQ_INN": "590720390"}]
            raise AssertionError(f"Unexpected direct Bitrix method: {method}")

        async def get_bank_details(self, requisite_id: int):
            return []

        async def get_requisite_preset_country_id(self, preset_id: int):
            return 4

        async def create_bank_detail(
            self, requisite_id: int, country_id: int, fields: dict
        ):
            self.created.append(fields)
            return 101

    class FakeEGR:
        async def get_company_info(self, unp: str):
            return EGRCompanyInfo(
                full_name="ООО Тест",
                short_name="ООО Тест",
                is_empty=False,
                is_ip=False,
                bank_accounts=[
                    {
                        "account_number": "BY32AKBB30120000424630000000",
                        "bank_code": "AKBBBY2X",
                        "bank_name": "Беларусбанк",
                        "currency_name": "BYN",
                    }
                ],
            )

    bitrix = FakeBitrix()
    service = RequisiteService(bitrix, FakeEGR())

    asyncio.run(service.process_company_update(42))

    assert len(bitrix.created) == 1
    assert bitrix.created[0]["RQ_ACC_NUM"] == "BY32AKBB30120000424630000000"
    assert "crm.company.update" not in bitrix.methods
    assert "crm.requisite.update" not in bitrix.methods
