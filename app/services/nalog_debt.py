"""
Р РЋР В±Р С•РЎР‚ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р С• Р В·Р В°Р Т‘Р С•Р В»Р В¶Р ВµР Р…Р Р…Р С•РЎРѓРЎвЂљР С‘ РЎРѓ portal.nalog.gov.by (GWT-RPC).
Р вЂ™Р Р…Р ВµР Т‘РЎР‚РЎвЂР Р…Р Р…Р В°РЎРЏ Р В»Р С•Р С–Р С‘Р С”Р В° Р С‘Р В· Start.py: Р С—Р В°РЎР‚РЎРѓР С‘Р Р…Р С–, Р Р†РЎвЂ№Р С–РЎР‚РЎС“Р В·Р С”Р В° Р С—Р С• РЎР‚Р ВµР С–Р С‘Р С•Р Р…Р В°Р С, РЎРѓР С•РЎвЂ¦РЎР‚Р В°Р Р…Р ВµР Р…Р С‘Р Вµ Р Р† JSON Р С‘/Р С‘Р В»Р С‘ Р Р† Р вЂР вЂќ.
"""
from __future__ import annotations

import concurrent.futures
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import requests

import uuid as uuid_pkg

# Р С›Р С—РЎвЂ Р С‘Р С•Р Р…Р В°Р В»РЎРЉР Р…РЎвЂ№Р Вµ Р С‘Р СР С—Р С•РЎР‚РЎвЂљРЎвЂ№ (Р Т‘Р В»РЎРЏ РЎР‚Р В°Р В±Р С•РЎвЂљРЎвЂ№ Р В±Р ВµР В· РЎС“РЎРѓРЎвЂљР В°Р Р…Р С•Р Р†Р В»Р ВµР Р…Р Р…РЎвЂ№РЎвЂ¦ Р В·Р В°Р Р†Р С‘РЎРѓР С‘Р СР С•РЎРѓРЎвЂљР ВµР в„– Р С—РЎР‚Р С‘Р В»Р С•Р В¶Р ВµР Р…Р С‘РЎРЏ)
try:
    from app.core.config import settings
    _HAS_SETTINGS = True
except ImportError:
    _HAS_SETTINGS = False
    # Fallback Р Т‘Р В»РЎРЏ РЎР‚Р В°Р В±Р С•РЎвЂљРЎвЂ№ Р В±Р ВµР В· Р С—РЎР‚Р С‘Р В»Р С•Р В¶Р ВµР Р…Р С‘РЎРЏ
    class _FakeSettings:
        NALOG_DEBT_OUT_DIR = "dolg_data"
    settings = _FakeSettings()

try:
    from app.core.logger import get_logger
    logger = get_logger("nalog_debt")
except ImportError:
    import logging
    logger = logging.getLogger("nalog_debt")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

BASE = "https://www.portal.nalog.gov.by"
REFERER = f"{BASE}/debtor/"
MODULE_BASE = f"{BASE}/debtor/debtoa/"
DISPATCH_URL = f"{BASE}/debtor/dispatch/SearchDataAction"

NOCACHE_URLS = [
    f"{MODULE_BASE}debtoa.nocache.js",
    f"{MODULE_BASE}debtoa.nocache.js?v=1.0.30-3",
]

SERVICE_CLASS = "com.gwtplatform.dispatch.rpc.shared.DispatchService"
ACTION_CLASS = "by.sws.debtoa.shared.dispatch.SearchDataAction/2786161043"

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "text/x-gwt-rpc; charset=UTF-8",
    "Origin": BASE,
    "Referer": REFERER,
    "X-GWT-Module-Base": MODULE_BASE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.7",
}

RGN_LIST = ["100", "200", "300", "400", "500", "600", "700"]


# --- GWT-RPC parser ---
class GwtRpcParseError(RuntimeError):
    pass


@dataclass
class JsParser:
    s: str
    i: int = 0

    def skip_ws(self) -> None:
        n = len(self.s)
        while self.i < n and self.s[self.i] in " \t\r\n":
            self.i += 1

    def peek(self) -> Optional[str]:
        self.skip_ws()
        return None if self.i >= len(self.s) else self.s[self.i]

    def consume(self, ch: str) -> None:
        self.skip_ws()
        if self.i >= len(self.s) or self.s[self.i] != ch:
            raise GwtRpcParseError(f"Expected {ch!r} at pos {self.i}")
        self.i += 1

    def parse_number(self) -> int:
        self.skip_ws()
        start = self.i
        if self.i < len(self.s) and self.s[self.i] == "-":
            self.i += 1
        while self.i < len(self.s) and self.s[self.i].isdigit():
            self.i += 1
        if self.i == start or (self.s[start] == "-" and self.i == start + 1):
            raise GwtRpcParseError(f"Bad number at pos {start}")
        return int(self.s[start : self.i])

    def parse_string_literal(self) -> str:
        self.skip_ws()
        if self.i >= len(self.s) or self.s[self.i] != '"':
            raise GwtRpcParseError(f"Expected string at pos {self.i}")
        self.i += 1
        out: list[str] = []
        n = len(self.s)
        while self.i < n:
            c = self.s[self.i]
            if c == '"':
                self.i += 1
                return "".join(out)
            if c == "\\":
                self.i += 1
                if self.i >= n:
                    raise GwtRpcParseError("EOF in escape")
                esc = self.s[self.i]
                if esc in ['"', "\\", "/"]:
                    out.append(esc)
                elif esc == "b":
                    out.append("\b")
                elif esc == "f":
                    out.append("\f")
                elif esc == "n":
                    out.append("\n")
                elif esc == "r":
                    out.append("\r")
                elif esc == "t":
                    out.append("\t")
                elif esc == "u":
                    hexpart = self.s[self.i + 1 : self.i + 5]
                    if len(hexpart) < 4 or any(ch not in "0123456789abcdefABCDEF" for ch in hexpart):
                        raise GwtRpcParseError(f"Bad unicode escape at pos {self.i}")
                    out.append(chr(int(hexpart, 16)))
                    self.i += 4
                else:
                    out.append(esc)
                self.i += 1
                continue
            out.append(c)
            self.i += 1
        raise GwtRpcParseError("EOF in string")

    def parse_string_expr(self) -> str:
        parts = [self.parse_string_literal()]
        while True:
            self.skip_ws()
            if self.i < len(self.s) and self.s[self.i] == "+":
                self.i += 1
                parts.append(self.parse_string_literal())
            else:
                break
        return "".join(parts)

    def parse_value(self) -> Any:
        ch = self.peek()
        if ch == "[":
            return self.parse_array()
        if ch == '"':
            return self.parse_string_expr()
        if ch is None:
            raise GwtRpcParseError("Unexpected EOF")
        if ch == "-" or ch.isdigit():
            return self.parse_number()
        if self.s.startswith("null", self.i):
            self.i += 4
            return None
        if self.s.startswith("true", self.i):
            self.i += 4
            return True
        if self.s.startswith("false", self.i):
            self.i += 5
            return False
        raise GwtRpcParseError(f"Unexpected token at pos {self.i}: {self.s[self.i:self.i+30]!r}")

    def parse_array(self) -> list[Any]:
        self.consume("[")
        arr: list[Any] = []
        self.skip_ws()
        if self.peek() == "]":
            self.consume("]")
            return arr
        while True:
            arr.append(self.parse_value())
            self.skip_ws()
            ch = self.peek()
            if ch == ",":
                self.i += 1
                continue
            if ch == "]":
                self.i += 1
                break
            raise GwtRpcParseError(f"Expected ',' or ']' at pos {self.i}")
        return arr


def parse_gwt_rpc(raw_text: str) -> Any:
    t = raw_text.strip()
    if t.startswith("//EX"):
        raise GwtRpcParseError(t[:800])
    if not t.startswith("//OK"):
        raise GwtRpcParseError("Not a //OK response")
    payload = t[4:].lstrip()
    return JsParser(payload).parse_value()


def extract_items(resp_text: str) -> list[dict[str, Any]]:
    t = resp_text.strip()
    if t.startswith("{") or t.startswith("["):
        obj = json.loads(t)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        for k in ("items", "data", "result", "rows"):
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return []
    outer = parse_gwt_rpc(t)
    if not isinstance(outer, list) or len(outer) < 3:
        raise GwtRpcParseError("Unexpected outer format")
    result_arr = outer[2]
    if not isinstance(result_arr, list) or len(result_arr) < 2:
        raise GwtRpcParseError("Unexpected result format")
    data_str = result_arr[1]
    if not isinstance(data_str, str):
        raise GwtRpcParseError("Data is not a string")
    items = json.loads(data_str)
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def get_permutation(session: requests.Session, timeout: int = 30) -> str:
    last_err = None
    for url in NOCACHE_URLS:
        try:
            r = session.get(url, timeout=timeout, headers={"Referer": REFERER})
            if not r.ok:
                last_err = f"{url} -> {r.status_code}"
                continue
            txt = r.text
            m = re.search(r"/([0-9A-Fa-f]{32})\.cache\.js", txt)
            if m:
                return m.group(1).upper()
            m = re.search(r"strongName\s*=\s*['\"]([0-9A-Fa-f]{32})['\"]", txt)
            if m:
                return m.group(1).upper()
            c = re.findall(r"['\"]([0-9A-Fa-f]{32})['\"]", txt)
            if c:
                return c[0].upper()
            last_err = f"no permutation in {url}"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р С—Р С•Р В»РЎС“РЎвЂЎР С‘РЎвЂљРЎРЉ permutation Р В°Р Р†РЎвЂљР С•Р СР В°РЎвЂљР С‘РЎвЂЎР ВµРЎРѓР С”Р С‘: {last_err}")


def month_starts_asc(start: date, end: date) -> list[date]:
    s = date(start.year, start.month, 1)
    e = date(end.year, end.month, 1)
    out: list[date] = []
    d = s
    while d <= e:
        out.append(d)
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)
    return out


def ddmmyyyy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def build_payload(
    perm: str,
    dt_str: str,
    rgn: str,
    lmt: int = -1,
    recn: int = 0,
    imns: str = "",
) -> str:
    param = (
        "zadolj"
        f"`unp=`tbl=0`imns={imns}`nm=`dt={dt_str}`obl=`rgn={rgn}`lmt={lmt}`recn={recn}`order=nrefe desc"
    )
    return (
        "7|0|8|"
        f"{MODULE_BASE}|{perm}|"
        f"{SERVICE_CLASS}|execute|"
        "java.lang.String/2004016611|"
        "com.gwtplatform.dispatch.rpc.shared.Action|"
        f"{ACTION_CLASS}|"
        f"{param}|"
        "1|2|3|4|2|5|6|0|7|8|"
    )


def _headers_for_base(base_url: str) -> dict[str, str]:
    return {
        **DEFAULT_HEADERS,
        "Origin": base_url,
        "Referer": f"{base_url}/debtor/",
        "X-GWT-Module-Base": f"{base_url}/debtor/debtoa/",
    }


def _apply_cookie_header(session: requests.Session, cookie_header: str) -> None:
    for chunk in cookie_header.split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        session.cookies.set(name, value, domain="www.portal.nalog.gov.by", path="/")
        session.cookies.set(name, value, domain="lkfl.portal.nalog.gov.by", path="/")
        session.cookies.set(name, value, domain=".portal.nalog.gov.by", path="/")


def make_session(
    perm: str,
    jsessionid: Optional[str],
    cookie_header: Optional[str] = None,
) -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    s.headers["X-GWT-Permutation"] = perm
    cookie_header = (cookie_header or "").strip()
    if cookie_header:
        s.headers["Cookie"] = cookie_header
        _apply_cookie_header(s, cookie_header)
    elif jsessionid:
        s.headers["Cookie"] = f"JSESSIONID={jsessionid}"
        _apply_cookie_header(s, f"JSESSIONID={jsessionid}")
    return s


def _post_with_redirect_handling(
    session: requests.Session,
    url: str,
    body: bytes,
    timeout: float,
) -> requests.Response:
    response = session.post(url, data=body, timeout=timeout, allow_redirects=False)
    if response.is_redirect or response.is_permanent_redirect:
        location = response.headers.get("Location", "").strip()
        if not location:
            response.raise_for_status()
            return response
        redirected = requests.compat.urljoin(url, location)
        target = requests.utils.urlparse(redirected)
        target_base = f"{target.scheme}://{target.netloc}"
        redirected_response = session.post(
            redirected,
            data=body,
            timeout=timeout,
            allow_redirects=False,
            headers=_headers_for_base(target_base),
        )
        redirected_response.raise_for_status()
        return redirected_response
    response.raise_for_status()
    return response


def fetch_all_for_date_one_region(
    session: requests.Session,
    perm: str,
    dt_str: str,
    rgn: str,
    timeout: float,
    retries: int,
    errors_dir: Path,
) -> list[dict[str, Any]]:
    last_err: Optional[str] = None
    last_text: str = ""
    body = build_payload(perm=perm, dt_str=dt_str, rgn=rgn, lmt=-1, recn=0, imns="")
    for attempt in range(retries + 1):
        try:
            r = _post_with_redirect_handling(
                session=session,
                url=DISPATCH_URL,
                body=body.encode("utf-8"),
                timeout=timeout,
            )
            last_text = r.text
            return extract_items(last_text)
        except Exception as e:
            last_err = repr(e)
            time.sleep(min(1.2 + attempt * 0.8, 5.0))
    errors_dir.mkdir(parents=True, exist_ok=True)
    fname = errors_dir / f"bad_{dt_str.replace('.', '-')}_rgn{rgn}.txt"
    fname.write_text(last_text[:2_000_000], encoding="utf-8", errors="replace")
    raise RuntimeError(f"Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р С—Р С•Р В»РЎС“РЎвЂЎР С‘РЎвЂљРЎРЉ Р Т‘Р В°Р Р…Р Р…РЎвЂ№Р Вµ dt={dt_str} rgn={rgn}: {last_err}")


def normalize_imns_code(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    if s.isdigit():
        return s.zfill(3)
    return s


def extract_imns_code(row: dict[str, Any]) -> str:
    for k in ("imns", "mns", "distr", "imnsCode"):
        if k in row and row[k] not in (None, ""):
            return normalize_imns_code(row[k])
    return ""


def extract_imns_name(row: dict[str, Any]) -> str:
    for k in ("nms", "imns_name", "mnsName", "inspectName"):
        v = row.get(k)
        if v:
            return str(v).strip()
    return ""


def normalize_dgash(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s.split()[0] if s else ""


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_date_json(d: date, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "date": ddmmyyyy(d),
        "date_iso": d.isoformat(),
        "count": len(items),
        "items": items,
    }


def first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
    return None


def process_one_date(
    d: date,
    perm: str,
    jsessionid: Optional[str],
    cookie_header: Optional[str],
    out_dir: Path,
    timeout: float,
    retries: int,
    overwrite: bool,
    skip_existing: bool,
    sleep_min: float,
    sleep_max: float,
    errors_dir: Path,
) -> None:
    out_path = out_dir / f"{d.isoformat()}.json"
    if skip_existing and out_path.exists():
        return
    session = make_session(
        perm=perm,
        jsessionid=jsessionid,
        cookie_header=cookie_header,
    )
    dt_str = ddmmyyyy(d)
    out_items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for rgn in RGN_LIST:
        rows = fetch_all_for_date_one_region(
            session=session,
            perm=perm,
            dt_str=dt_str,
            rgn=rgn,
            timeout=timeout,
            retries=retries,
            errors_dir=errors_dir,
        )
        for row in rows:
            unp = str(row.get("unp") or "").strip()
            imns_code = extract_imns_code(row)
            imns_name = extract_imns_name(row)
            dt_val = str((row.get("dt") or dt_str)).strip()
            dgash_val = normalize_dgash(row.get("dgash"))
            key = (unp, imns_code, dt_val, dgash_val)
            if key in seen:
                continue
            seen.add(key)
            out_items.append({
                "unp": unp,
                "imns_code": imns_code,
                "imns_name": imns_name,
                "debt_date": dt_val,
                "repayment_date": dgash_val,
            })
        time.sleep(random.uniform(sleep_min, sleep_max))
    payload = build_date_json(d, out_items)
    if overwrite or (not out_path.exists()):
        atomic_write_json(out_path, payload)


def run_fetcher(
    start_date: str = "2017-01-01",
    end_date: str = "2026-01-01",
    out_dir: Optional[Path] = None,
    perm: str = "",
    jsessionid: Optional[str] = None,
    cookie_header: Optional[str] = None,
    timeout: float = 45.0,
    retries: int = 3,
    workers: int = 1,
    overwrite: bool = False,
    skip_existing: bool = False,
    sleep_min: float = 0.10,
    sleep_max: float = 0.30,
    mode: str = "range",
) -> Path:
    """Р вЂ”Р В°Р С—РЎС“РЎРѓР С” РЎРѓР В±Р С•РЎР‚Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦: Р Р†РЎвЂ№Р С–РЎР‚РЎС“Р В·Р С”Р В° Р Р† JSON Р С—Р С• Р Т‘Р В°РЎвЂљР В°Р С."""
    out_dir = out_dir or Path(settings.NALOG_DEBT_OUT_DIR)
    errors_dir = out_dir / "_errors"
    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "monthly":
        today = date.today()
        dates = [date(today.year, today.month, 1)]
    else:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        if start_d > end_d:
            raise ValueError("start Р Т‘Р С•Р В»Р В¶Р ВµР Р… Р В±РЎвЂ№РЎвЂљРЎРЉ <= end")
        dates = month_starts_asc(start_d, end_d)

    perm = (perm or "").strip().upper()
    if not perm:
        s = requests.Session()
        s.headers.update({
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
        })
        perm = get_permutation(s, timeout=int(timeout))
    if not re.fullmatch(r"[0-9A-F]{32}", perm):
        raise ValueError("perm Р Т‘Р С•Р В»Р В¶Р ВµР Р… Р В±РЎвЂ№РЎвЂљРЎРЉ 32-РЎРѓР С‘Р СР Р†Р С•Р В»РЎРЉР Р…РЎвЂ№Р С hex")

    workers = max(1, min(workers, 4))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                process_one_date,
                d=d,
                perm=perm,
                jsessionid=jsessionid,
                cookie_header=cookie_header,
                out_dir=out_dir,
                timeout=timeout,
                retries=retries,
                overwrite=overwrite,
                skip_existing=skip_existing,
                sleep_min=sleep_min,
                sleep_max=sleep_max,
                errors_dir=errors_dir,
            )
            for d in dates
        ]
        for f in concurrent.futures.as_completed(futs):
            f.result()
    logger.info("Р РЋР В±Р С•РЎР‚ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р В·Р В°Р Р†Р ВµРЎР‚РЎв‚¬РЎвЂР Р…: %s", out_dir)
    return out_dir


def load_json_file_to_db(json_path: Path, session) -> int:
    """
    Р вЂ”Р В°Р С–РЎР‚РЎС“Р В¶Р В°Р ВµРЎвЂљ Р С•Р Т‘Р С‘Р Р… JSON-РЎвЂћР В°Р в„–Р В» РЎРѓРЎР‚Р ВµР В·Р В° (Р Т‘Р В°РЎвЂљР В° Р Р† Р С‘Р СР ВµР Р…Р С‘: YYYY-MM-DD.json) Р Р† РЎвЂљР В°Р В±Р В»Р С‘РЎвЂ РЎС“ nalog_debt_records.
    Р вЂ™Р С•Р В·Р Р†РЎР‚Р В°РЎвЂ°Р В°Р ВµРЎвЂљ Р С”Р С•Р В»Р С‘РЎвЂЎР ВµРЎРѓРЎвЂљР Р†Р С• Р Р†РЎРѓРЎвЂљР В°Р Р†Р В»Р ВµР Р…Р Р…РЎвЂ№РЎвЂ¦ Р В·Р В°Р С—Р С‘РЎРѓР ВµР в„– (РЎРѓ РЎС“РЎвЂЎРЎвЂРЎвЂљР С•Р С ON CONFLICT DO NOTHING Р С‘Р В»Р С‘ merge).
    """
    from app.database.models import NalogDebtRecord
    from sqlalchemy.dialects.postgresql import insert

    stem = json_path.stem
    try:
        slice_d = datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("Р СџРЎР‚Р С•Р С—РЎС“РЎРѓР С” РЎвЂћР В°Р в„–Р В»Р В° (Р Р…Р Вµ Р Т‘Р В°РЎвЂљР В° Р Р† Р С‘Р СР ВµР Р…Р С‘): %s", json_path)
        return 0

    text = json_path.read_text(encoding="utf-8")
    data = json.loads(text)
    items = data.get("items") if isinstance(data, dict) else []
    if not items:
        return 0

    to_insert = []
    for it in items:
        unp_s = str(first_present(it, "unp", "\u0423\u041d\u041f") or "").strip()
        if not unp_s or not unp_s.isdigit():
            continue
        debtor_unp = int(unp_s)
        imns_code = (it.get("imns_code") or "").strip()[:10]
        imns_name = (it.get("imns_name") or "")[:500] if it.get("imns_name") else None
        debt_date = str(first_present(it, "debt_date", "\u0414\u0430\u0442\u0430 \u0437\u0430\u0434\u043e\u043b\u0436\u0435\u043d\u043d\u043e\u0441\u0442\u0438") or "")[:50]
        repayment_date = str(first_present(it, "repayment_date", "\u0414\u0430\u0442\u0430 \u043f\u043e\u0433\u0430\u0448\u0435\u043d\u0438\u044f \u0437\u0430\u0434\u043e\u043b\u0436\u0435\u043d\u043d\u043e\u0441\u0442\u0438") or "")[:50]
        to_insert.append({
            "id": uuid_pkg.uuid4(),
            "debtor_unp": debtor_unp,
            "imns_code": imns_code,
            "imns_name": imns_name,
            "debt_date": debt_date,
            "repayment_date": repayment_date,
            "slice_date": slice_d,
        })

    if not to_insert:
        return 0

    # Событие подписки tax_debt: УНП, появившиеся в этом срезе, но отсутствовавшие
    # в предыдущем (новые должники). emit_company_event отсекает неотслеживаемых.
    try:
        from sqlalchemy import func as _sa_func
        from app.services.subscription_events import emit_company_event, EVENT_TAX_DEBT

        current_unps = {row["debtor_unp"] for row in to_insert}
        prev_slice = (
            session.query(_sa_func.max(NalogDebtRecord.slice_date))
            .filter(NalogDebtRecord.slice_date < slice_d)
            .scalar()
        )
        prev_unps: set[int] = set()
        if prev_slice is not None:
            prev_unps = {
                r[0]
                for r in session.query(NalogDebtRecord.debtor_unp)
                .filter(NalogDebtRecord.slice_date == prev_slice)
                .distinct()
                .all()
            }
        for unp in current_unps - prev_unps:
            emit_company_event(session, unp, EVENT_TAX_DEBT,
                               new_value=f"задолженность на {slice_d.isoformat()}")
    except Exception:
        # Эмиссия событий не должна валить импорт задолженностей.
        pass

    stmt = insert(NalogDebtRecord).values(to_insert)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[
            NalogDebtRecord.debtor_unp,
            NalogDebtRecord.imns_code,
            NalogDebtRecord.debt_date,
            NalogDebtRecord.repayment_date,
            NalogDebtRecord.slice_date,
        ]
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount if hasattr(result, "rowcount") else len(to_insert)


def run_import_to_db(json_dir: Path, session) -> int:
    """Р ВР СР С—Р С•РЎР‚РЎвЂљ Р Р†РЎРѓР ВµРЎвЂ¦ JSON-РЎвЂћР В°Р в„–Р В»Р С•Р Р† Р С‘Р В· Р С”Р В°РЎвЂљР В°Р В»Р С•Р С–Р В° Р Р† Р вЂР вЂќ. Р ВР СР ВµР Р…Р В° РЎвЂћР В°Р в„–Р В»Р С•Р Р†: YYYY-MM-DD.json."""
    total = 0
    for path in sorted(json_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            n = load_json_file_to_db(path, session)
            total += n
            logger.info("Р ВР СР С—Р С•РЎР‚РЎвЂљ %s: %s Р В·Р В°Р С—Р С‘РЎРѓР ВµР в„–", path.name, n)
        except Exception as e:
            logger.exception("Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р С‘Р СР С—Р С•РЎР‚РЎвЂљР В° %s: %s", path, e)
    return total
