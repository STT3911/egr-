"""УНП generation / validation for directed brute-force enumeration.

Назначение: получить юрлица (в т.ч. бюджетные организации и госорганы), которых
НЕТ в ЕГР-перечислении `getRegNumByState`, но которые стоят на учёте в ГРП.
Полный перебор 10^9 бессмыслен — 9-я цифра контрольная, поэтому свободны только
первые 8 знаков, а первый знак задаёт регион. Это даёт ~90.9 млн валидных УНП
(≈64 млн для регионов 1..7), которые дополнительно режутся дедупликацией против
уже известных УНП и ограничением диапазона порядковых номеров.

Алгоритм контрольной цифры (проверен на реальных УНП 100582333→3, 600032395→5,
491038130→0):
  веса позиций 1..8 = (29, 23, 19, 17, 13, 7, 5, 3)
  control = (Σ digit_i * weight_i) % 11
  если остаток == 10 — номер невалиден (МНС такие не присваивает).

ВНИМАНИЕ: ходящие по сети формулы с весами [29,19,17,13,7,5,3,1] и
[2,3,4,5,6,7,2,3] — НЕВЕРНЫ (дают неверную контрольную цифру).
"""

from __future__ import annotations

from typing import Iterable, Iterator, Optional, Set

# Веса позиций 1..8 (слева направо). НЕ менять — выверено на реальных УНП.
WEIGHTS = (29, 23, 19, 17, 13, 7, 5, 3)

# Первые знаки, реально используемые для юрлиц (код региона регистрации).
# Уточнить по своей БД: SELECT DISTINCT left(unp::text, 1) FROM grp_taxpayer_data;
DEFAULT_REGIONS = (1, 2, 3, 4, 5, 6, 7)

# Длина порядкового номера (знаки 2..8) и его максимум.
SEQ_DIGITS = 7
SEQ_MAX = 10 ** SEQ_DIGITS - 1  # 9_999_999


def control_digit(body8: str) -> Optional[int]:
    """Контрольная (9-я) цифра по первым 8 знакам.

    Возвращает 0..9, либо None если остаток == 10 (невалидный УНП).
    Ожидает строку ровно из 8 цифр.
    """
    s = 0
    for i in range(8):
        s += int(body8[i]) * WEIGHTS[i]
    r = s % 11
    return None if r == 10 else r


def is_valid_unp(unp: str) -> bool:
    """True, если строка — корректный 9-значный УНП юрлица (цифры + контроль)."""
    if not (isinstance(unp, str) and len(unp) == 9 and unp.isdigit()):
        return False
    cd = control_digit(unp)
    return cd is not None and cd == int(unp[8])


def build_unp(region: int, seq: int) -> Optional[str]:
    """Собрать УНП из первого знака (регион) и порядкового номера (7 знаков).

    Возвращает 9-значную строку, либо None если комбинация невалидна (остаток 10).
    """
    body = f"{region}{seq:0{SEQ_DIGITS}d}"
    cd = control_digit(body)
    if cd is None:
        return None
    return body + str(cd)


def iter_candidate_unps(
    regions: Iterable[int] = DEFAULT_REGIONS,
    seq_start: int = 0,
    seq_end: int = SEQ_MAX,
    exclude: Optional[Set[int]] = None,
) -> Iterator[str]:
    """Поток валидных УНП-кандидатов, которых нет в `exclude`.

    `exclude` — множество УЖЕ известных УНП (int) для дедупликации, чтобы не
    долбить ГРП по тому, что уже есть в БД.
    """
    exclude = exclude or set()
    for region in regions:
        for seq in range(seq_start, seq_end + 1):
            unp = build_unp(region, seq)
            if unp is not None and int(unp) not in exclude:
                yield unp


def count_candidates(
    regions: Iterable[int] = DEFAULT_REGIONS,
    seq_start: int = 0,
    seq_end: int = SEQ_MAX,
) -> int:
    """Оценка числа валидных УНП в диапазоне (без учёта дедупа).

    Остатки по модулю 11 распределены практически равномерно, поэтому ~1/11
    тел невалидны (остаток 10). Возвращает аналитическую оценку без перебора.
    """
    span = max(0, seq_end - seq_start + 1)
    n_regions = sum(1 for _ in regions)
    return round(span * n_regions * 10 / 11)
