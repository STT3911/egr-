"""Классификатор государственных организаций-юрлиц.

Наполняет справочник `gov_organizations` поверх уже собранных данных:
  - egr_raw_company_data (vnaim + ОПФ nsi00203) — госпредприятия/учреждения, которые
    проходят госрегистрацию (РУП/КУП/ГУ/ГУО/госУП и т.п.);
  - grp_taxpayer_data (full_name) — то, что есть в ГРП (включая редкие чистые госорганы).

ВАЖНО: чистые госорганы (сельисполкомы, сельские/районные Советы, министерства) в ЕГР
НЕ регистрируются — их там нет. Их добор — отдельная дорожка (перебор ГРП,
см. scripts/unp_enumerate.py). Этот модуль классифицирует то, что уже в БД.

Признака формы собственности (ОКФС) в данных нет, поэтому госпринадлежность
определяется по маркерам наименования (+ ОПФ), с исключением частных форм.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import GovOrganization

logger = get_logger("gov_organizations")


# --- Маркеры частных/негосударственных форм: при совпадении запись НЕ госорганизация ---
PRIVATE_MARKERS = [
    "частн", "чуп", "чтуп", "чпуп", "чсуп",
    "иностранн", "совместное общество", "совместное предприятие",
    "общество с ограниченной ответственностью", "общество с дополнительной",
    "крестьянское (фермерское)", "крестьянское(фермерское)",
    "индивидуальный предприниматель",
    # Общественные/профсоюзные/религиозные/кооперативные — не госорганы
    "профсоюз", "профком", "первичная организация", "первичная профсоюзная",
    "общественное объединение", "общественной организации", "общественная организация",
    "союз молодежи", "союза молодежи", "райком", "горком",
    "потребительск", "райпо", "потребительского общества",
    "приход храма", "епархи", "религиозн", "церкв", "православн",
]

# --- Категории госорганизаций: (category, список маркеров) ---
# Порядок важен: первый сработавший выигрывает.
COUNCIL_MARKERS = [
    "сельский совет", "поселковый совет", "городской совет", "районный совет",
    "областной совет", "совет депутатов",
    "сельисполком", "исполнительный комитет", "исполнительного комитета",
    # сокращения исполкомов: теперь безопасны — формы (РУП/ГУП…) и профсоюзы
    # отсекаются РАНЬШЕ, поэтому остаются только сами органы и их отделы/управления.
    "исполком", "райисполком", "облисполком", "горисполком", "горрайисполком",
]
GOV_BODY_MARKERS = [
    "министерство", "государственный комитет", "комитет государственного",
    "государственный таможенный комитет", "департамент",
    "инспекция министерства по налогам", "инспекция мнс", "инспекция",
    "национальный банк", "национальная академия наук",
    # силовые/военные/судебные/статистика
    "войсковая часть", "военный комиссариат", "военкомат",
    "управление внутренних дел", "отдел внутренних дел",
    "отдел статистики", "управление статистики",
    "экономический суд", "районный суд", "областной суд", "городской суд",
]
INSTITUTION_MARKERS = [
    "государственное учреждение", "учреждение здравоохранения",
    "учреждение образования", "учреждение культуры",
    "государственное лечебно", "государственное лесохозяйственное",
]
UNITARY_MARKERS = [
    "республиканское унитарное предприятие", "коммунальное унитарное предприятие",
    "коммунальное сельскохозяйственное унитарное предприятие",
    "производственное унитарное предприятие", "торговое унитарное предприятие",
    "дочернее унитарное предприятие", "унитарное предприятие",
    "казённое предприятие", "казенное предприятие",
]
JOINT_STOCK_MARKERS = [
    "открытое акционерное общество", "закрытое акционерное общество",
]
# Прочие гос-формы (производственные объединения, концерны) — своя ОПФ-форма,
# проверяется до органов, чтобы не путать с упоминанием исполкома/министерства.
OTHER_STATE_MARKERS = [
    "государственное производственное объединение", "производственное объединение",
    "научно-производственное объединение", "государственное объединение",
    "концерн",
]


def _compile_regex(markers: List[str]) -> re.Pattern:
    return re.compile("|".join(re.escape(m) for m in markers), re.IGNORECASE)


_PRIVATE_RE = _compile_regex(PRIVATE_MARKERS)
_COUNCIL_RE = _compile_regex(COUNCIL_MARKERS)
_GOV_BODY_RE = _compile_regex(GOV_BODY_MARKERS)
_INSTITUTION_RE = _compile_regex(INSTITUTION_MARKERS)
_UNITARY_RE = _compile_regex(UNITARY_MARKERS)
_JOINT_STOCK_RE = _compile_regex(JOINT_STOCK_MARKERS)
_OTHER_STATE_RE = _compile_regex(OTHER_STATE_MARKERS)

# Все включающие маркеры (для SQL-предфильтра кандидатов)
ALL_INCLUDE_MARKERS = (
    COUNCIL_MARKERS + GOV_BODY_MARKERS + INSTITUTION_MARKERS
    + UNITARY_MARKERS + JOINT_STOCK_MARKERS + OTHER_STATE_MARKERS
)


@dataclass
class Classification:
    category: str
    ownership: str  # state | communal | unknown
    marker: str


def _ownership_from_name(n: str, default: str) -> str:
    if "республиканск" in n:
        return "state"
    if "коммунальн" in n:
        return "communal"
    if "государственн" in n:
        return "state"
    return default


def classify_name(name: Optional[str], opf_name: Optional[str] = None,
                   include_joint_stock: bool = False) -> Optional[Classification]:
    """Определить категорию/принадлежность по наименованию (+ ОПФ).

    Возвращает Classification или None (не госорганизация / частное).
    """
    if not name:
        return None
    text_l = (name + " " + (opf_name or "")).lower()

    # 1) Частные формы — сразу отсекаем
    if _PRIVATE_RE.search(text_l):
        return None

    # ВАЖНО: сначала проверяем СОБСТВЕННУЮ ОПФ-форму (унитарное предприятие /
    # учреждение / АО), и только потом органы. Иначе РУП/ГУП с упоминанием
    # «Министерства…/…исполкома» в названии ошибочно попадают в gov_body/council.

    # 2) Унитарные предприятия (частные уже отсеяны) → state/communal/unknown
    m = _UNITARY_RE.search(text_l)
    if m:
        return Classification("unitary_enterprise", _ownership_from_name(text_l, "unknown"), m.group(0))

    # 3) Государственные учреждения → state/communal по наименованию
    m = _INSTITUTION_RE.search(text_l)
    if m:
        return Classification("gov_institution", _ownership_from_name(text_l, "state"), m.group(0))

    # 3b) Производственные объединения / концерны → other_state
    m = _OTHER_STATE_RE.search(text_l)
    if m:
        return Classification("other_state", _ownership_from_name(text_l, "state"), m.group(0))

    # 4) Акционерные общества — госдоля из данных не определяется → unknown.
    #    По умолчанию НЕ включаем (много частных); только если есть гос-намёк
    #    или включено флагом. НЕ проваливаемся дальше в органы.
    m = _JOINT_STOCK_RE.search(text_l)
    if m:
        own = _ownership_from_name(text_l, "unknown")
        if include_joint_stock or own != "unknown":
            return Classification("joint_stock", own, m.group(0))
        return None

    # 5) Министерства / госкомитеты / департаменты (своей ОПФ-формы нет) → state
    m = _GOV_BODY_RE.search(text_l)
    if m:
        return Classification("gov_body", "state", m.group(0))

    # 6) Советы / исполкомы (местное управление, своей ОПФ-формы нет) → communal
    m = _COUNCIL_RE.search(text_l)
    if m:
        return Classification("local_council", "communal", m.group(0))

    return None


# Наименование в ЕГР лежит в массиве `names` (история юр-имён), поле `vnaim`
# (vn — краткое, vnaimb — белорусское). В base_info имени НЕТ.
# Массив может быть в отдельной колонке `names` либо в data->'names'.
_EGR_NAMES_SQL = """(CASE
        WHEN jsonb_typeof(names) = 'array' THEN names
        WHEN jsonb_typeof(data->'names') = 'array' THEN data->'names'
        ELSE '[]'::jsonb END)"""
# Текущее наименование: предпочитаем актуальное (dto IS NULL), затем самое позднее.
_EGR_NAME_SQL = f"""(
    SELECT e->>'vnaim'
    FROM jsonb_array_elements({_EGR_NAMES_SQL}) e
    WHERE e->>'vnaim' IS NOT NULL
    ORDER BY (e->>'dto' IS NULL) DESC, e->>'dfrom' DESC NULLS LAST
    LIMIT 1
)"""

# POSIX-regex для предфильтра кандидатов в SQL (без частных — их отсеет classify_name)
_INCLUDE_REGEX_SQL = "|".join(re.escape(m) for m in ALL_INCLUDE_MARKERS)


def _iter_egr_candidates(db, batch: int = 5000) -> Iterator[Tuple[int, str, Optional[str], Optional[int]]]:
    """unp, name, opf_name, opf_code — только кандидаты (имя матчит включающие маркеры).

    ОПФ-кода (nsi00203) в base_info нет → opf_* возвращаем None; классификация
    идёт по наименованию (форма всё равно входит в полное имя).
    """
    sql = text(f"""
        SELECT unp, {_EGR_NAME_SQL} AS name
        FROM egr_raw_company_data
        WHERE EXISTS (
            SELECT 1 FROM jsonb_array_elements({_EGR_NAMES_SQL}) e
            WHERE e->>'vnaim' ~* :rx
        )
    """).bindparams(rx=_INCLUDE_REGEX_SQL)
    # Кандидатов немного (~125k); читаем всё разом, чтобы не держать серверный
    # курсор открытым во время commit-ов записи (иначе "named cursor isn't valid").
    for unp, name in db.execute(sql).fetchall():
        yield int(unp), name, None, None


def _iter_grp_candidates(db, batch: int = 5000) -> Iterator[Tuple[int, str]]:
    sql = text("""
        SELECT unp, full_name
        FROM grp_taxpayer_data
        WHERE full_name ~* :rx
    """).bindparams(rx=_INCLUDE_REGEX_SQL)
    for unp, name in db.execute(sql).fetchall():
        yield int(unp), name


def _flush(db, rows: List[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(GovOrganization).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[GovOrganization.unp],
        set_={
            "full_name": stmt.excluded.full_name,
            "short_name": stmt.excluded.short_name,
            "opf_code": stmt.excluded.opf_code,
            "opf_name": stmt.excluded.opf_name,
            "category": stmt.excluded.category,
            "ownership": stmt.excluded.ownership,
            "source": stmt.excluded.source,
            "matched_marker": stmt.excluded.matched_marker,
            "updated_at": text("now()"),
        },
    )
    db.execute(stmt)
    db.commit()


def rebuild(include_joint_stock: bool = False, flush_every: int = 1000) -> dict:
    """Полная пересборка справочника gov_organizations из ЕГР + ГРП.

    ЕГР идёт первым (есть ОПФ); ГРП дополняет тем, чего нет в ЕГР (on-conflict не
    перетирает уже вставленное из ЕГР, т.к. ГРП-кандидаты с тем же УНП обновят
    запись — но source станет 'grp'; чтобы ЕГР имел приоритет, ГРП пишем только
    для НЕизвестных УНП).
    """
    db = SessionLocal()
    stats = {"egr_scanned": 0, "egr_added": 0, "grp_scanned": 0, "grp_added": 0}
    seen: set = set()
    try:
        # Полная пересборка: справочник целиком выводится из исходных данных,
        # поэтому очищаем перед наполнением (иначе остаются устаревшие записи,
        # переставшие проходить классификацию после изменения маркеров).
        db.execute(text("TRUNCATE TABLE gov_organizations"))
        db.commit()

        # --- ЕГР ---
        buf: List[dict] = []
        for unp, name, opf_name, opf_code in _iter_egr_candidates(db):
            stats["egr_scanned"] += 1
            cl = classify_name(name, opf_name, include_joint_stock)
            if not cl:
                continue
            seen.add(unp)
            buf.append({
                "unp": unp, "full_name": name, "short_name": None,
                "opf_code": opf_code, "opf_name": opf_name,
                "category": cl.category, "ownership": cl.ownership,
                "source": "egr", "matched_marker": cl.marker,
            })
            stats["egr_added"] += 1
            if len(buf) >= flush_every:
                _flush(db, buf); buf.clear()
        _flush(db, buf); buf.clear()
        logger.info("ЕГР: просмотрено=%d, добавлено=%d", stats["egr_scanned"], stats["egr_added"])

        # --- ГРП (только УНП, которых нет в ЕГР-результате) ---
        for unp, name in _iter_grp_candidates(db):
            stats["grp_scanned"] += 1
            if unp in seen:
                continue
            cl = classify_name(name, None, include_joint_stock)
            if not cl:
                continue
            seen.add(unp)
            buf.append({
                "unp": unp, "full_name": name, "short_name": None,
                "opf_code": None, "opf_name": None,
                "category": cl.category, "ownership": cl.ownership,
                "source": "grp", "matched_marker": cl.marker,
            })
            stats["grp_added"] += 1
            if len(buf) >= flush_every:
                _flush(db, buf); buf.clear()
        _flush(db, buf); buf.clear()
        logger.info("ГРП: просмотрено=%d, добавлено=%d", stats["grp_scanned"], stats["grp_added"])

        # Проставляем ссылку на центральный реестр (egr_companies) по УНП.
        res = db.execute(text("""
            UPDATE gov_organizations g
            SET company_id = c.id
            FROM egr_companies c
            WHERE c.unp = g.unp AND g.company_id IS DISTINCT FROM c.id
        """))
        db.commit()
        stats["linked_company_id"] = res.rowcount or 0
        logger.info("gov_organizations.company_id проставлено: %d", stats["linked_company_id"])
    finally:
        db.close()
    return stats
