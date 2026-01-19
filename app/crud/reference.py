"""CRUD operations for reference tables"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logger import get_logger

logger = get_logger("crud.reference")


class ReferenceCRUD:
    """CRUD operations for reference tables"""
    
    VALID_TABLES = {
        "ref_statuses",
        "ref_creation_methods",
        "ref_entity_types",
        "ref_authorities",
        "ref_liquidation_methods",
        "ref_ved",
        "ref_countries",
        "ref_soato",
        "ref_foundations",
        "ref_events",
        "ref_street_types",
        "ref_room_types",
        "ref_room_categories",
        "ref_settlement_types",
        "ref_document_types",
        "ref_currencies",
        "ref_positions",
        "ref_opf"
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def _validate_table_name(self, table_name: str):
        """Validate that table name is one of the allowed reference tables"""
        if table_name not in self.VALID_TABLES:
            raise ValueError(f"Invalid table name: {table_name}")
    
    def get_all(self, table_name: str, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all items from a reference table
        
        Args:
            table_name: Name of reference table
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of reference items as dictionaries
        """
        self._validate_table_name(table_name)
        
        query = text(f"""
            SELECT * FROM {table_name}
            ORDER BY id
            LIMIT :limit OFFSET :offset
        """)
        
        result = self.db.execute(query, {"limit": limit, "offset": offset})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result]
    
    def get_by_id(self, table_name: str, ref_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a reference item by ID
        
        Args:
            table_name: Name of reference table
            ref_id: Reference item ID
            
        Returns:
            Reference item dictionary or None
        """
        self._validate_table_name(table_name)
        
        query = text(f"SELECT * FROM {table_name} WHERE id = :ref_id")
        result = self.db.execute(query, {"ref_id": ref_id})
        row = result.fetchone()
        
        if not row:
            return None
        
        columns = result.keys()
        return dict(zip(columns, row))
    
    def search(self, table_name: str, search_term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search in reference table by name
        
        Args:
            table_name: Name of reference table
            search_term: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching reference items
        """
        self._validate_table_name(table_name)
        
        query = text(f"""
            SELECT * FROM {table_name}
            WHERE name ILIKE :search_term
            ORDER BY name
            LIMIT :limit
        """)
        
        result = self.db.execute(query, {
            "search_term": f"%{search_term}%",
            "limit": limit
        })
        
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result]
    
    def count(self, table_name: str) -> int:
        """
        Get count of items in reference table
        
        Args:
            table_name: Name of reference table
            
        Returns:
            Number of items in table
        """
        self._validate_table_name(table_name)
        
        query = text(f"SELECT COUNT(*) FROM {table_name}")
        result = self.db.execute(query)
        return result.scalar()
    
    def bulk_upsert(self, table_name: str, items: List[Dict[str, Any]]):
        """
        Bulk insert or update reference items
        
        Args:
            table_name: Name of reference table
            items: List of reference items to upsert
        """
        self._validate_table_name(table_name)
        
        if not items:
            logger.warning(f"No items to upsert for {table_name}")
            return
        
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


