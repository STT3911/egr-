"""EGR API clients"""
import os
from pathlib import Path

import httpx
from typing import Optional, List, Dict, Any, Union
from app.core.logger import get_logger

logger = get_logger("egr_client")


def _httpx_ssl_verify() -> Union[bool, str]:
    """
    Цепочка доверия для HTTPS.

    egr.gov.by отдаёт leaf без intermediate; в образе добавляем intermediate в
    /usr/local/share/ca-certificates и update-ca-certificates → полный bundle в
    /etc/ssl/certs/ca-certificates.crt.

    httpx с verify=True по умолчанию опирается на certifi, где этой цепочки нет,
    поэтому в контейнере явно используем системный bundle, если файл есть.
    """
    flag = os.environ.get("HTTPX_SSL_VERIFY", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        p = os.environ.get(key)
        if p and Path(p).is_file():
            return p
    system_ca = Path("/etc/ssl/certs/ca-certificates.crt")
    if system_ca.is_file():
        return str(system_ca)
    return True


class BaseClient:
    """Base HTTP client with connection pooling"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Connection pool for better performance
        self._client = None
        # Увеличенный пул соединений и таймаут ожидания соединения,
        # чтобы снизить вероятность PoolTimeout при массовых запросах.
        self._limits = httpx.Limits(
            max_keepalive_connections=50,
            max_connections=200,
        )
        self._timeout = httpx.Timeout(
            30.0,      # общий timeout
            connect=10.0,
            read=30.0,
            write=30.0,
            pool=60.0,  # сколько ждём свободное соединение из пула
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pool"""
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=headers,
                verify=_httpx_ssl_verify(),
                limits=self._limits,
                http2=True  # Enable HTTP/2 for better performance
            )
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """
        Make HTTP request with detailed error logging.
        
        В лог уходит:
        - HTTP статус (если был ответ)
        - первые ~300 символов тела ответа (если есть)
        - тип и текст исключения
        """
        url = f"{self.base_url}/{endpoint}"
        client = await self._get_client()

        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            resp = e.response
            body_preview = ""
            try:
                body_preview = resp.text[:300]
            except Exception:
                body_preview = "<unreadable body>"
            logger.error(
                "API HTTP error (%s %s) status=%s url=%s body=%r",
                method,
                endpoint,
                resp.status_code,
                str(resp.url),
                body_preview,
            )
            return None
        except httpx.RequestError as e:
            # Проблемы сети/таймауты/разрыв соединения
            logger.error(
                "API Request Error (%s %s): %s",
                method,
                url,
                repr(e),
            )
            return None
        except Exception as e:
            # Непредвиденные ошибки (JSONDecodeError и т.п.)
            logger.exception(
                "API Unexpected Error (%s %s): %s",
                method,
                url,
                repr(e),
            )
            return None


class MobileEGRClient(BaseClient):
    """Client for https://egr.gov.by/egrmobile/api/v1"""
    
    def __init__(self, base_url: str = "https://egr.gov.by/egrmobile/api/v1"):
        super().__init__(base_url)
    
    async def get_common_info(self, identifier: str) -> Optional[Dict]:
        """Get common company information"""
        # egrmobile использует:
        # - pan: УНП (9 цифр)
        # - unn: альтернативный идентификатор (для ИП/прочего, когда не 9 цифр)
        params = {"pan": identifier} if identifier.isdigit() and len(identifier) == 9 else {"unn": identifier}
        return await self._make_request("GET", "extracts/commonInfo", params=params)

    async def get_place_location(self, identifier: str) -> Optional[Dict]:
        """Get company location"""
        # В ссылке пользователя используется pan={company_unp}
        params = {"pan": identifier} if identifier.isdigit() and len(identifier) == 9 else {"unn": identifier}
        return await self._make_request("GET", "extracts/placeLocation", params=params)


class EGRClient(BaseClient):
    """Client for https://egr.gov.by/api/v2/egr (HTTPS)"""
    
    def __init__(self, base_url: str = "https://egr.gov.by/api/v2/egr"):
        super().__init__(base_url)

    async def get_base_info_by_period_raw(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Get base info for period (single request)
        WARNING: API has limit ~2500 records per request!
        """
        endpoint = f"getBaseInfoByPeriod/{start_date}/{end_date}"
        result = await self._make_request("GET", endpoint)
        return result if isinstance(result, list) else []
    
    async def get_base_info_by_period(
        self, 
        start_date: str, 
        end_date: str,
        auto_split: bool = True
    ) -> List[Dict]:
        """
        Get base info for period with automatic splitting if API limit reached
        
        Args:
            start_date: Date in DD.MM.YYYY format
            end_date: Date in DD.MM.YYYY format
            auto_split: Auto-split period by days if limit reached
            
        Returns:
            Complete list of companies for the period
        """
        from datetime import datetime, timedelta
        
        result = await self.get_base_info_by_period_raw(start_date, end_date)
        
        if not result or len(result) < 2500 or not auto_split:
            return result
        
        # Hit API limit - split by days
        logger.warning(
            f"⚠️  Got {len(result)} records (API limit). Splitting period by days..."
        )
        
        start = datetime.strptime(start_date, "%d.%m.%Y")
        end = datetime.strptime(end_date, "%d.%m.%Y")
        
        all_records = []
        seen_unps = set()
        current = start
        
        while current <= end:
            day_str = current.strftime("%d.%m.%Y")
            day_result = await self.get_base_info_by_period_raw(day_str, day_str)
            
            if day_result:
                for record in day_result:
                    unp = record.get("ngrn") or record.get("vunp")
                    if unp and unp not in seen_unps:
                        all_records.append(record)
                        seen_unps.add(unp)
                
                if len(day_result) >= 2500:
                    logger.error(
                        f"❌ {day_str}: {len(day_result)} records - API limit hit even for single day!"
                    )
            
            current += timedelta(days=1)
        
        logger.info(f"✅ Complete: {len(all_records)} unique records for {start_date} - {end_date}")
        
        return all_records
        
    async def get_events_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get events for period"""
        endpoint = f"getEventByPeriod/{start_date}/{end_date}"
        result = await self._make_request("GET", endpoint)
        return result if isinstance(result, list) else []

    async def get_base_info(self, unp: int) -> Optional[Dict]:
        """Get base company info"""
        result = await self._make_request("GET", f"getBaseInfoByRegNum/{unp}")
        # API может вернуть list с одним элементом или dict
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        return result if isinstance(result, dict) else None

    async def get_all_addresses(self, unp: int) -> List[Dict]:
        """Get all addresses"""
        res = await self._make_request("GET", f"getAllAddressByRegNum/{unp}")
        return res if isinstance(res, list) else []

    async def get_all_ved(self, unp: int) -> List[Dict]:
        """Get all VED codes"""
        res = await self._make_request("GET", f"getAllVEDByRegNum/{unp}")
        return res if isinstance(res, list) else []

    async def get_all_jur_names(self, unp: int) -> List[Dict]:
        """Get all juridical names"""
        res = await self._make_request("GET", f"getAllJurNamesByRegNum/{unp}")
        return res if isinstance(res, list) else []

    async def get_all_ip_fio(self, unp: int) -> List[Dict]:
        """Get all IP FIO"""
        res = await self._make_request("GET", f"getAllIPFIOByRegNum/{unp}")
        return res if isinstance(res, list) else []

    async def get_full_company_history(self, unp: int) -> Optional[Dict[str, Any]]:
        """Get full company history with all data"""
        import asyncio
        
        base_info = await self.get_base_info(unp)
        if not base_info:
            return None

        tasks = [
            self.get_all_addresses(unp),
            self.get_all_ved(unp)
        ]
        
        is_juridical = base_info.get("nsi00211", {}).get("nkvob") == 1  # Corrected from nvob
        if is_juridical:
            tasks.append(self.get_all_jur_names(unp))
        else:
            tasks.append(self.get_all_ip_fio(unp))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        addresses = results[0] if not isinstance(results[0], Exception) else []
        ved = results[1] if not isinstance(results[1], Exception) else []
        names = results[2] if not isinstance(results[2], Exception) else []

        if not addresses or not ved or not names:
            logger.warning(
                "History fetch UNP %s: addresses=%s ved=%s names=%s juridical=%s",
                unp,
                len(addresses),
                len(ved),
                len(names),
                is_juridical,
            )

        return {
            "base_info": base_info,
            "addresses": addresses,
            "ved": ved,
            "names": names
        }
    
    # =====================================================
    # Current data methods (without history)
    # =====================================================
    
    async def get_address(self, unp: int) -> Optional[Dict]:
        """Get current address (without history)"""
        res = await self._make_request("GET", f"getAddressByRegNum/{unp}")
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return res if isinstance(res, dict) else None
    
    async def get_jur_name(self, unp: int) -> Optional[Dict]:
        """Get current juridical name (without history)"""
        res = await self._make_request("GET", f"getJurNamesByRegNum/{unp}")
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return res if isinstance(res, dict) else None
    
    async def get_ved_current(self, unp: int) -> Optional[Dict]:
        """Get current VED code (without history)"""
        res = await self._make_request("GET", f"getVEDByRegNum/{unp}")
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return res if isinstance(res, dict) else None
    
    async def get_ip_fio_current(self, unp: int) -> Optional[Dict]:
        """Get current IP FIO (without history)"""
        res = await self._make_request("GET", f"getIPFIOByRegNum/{unp}")
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return res if isinstance(res, dict) else None
    
    # =====================================================
    # Events methods
    # =====================================================
    
    async def get_events(self, unp: int) -> List[Dict]:
        """Get company events (registration, liquidation, bankruptcy, etc.)"""
        res = await self._make_request("GET", f"getEventByRegNum/{unp}")
        return res if isinstance(res, list) else []
    
    # =====================================================
    # Search methods
    # =====================================================
    
    async def get_short_info_by_name(self, name: str) -> List[Dict]:
        """Search companies by name"""
        res = await self._make_request("GET", f"getShortInfoByRegName/{name}")
        return res if isinstance(res, list) else []
    
    async def get_short_info(self, unp: int) -> Optional[Dict]:
        """Get short company info"""
        res = await self._make_request("GET", f"getShortInfoByRegNum/{unp}")
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return res if isinstance(res, dict) else None
    
    async def get_reg_nums_by_state(self, state: int) -> List[int]:
        """
        Get list of UNPs by company state
        
        States:
        1 - Действующий
        2 - Исключен из ЕГР
        3 - Находится в процессе ликвидации
        4 - Процедура банкротства
        5 - Прекращение деятельности в результате реорганизации
        6 - Переход в другой РО
        7 - Переход в другой ТО
        8 - Прекращение деятельности в прежней ОПФ
        9 - Ошибка
        10 - Приостановлена деятельность
        11 - Утрата правоспособности
        12 - Регистрация аннулирована
        13 - Двойная регистрация
        """
        res = await self._make_request("GET", f"getRegNumByState/{state}")
        if isinstance(res, list):
            # Extract UNP from each record
            unps = []
            for record in res:
                if isinstance(record, dict):
                    unp = record.get("ngrn")
                    if unp:
                        unps.append(unp)
                elif isinstance(record, int):
                    unps.append(record)
            return unps
        return []
    
    # =====================================================
    # Period-based methods
    # =====================================================
    
    async def get_addresses_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get addresses for period"""
        res = await self._make_request("GET", f"getAddressByPeriod/{start_date}/{end_date}")
        return res if isinstance(res, list) else []
    
    async def get_jur_names_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get juridical names for period"""
        res = await self._make_request("GET", f"getJurNamesByPeriod/{start_date}/{end_date}")
        return res if isinstance(res, list) else []
    
    async def get_ved_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get VED codes for period"""
        res = await self._make_request("GET", f"getVEDByPeriod/{start_date}/{end_date}")
        return res if isinstance(res, list) else []
    
    async def get_ip_fio_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get IP FIO for period"""
        res = await self._make_request("GET", f"getIPFIOByPeriod/{start_date}/{end_date}")
        return res if isinstance(res, list) else []
    
    async def get_short_info_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Get short info for period"""
        res = await self._make_request("GET", f"getShortInfoByPeriod/{start_date}/{end_date}")
        return res if isinstance(res, list) else []

