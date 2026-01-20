"""Service for mapping EGR data to DB structure"""
from typing import Dict, Any
from datetime import datetime
from app.core.logger import get_logger

logger = get_logger("mapper")


class CompanyMapper:
    """Service for transforming EGR data into DB structure"""

    # Mapping text statuses from Mobile API to codes (nsi00219)
    STATUS_MAPPING = {
        "Действующий": 1,
        "Ликвидация": 2,
        "В процессе ликвидации": 2,
        "Прекращение деятельности": 3,
        "Банкротство": 4,
        "Исключен": 5
    }

    def map_to_db_structure(self, unp: int, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main method: determines data format and calls appropriate parser
        """
        # Check if response is from Mobile API (new combined format)
        if "common_info" in raw_data:
            return self._map_mobile_api_combined(unp, raw_data)
        
        # Check if response is from Mobile API (old format)
        elif "unn" in raw_data and "fullNameRus" in raw_data:
            return self._map_mobile_api(unp, raw_data)
        
        # Check if response is from Legacy API
        elif "base_info" in raw_data:
            return self._map_legacy_api(unp, raw_data)

        # Base-info only payload (from JSON dumps)
        elif "ngrn" in raw_data or "NGRN" in raw_data:
            return self._map_legacy_api(unp, {"base_info": raw_data})
            
        else:
            logger.warning(f"Unknown data format for UNP {unp}")
            return self._get_empty_structure(unp)

    def _map_mobile_api_combined(self, unp: int, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse combined response from Mobile API (common_info + place_location)"""
        
        data = raw_data.get("common_info", {})
        location_data = raw_data.get("place_location", {})
        
        # Parse status from text to code
        status_text = data.get("state", "")
        status_code = self.STATUS_MAPPING.get(status_text)

        # Main company data
        company_data = {
            "unp": unp,
            "current_status_code": status_code,
            "registration_date": self._parse_iso_date(data.get("dateOfStateRegistration")),
            "liquidation_date": self._parse_iso_date(data.get("dateDecisionLiquidation")),  # Note: cyrillic 'с'
            "liquidation_decision_no": data.get("numberDecisionLiquidation"),  # Note: cyrillic 'с'
            "liquidation_reason_id": None,
            "liquidation_authority_id": None,
        }

        # Name history
        names_data = [{
            "full_name_ru": data.get("fullNameRus"),
            "short_name_ru": data.get("shortNameRus"),
            "full_name_by": data.get("fullNameBel"),
            "valid_from": self._parse_iso_date(data.get("dateOfStateRegistration")),
            "valid_to": None
        }]

        # Contacts
        contacts_data = []
        if any([data.get("email"), data.get("site"), data.get("phone"), data.get("fax")]):
            contacts_data.append({
                "email": data.get("email"),
                "website": data.get("site"),
                "phone": data.get("phone"),
                "fax": data.get("fax"),
                "valid_from": datetime.now().date(),
                "valid_to": None
            })

        # Parse addresses from place_location
        addresses_data = []
        if location_data and isinstance(location_data, dict):
            address_text = location_data.get("vpadres")
            region = location_data.get("region")
            district = location_data.get("district")
            
            if address_text:
                addresses_data.append({
                    "full_address": address_text,
                    "postal_code": None,
                    "region": region,
                    "district": district,
                    "valid_from": self._parse_iso_date(data.get("dateOfStateRegistration")),
                    "valid_to": None
                })

        # VED codes - not available in Mobile API
        ved_data = []

        return {
            "company": company_data,
            "names": names_data,
            "addresses": addresses_data,
            "ved": ved_data,
            "contacts": contacts_data
        }

    def _map_mobile_api(self, unp: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse response from Mobile API (flat JSON)"""
        
        # Parse status from text to code
        status_text = data.get("state", "")
        status_code = self.STATUS_MAPPING.get(status_text)

        # Main company data
        company_data = {
            "unp": unp,
            "current_status_code": status_code,
            "registration_date": self._parse_iso_date(data.get("dateOfStateRegistration")),
            "liquidation_date": self._parse_iso_date(data.get("dateDecisionLiquidation")),  # Note: cyrillic 'с'
            "liquidation_decision_no": data.get("numberDecisionLiquidation"),  # Note: cyrillic 'с'
            "liquidation_reason_id": None,  # Not in this JSON
            "liquidation_authority_id": None,
        }

        # Name history (taking current as actual)
        names_data = [{
            "full_name_ru": data.get("fullNameRus"),
            "short_name_ru": data.get("shortNameRus"),
            "full_name_by": data.get("fullNameBel"),
            "valid_from": self._parse_iso_date(data.get("dateOfStateRegistration")),
            "valid_to": None
        }]

        # Contacts (in root JSON)
        contacts_data = []
        if any([data.get("email"), data.get("site"), data.get("phone"), data.get("fax")]):
            contacts_data.append({
                "email": data.get("email"),
                "website": data.get("site"),
                "phone": data.get("phone"),
                "fax": data.get("fax"),
                "valid_from": datetime.now().date(),
                "valid_to": None
            })

        # Addresses - would need second request to placeLocation
        addresses_data = []

        return {
            "company": company_data,
            "addresses": addresses_data,
            "names": names_data,
            "ved": [],  # Not in commonInfo
            "contacts": contacts_data
        }

    def _map_legacy_api(self, unp: int, egr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse response from Legacy API (nested JSON)"""
        base_info = egr_data.get("base_info", {})
        
        company_data = {
            "unp": unp,
            "current_status_code": base_info.get("nsi00219", {}).get("nksost"),
            "registration_date": self._parse_legacy_date(base_info.get("dfrom")),
            "liquidation_date": self._parse_legacy_date(base_info.get("dto")),
            "liquidation_reason_id": base_info.get("nsi00228", {}).get("nkslkv"),
            "liquidation_decision_no": base_info.get("vnrlkv"),
            "liquidation_authority_id": base_info.get("nsi00212LKV", {}).get("nkuz"),
        }
        
        # Parse addresses - assemble full address from components
        addresses_data = []
        for addr in egr_data.get("addresses", []):
            # Assemble full address from components
            address_parts = []

            # Country
            country = addr.get("nsi00201", {}).get("vnstranp")
            if country and country != "Республика Беларусь":
                address_parts.append(country)

            # Region
            region = addr.get("vregion")
            if region:
                address_parts.append(region)

            # City/District
            city = addr.get("vnp")
            if city:
                # Add city type if available
                city_type = addr.get("nsi00239", {}).get("vntnpk", "")
                address_parts.append(f"{city_type} {city}".strip())

            # Street
            street = addr.get("vulitsa")
            if street:
                # Add street type if available
                street_type = addr.get("nsi00226", {}).get("vntulk", "")
                address_parts.append(f"{street_type} {street}".strip())

            # House
            house = addr.get("vdom")
            if house:
                address_parts.append(f"д. {house}")

            # Apartment/Office
            apartment = addr.get("vpom")
            if apartment:
                # Check if it's residential or office
                room_type = addr.get("nsi00234", {}).get("vnvpom")
                if room_type and "нежилое" in room_type.lower():
                    address_parts.append(f"оф. {apartment}")
                else:
                    address_parts.append(f"кв. {apartment}")

            full_address = ", ".join(address_parts) if address_parts else None

            addresses_data.append({
                "full_address": full_address,
                "postal_code": addr.get("nindex"),
                "region": addr.get("vregion"),
                "district": addr.get("nsi00202", {}).get("vnsfull"),  # More detailed district info
                "valid_from": self._parse_legacy_date(addr.get("dfrom")),
                "valid_to": self._parse_legacy_date(addr.get("dto")),
            })
        
        # Parse names
        names_data = []
        is_juridical = base_info.get("nsi00211", {}).get("nkvob") == 1  # Corrected from nvob
        
        for name in egr_data.get("names", []):
            if is_juridical:
                names_data.append({
                    "full_name_ru": name.get("vnaim"),
                    "short_name_ru": name.get("vn"),  # Corrected from vnaimk
                    "full_name_by": name.get("vnaimb"),  # Corrected from vnbel
                    "valid_from": self._parse_legacy_date(name.get("dfrom")),
                    "valid_to": self._parse_legacy_date(name.get("dto")),
                })
            else:
                # IP FIO - EGR API provides full name in 'vfio' field
                full_name = name.get("vfio", "").strip()
                if not full_name:
                    # Fallback to separate fields if vfio is empty
                    full_name = f"{name.get('vfam', '')} {name.get('vim', '')} {name.get('viotch', '')}".strip()

                names_data.append({
                    "full_name_ru": full_name,
                    "short_name_ru": full_name,
                    "full_name_by": None,
                    "valid_from": self._parse_legacy_date(name.get("dfrom")),
                    "valid_to": self._parse_legacy_date(name.get("dto")),
                })

        if not names_data:
            fallback_full = (
                base_info.get("vnaim")
                or base_info.get("VNAIM")
                or base_info.get("vfio")
                or base_info.get("VFIO")
            )
            fallback_short = (
                base_info.get("vnaimk")
                or base_info.get("VNAIMK")
                or base_info.get("vn")
                or base_info.get("VN")
            )
            fallback_by = (
                base_info.get("vnaimb")
                or base_info.get("VNAIMBY")
                or base_info.get("vnaimby")
            )
            if fallback_full or fallback_short or fallback_by:
                names_data.append({
                    "full_name_ru": fallback_full,
                    "short_name_ru": fallback_short or fallback_full,
                    "full_name_by": fallback_by,
                    "valid_from": self._parse_legacy_date(base_info.get("dfrom")),
                    "valid_to": self._parse_legacy_date(base_info.get("dto")),
                })
        
        # Parse VED
        ved_data = []
        for ved in egr_data.get("ved", []):
            ved_data.append({
                "ved_code": ved.get("nsi00118", {}).get("nkved"),
                "ved_name": ved.get("nsi00118", {}).get("vnved"),
                "valid_from": self._parse_legacy_date(ved.get("dfrom")),
                "valid_to": self._parse_legacy_date(ved.get("dto")),
            })

        # Parse contacts from addresses (Legacy API stores contacts in address records)
        contacts_data = []
        for addr in egr_data.get("addresses", []):
            contact_info = {}

            # Extract phone from vtels field
            phone = addr.get("vtels")
            if phone:
                # Clean phone number - remove extra spaces and normalize format
                phone = phone.strip()
                if phone and phone not in [",", "-", "+"]:  # Filter out empty phone entries
                    contact_info["phone"] = phone

            # Extract email from vemail field
            email = addr.get("vemail")
            if email:
                email = email.strip()
                if email:  # Filter out empty emails
                    contact_info["email"] = email

            # Only add contact if we have at least one field
            if contact_info:  # This checks if dict has any items
                contact_info.update({
                    "website": None,  # Legacy API doesn't have website
                    "fax": None,      # Legacy API doesn't have fax
                    "valid_from": self._parse_legacy_date(addr.get("dfrom")),
                    "valid_to": self._parse_legacy_date(addr.get("dto")),
                })
                contacts_data.append(contact_info)


        return {
            "company": company_data,
            "addresses": addresses_data,
            "names": names_data,
            "ved": ved_data,
            "contacts": contacts_data
        }

    def _get_empty_structure(self, unp: int) -> Dict:
        """Empty structure template"""
        return {
            "company": {"unp": unp},
            "addresses": [],
            "names": [],
            "ved": [],
            "contacts": []
        }

    def _parse_legacy_date(self, date_str: str) -> Any:
        """Parse DD.MM.YYYY format"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%d.%m.%Y").date()
        except (ValueError, TypeError):
            return None

    def _parse_iso_date(self, date_str: str) -> Any:
        """Parse ISO 8601: 2011-10-12T00:00:00.000+03:00"""
        if not date_str:
            return None
        try:
            # Take only date part YYYY-MM-DD
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

