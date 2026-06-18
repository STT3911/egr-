"""
Тонкий эндпоинт для приложения Битрикс24.

Отдаёт ТОЛЬКО данные, нужные для заполнения реквизитов компании по УНП,
а не весь профиль (требование лида). Источник — наша БД (профиль ЕГР + ГРП).
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import get_logger
from app.core.security import verify_api_key
from app.crud.company import CompanyCRUD
from app.crud.grp import GrpCRUD
from app.schemas.bitrix import BitrixRequisiteAddress, BitrixRequisiteData

router = APIRouter()
logger = get_logger("api.bitrix")

# Маркеры организационно-правовых форм юрлица — если есть в названии, это НЕ ИП.
# Включаем как аббревиатуры (ООО), так и развёрнутые формы («Общество с ограниченной…»),
# потому что в ЕГР полное наименование часто хранится без аббревиатуры.
_ORG_MARKERS = (
    "ООО", "ЗАО", "ОАО", "ПАО", "ЧУП", "ОДО", "УП ", "РУП", "РУПП",
    "ГП ", "КУП", "ТУП", "СООО", "ИООО", "ЗАСО", "ОАСО", "ТОВАРИЩЕСТВО",
    "УЧРЕЖДЕНИЕ", "КООПЕРАТИВ", "ОБЪЕДИНЕНИЕ", "ФОНД", "ПРЕДПРИЯТИЕ",
    "ОБЩЕСТВО", "АКЦИОНЕРНОЕ", "УНИТАРНОЕ", "ОРГАНИЗАЦИЯ", "КОНЦЕРН", "ХОЛДИНГ",
)

# Код вида субъекта из ЕГР (nsi00211.nkvob): 1 — юридическое лицо.
_ENTITY_TYPE_JURIDICAL = 1

# Префиксы, которые срезаем из названия ИП, чтобы получить ФИО для поля «директор».
_IP_PREFIXES = (
    "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ",
    "ИП",
)


def _detect_is_ip(
    full_name: str,
    short_name: str,
    unp: str,
    entity_type_id: int | None = None,
) -> bool:
    """ИП или юрлицо.

    Приоритет — достоверный вид субъекта из ЕГР (``entity_type_id``); название
    используется только как фолбэк, когда тип в БД неизвестен. При неопределённости
    считаем компанию ОРГАНИЗАЦИЕЙ — это безопаснее, чем налепить «ИП» на юрлицо.
    """
    # 1) Достоверный признак из ЕГР: 1 → юрлицо, иначе ИП/физлицо.
    if entity_type_id is not None:
        try:
            return int(entity_type_id) != _ENTITY_TYPE_JURIDICAL
        except (TypeError, ValueError):
            pass

    # 2) Фолбэк по названию — учитываем и полное, и краткое наименование.
    text = f"{full_name or ''} {short_name or ''}".upper().strip()
    if "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ" in text:
        return True
    if text.startswith("ИП ") or text.startswith("ИП."):
        return True
    # В УНП есть буквы — это физлицо/ИП (правило налоговой РБ).
    if unp and not str(unp).isdigit():
        return True
    # Нашли маркер юрлица — точно организация.
    if any(marker in text for marker in _ORG_MARKERS):
        return False
    # 3) Не определили — считаем организацией.
    return False


def _extract_director(full_name: str, short_name: str) -> str:
    """Из названия ИП достаём ФИО (срезаем префикс «Индивидуальный предприниматель»/«ИП»)."""
    source = (full_name or short_name or "").strip()
    if not source:
        return ""
    upper = source.upper()
    for prefix in _IP_PREFIXES:
        if upper.startswith(prefix):
            cleaned = source[len(prefix):].lstrip(" .,-")
            return cleaned or source
    return source


def _pick_current(items: list, key: str = "valid_to") -> dict | None:
    """Выбрать актуальную запись истории (valid_to is None) либо первую."""
    if not items:
        return None
    for item in items:
        if item.get(key) is None:
            return item
    return items[0]


@router.get("/requisite/{unp}", response_model=BitrixRequisiteData)
def get_requisite_data(
    unp: str = Path(..., regex=r"^\d{9}$", description="УНП (9 цифр)"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Срез данных компании под реквизит Битрикс24: наименования, директор, орган, адрес, ОКЭД."""
    unp_int = int(unp)

    dossier = CompanyCRUD(db).get_full_dossier(unp_int)
    grp = GrpCRUD(db).get_by_unp(unp_int)

    if not dossier and not grp:
        raise HTTPException(status_code=404, detail=f"Компания {unp} не найдена")

    dossier = dossier or {}

    # Наименования: приоритет — профиль ЕГР, затем ГРП.
    full_name = dossier.get("current_name_ru") or (grp.full_name if grp else None)
    short_name = dossier.get("current_short_name_ru") or (grp.short_name if grp else None)

    # Орган регистрации (для ИП — основание «Свидетельство...»): из ГРП.
    authority = grp.inspectorate_name if grp else None

    # Дата регистрации: профиль, затем ГРП.
    registration_date = dossier.get("registration_date")
    if not registration_date and grp and grp.registration_date:
        registration_date = grp.registration_date.isoformat()

    # Текущий ОКЭД.
    okved = None
    current_ved = _pick_current(dossier.get("ved", []))
    if current_ved:
        okved = current_ved.get("ved_code")

    # Юридический адрес. Приоритет источников совпадает с остальным сервисом
    # (публичный API/админка используют COALESCE(place_location, addresses_history)):
    #   1) egr_company_place_locations — самый свежий и полный источник,
    #   2) текущая запись истории адресов ЕГР,
    #   3) адрес из ГРП.
    address = None
    place_addr = dossier.get("place_location_address")
    current_addr = _pick_current(dossier.get("addresses", []))
    if place_addr:
        address = BitrixRequisiteAddress(
            full_address=place_addr,
            postal_code=current_addr.get("postal_code") if current_addr else None,
            region=current_addr.get("region") if current_addr else None,
        )
    elif current_addr and current_addr.get("full_address"):
        address = BitrixRequisiteAddress(
            full_address=current_addr.get("full_address"),
            postal_code=current_addr.get("postal_code"),
            region=current_addr.get("region"),
        )
    elif grp and grp.address:
        address = BitrixRequisiteAddress(full_address=grp.address)

    is_ip = _detect_is_ip(full_name or "", short_name or "", unp, dossier.get("entity_type_id"))
    director = _extract_director(full_name or "", short_name or "") if is_ip else None

    return BitrixRequisiteData(
        unp=unp_int,
        is_ip=is_ip,
        full_name=full_name,
        short_name=short_name,
        director=director,
        authority=authority,
        registration_date=registration_date,
        okved=okved,
        address=address,
    )
