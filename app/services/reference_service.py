"""Service for managing reference tables (справочники)"""
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logger import get_logger
from app.core.database import SessionLocal

logger = get_logger("reference_service")


class ReferenceService:
    """Service for loading and managing reference data from EGR API"""
    
    # Mapping of reference table names to their extraction paths in JSON
    REFERENCE_MAPPINGS = {
        "ref_statuses": {
            "json_path": "nsi00219",
            "id_field": "nksost",
            "name_field": "vnsostk",
            "system_id": 219
        },
        "ref_creation_methods": {
            "json_path": "nsi00208",
            "id_field": "nkscrt",
            "name_field": "vnscrtp",
            "system_id": 208
        },
        "ref_entity_types": {
            "json_path": "nsi00211",
            "id_field": "nkvob",
            "name_field": "vnvobp",
            "system_id": 211
        },
        "ref_liquidation_methods": {
            "json_path": "nsi00228",
            "id_field": "nkslkv",
            "name_field": "vnslkvp",
            "system_id": 228
        },
        "ref_ved": {
            "json_path": "nsi00114",
            "id_field": "nsi00114",
            "code_field": "vkvdn",
            "name_field": "vnvdnp",
            "system_id": 114
        },
        "ref_countries": {
            "json_path": "nsi00201",
            "id_field": "nsi00201",
            "code_field": "nkstran",
            "name_field": "vnstranp",
            "system_id": 201
        },
        "ref_soato": {
            "json_path": "nsi00202",
            "id_field": "nsi00202",
            "code_field": "nksoato",
            "name_field": "vnsfull",
            "object_number_field": "objectnumber",
            "system_id": 202
        },
        "ref_foundations": {
            "json_path": "nsi00213",
            "id_field": "nsi00213",
            "code_field": "nkosn",
            "name_field": "vnosn",
            "system_id": 213
        },
        "ref_events": {
            "json_path": "nsi00223",
            "id_field": "nsi00223",
            "code_field": "nkop",
            "name_field": "vnop",
            "system_id": 223
        },
        "ref_street_types": {
            "json_path": "nsi00226",
            "id_field": "nsi00226",
            "code_field": "nktul",
            "name_field": "vntulk",
            "system_id": 226
        },
        "ref_room_types": {
            "json_path": "nsi00227",
            "id_field": "nsi00227",
            "code_field": "nktpom",
            "name_field": "vntpomk",
            "system_id": 227
        },
        "ref_room_categories": {
            "json_path": "nsi00234",
            "id_field": "nsi00234",
            "code_field": "nkvpom",
            "name_field": "vnvpom",
            "system_id": 234
        },
        "ref_settlement_types": {
            "json_path": "nsi00239",
            "id_field": "nsi00239",
            "code_field": "nktnp",
            "name_field": "vntnpk",
            "system_id": 239
        },
        "ref_document_types": {
            "json_path": "nsi00206",
            "id_field": "nsi00206",
            "code_field": "nkvdok",
            "name_field": "vnvdok",
            "system_id": 206
        },
        "ref_currencies": {
            "json_path": "nsi00204",
            "id_field": "nsi00204",
            "code_field": "nkvalut",
            "name_field": "vnvalutp",
            "system_id": 204
        },
        "ref_positions": {
            "json_path": "nsi00207",
            "id_field": "nsi00207",
            "code_field": "nkdolgn",
            "name_field": "vndolgnp",
            "system_id": 207
        },
        "ref_opf": {
            "json_path": "nsi00203",
            "id_field": "nsi00203",
            "code_field": "nkopf",
            "name_field": "vnopfp",
            "system_id": 203
        }
    }
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self._should_close_db = db is None
    
    def close(self):
        """Close database session if it was created by this service"""
        if self._should_close_db:
            self.db.close()
    
    def extract_references_from_raw_data(self) -> Dict[str, List[Dict]]:
        """
        Extract all reference data from egr_raw_company_data table
        
        Returns:
            Dictionary with table_name -> list of reference items
        """
        logger.info("Extracting reference data from egr_raw_company_data")
        
        references = {}
        
        # Query all raw data
        query = text("SELECT data FROM egr_raw_company_data WHERE data IS NOT NULL")
        result = self.db.execute(query)
        
        for row in result:
            data = row[0]
            if not isinstance(data, dict):
                continue
            
            base_info = data.get("base_info", {})
            
            # Extract data for each reference type
            for table_name, mapping in self.REFERENCE_MAPPINGS.items():
                if table_name not in references:
                    references[table_name] = {}
                
                json_path = mapping["json_path"]
                
                # Handle authorities which can be in multiple places
                if table_name == "ref_authorities":
                    for suffix in ["", "CRT", "LKV"]:
                        path = json_path + suffix
                        ref_data = base_info.get(path)
                        if ref_data and isinstance(ref_data, dict):
                            self._extract_reference_item(
                                ref_data, mapping, references[table_name]
                            )
                else:
                    ref_data = base_info.get(json_path)
                    if ref_data and isinstance(ref_data, dict):
                        self._extract_reference_item(
                            ref_data, mapping, references[table_name]
                        )
        
        # Convert dict to list
        for table_name in references:
            references[table_name] = list(references[table_name].values())
        
        logger.info(f"Extracted references: {[(k, len(v)) for k, v in references.items()]}")
        
        return references
    
    def _extract_reference_item(
        self, 
        ref_data: Dict, 
        mapping: Dict, 
        target_dict: Dict
    ):
        """Extract single reference item from JSON data"""
        ref_id = ref_data.get(mapping["id_field"])
        
        if not ref_id:
            return
        
        item = {
            "id": ref_id,
            "name": ref_data.get(mapping["name_field"], ""),
            "system_id": mapping["system_id"]
        }
        
        # Add optional fields
        if "code_field" in mapping:
            item["code"] = ref_data.get(mapping["code_field"])
        
        if "object_number_field" in mapping:
            item["object_number"] = ref_data.get(mapping["object_number_field"])
        
        # Store by ID to avoid duplicates
        target_dict[ref_id] = item
    
    def upsert_references(self, table_name: str, items: List[Dict]):
        """
        Bulk upsert reference items into specified table
        
        Args:
            table_name: Name of reference table
            items: List of reference items to insert/update
        """
        if not items:
            logger.warning(f"No items to upsert for {table_name}")
            return
        
        logger.info(f"Upserting {len(items)} items into {table_name}")
        
        # Build column list dynamically based on first item
        sample_item = items[0]
        columns = list(sample_item.keys())
        columns_str = ", ".join(columns)
        
        # Build placeholders for VALUES
        placeholders = ", ".join([f":{col}" for col in columns])
        
        # Build ON CONFLICT UPDATE clause
        update_cols = [col for col in columns if col != 'id']
        update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
        
        query = text(f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT (id) DO UPDATE SET {update_str}
        """)
        
        try:
            for item in items:
                self.db.execute(query, item)
            self.db.commit()
            logger.info(f"Successfully upserted {len(items)} items into {table_name}")
        except Exception as e:
            logger.error(f"Error upserting into {table_name}: {e}")
            self.db.rollback()
            raise
    
    def update_all_references(self):
        """Extract and update all reference tables from raw data"""
        logger.info("Starting full reference tables update")
        
        references = self.extract_references_from_raw_data()
        
        for table_name, items in references.items():
            if items:
                self.upsert_references(table_name, items)
        
        logger.info("Reference tables update completed")
    
    def get_reference_count(self, table_name: str) -> int:
        """Get count of records in reference table"""
        query = text(f"SELECT COUNT(*) FROM {table_name}")
        result = self.db.execute(query)
        return result.scalar()


