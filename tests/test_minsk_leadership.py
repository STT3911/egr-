from datetime import date
from uuid import UUID

import requests

from app.services.minsk_leadership import (
    CHECK_KNOWLEDGE_URL,
    KNOWN_SOURCE_URLS,
    _canonical_source_url,
    _unique_company_matches,
    discover_source_urls,
    is_organization_head,
    parse_leadership_page,
)


SAMPLE_HTML = """
<html>
  <head><title>Список руководителей и специалистов 24.01.2025</title></head>
  <body>
    <table class="layout"><tr><td>
      <table>
        <tr><th>№</th><th>ФИО</th><th>Должность</th><th>Место работы</th><th>Вид</th></tr>
        <tr><td>1</td><td>Иванов Иван Иванович</td><td>Директор</td><td>ООО «Альфа»</td><td>первичная</td></tr>
        <tr><td>2</td><td>Петров Пётр Петрович</td><td>Заместитель директора</td><td>ООО «Альфа»</td><td>первичная</td></tr>
        <tr><td>3</td><td>Сидоров Семён Олегович</td><td>Директор ресторана</td><td>ООО «Бета»</td><td>периодическая</td></tr>
        <tr><td>4</td><td>Орлова Анна Игоревна</td><td>Председатель Правления</td><td>ЗАО «Гамма»</td><td>периодическая</td></tr>
      </table>
    </td></tr></table>
  </body>
</html>
"""


def test_parse_nested_leadership_table_and_event_date() -> None:
    rows = parse_leadership_page(
        SAMPLE_HTML,
        "https://komtrud.minsk.gov.by/example.php",
    )

    assert len(rows) == 4
    assert rows[0].event_date == date(2025, 1, 24)
    assert rows[0].person_name == "Иванов Иван Иванович"
    assert rows[0].organization_name == "ООО «Альфа»"
    assert [row.is_head for row in rows] == [True, False, False, True]


def test_head_classification_is_conservative() -> None:
    assert is_organization_head("Генеральный директор")
    assert is_organization_head("Директор ООО «Пример»")
    assert is_organization_head("Индивидуальный предприниматель")
    assert not is_organization_head("Заместитель генерального директора")
    assert not is_organization_head("Коммерческий директор")
    assert not is_organization_head("Руководитель отдела продаж")
    assert not is_organization_head("Главный инженер")


def test_source_url_canonicalization_removes_search_tracking() -> None:
    assert _canonical_source_url(
        "/news/detail.php?ID=7002&sphrase_id=39885"
    ) == "https://komtrud.minsk.gov.by/news/detail.php?ID=7002"
    assert _canonical_source_url(
        "/examination/labor_protection/20250123-spisok-rukovoditeley.php?sphrase_id=1"
    ) == (
        "https://komtrud.minsk.gov.by/examination/labor_protection/"
        "20250123-spisok-rukovoditeley.php"
    )
    assert _canonical_source_url("https://example.com/list.php") is None


def test_only_unambiguous_company_name_candidates_are_linked() -> None:
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")
    matches = _unique_company_matches(
        [
            ("альфа", first, 100000001),
            ("альфа", first, 100000001),  # another historical name row
            ("бета", first, 100000001),
            ("бета", second, 100000002),
        ]
    )

    assert matches == {"альфа": (first, 100000001)}


def test_known_sources_survive_search_endpoint_failure() -> None:
    class FailingSession:
        def get(self, url: str, timeout: float):
            raise requests.ConnectionError("search unavailable")

    urls = discover_source_urls(FailingSession(), retries=0)

    assert set(KNOWN_SOURCE_URLS).issubset(urls)
    assert CHECK_KNOWLEDGE_URL in urls
