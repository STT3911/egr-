"""Reference tables endpoints (Справочники)"""
from fastapi import APIRouter, HTTPException, Path, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any
from app.core.database import get_db
from app.core.logger import get_logger

logger = get_logger("api.references")
router = APIRouter()

# List of available reference tables
REFERENCE_TABLES = {
    "statuses": "ref_statuses",
    "creation-methods": "ref_creation_methods",
    "entity-types": "ref_entity_types",
    "authorities": "ref_authorities",
    "liquidation-methods": "ref_liquidation_methods",
    "ved": "ref_ved",
    "countries": "ref_countries",
    "soato": "ref_soato",
    "foundations": "ref_foundations",
    "events": "ref_events",
    "street-types": "ref_street_types",
    "room-types": "ref_room_types",
    "room-categories": "ref_room_categories",
    "settlement-types": "ref_settlement_types",
    "document-types": "ref_document_types",
    "currencies": "ref_currencies",
    "positions": "ref_positions",
    "opf": "ref_opf"
}


@router.get("/")
async def list_reference_types():
    """
    Получить список доступных справочников
    """
    return {
        "available_references": list(REFERENCE_TABLES.keys()),
        "description": {
            "statuses": "Статусы компаний (TSI00219)",
            "creation-methods": "Способы создания (TSI00208)",
            "entity-types": "Виды объектов ЮЛ/ИП (TSI00211)",
            "authorities": "Органы ЕГР (TSI00212)",
            "liquidation-methods": "Способы ликвидации (TSI00228)",
            "ved": "Виды экономической деятельности (TSI00114)",
            "countries": "Страны мира (TSI00201)",
            "soato": "СОАТО - территории РБ (TSI00202)",
            "foundations": "Основания для внесения (TSI00213)",
            "events": "События субъектов (TSI00223)",
            "street-types": "Типы улиц (TSI00226)",
            "room-types": "Типы помещений (TSI00227)",
            "room-categories": "Виды помещений (TSI00234)",
            "settlement-types": "Типы населенных пунктов (TSI00239)",
            "document-types": "Виды документов (TSI00206)",
            "currencies": "Валюты (TSI00204)",
            "positions": "Должности (TSI00207)",
            "opf": "Организационно-правовые формы (TSI00203)"
        }
    }


@router.get("/{ref_type}")
async def get_reference_data(
    ref_type: str = Path(..., description="Тип справочника"),
    limit: int = 1000,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Получить данные справочника
    
    Параметры:
    - ref_type: тип справочника (например, 'statuses', 'ved', 'countries')
    - limit: количество записей (по умолчанию 1000)
    - offset: смещение для пагинации (по умолчанию 0)
    """
    # Validate reference type against whitelist
    if ref_type not in REFERENCE_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Reference type '{ref_type}' not found. Available types: {list(REFERENCE_TABLES.keys())}"
        )
    
    table_name = REFERENCE_TABLES[ref_type]
    
    # Additional security: validate table name format (alphanumeric and underscore only)
    if not table_name.replace('_', '').isalnum():
        logger.error(f"Invalid table name format: {table_name}")
        raise HTTPException(status_code=500, detail="Invalid table configuration")
    
    try:
        # Get total count - using text() with validated table name from whitelist
        count_query = text(f"SELECT COUNT(*) FROM {table_name}")
        total = db.execute(count_query).scalar()
        
        # Get data with pagination - using parameterized query for user input
        query = text(f"""
            SELECT * FROM {table_name}
            ORDER BY id
            LIMIT :limit OFFSET :offset
        """)
        
        result = db.execute(query, {"limit": limit, "offset": offset})
        
        # Convert to list of dicts
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in result]
        
        return {
            "ref_type": ref_type,
            "table_name": table_name,
            "total": total,
            "limit": limit,
            "offset": offset,
            "count": len(data),
            "data": data
        }
        
    except Exception as e:
        logger.error(f"Error fetching reference data for {ref_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ref_type}/{ref_id}")
async def get_reference_item(
    ref_type: str = Path(..., description="Тип справочника"),
    ref_id: int = Path(..., description="ID элемента справочника"),
    db: Session = Depends(get_db),
):
    """
    Получить элемент справочника по ID
    """
    # Validate reference type against whitelist
    if ref_type not in REFERENCE_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Reference type '{ref_type}' not found"
        )
    
    table_name = REFERENCE_TABLES[ref_type]
    
    # Additional security: validate table name format
    if not table_name.replace('_', '').isalnum():
        logger.error(f"Invalid table name format: {table_name}")
        raise HTTPException(status_code=500, detail="Invalid table configuration")
    
    try:
        # Using parameterized query for ref_id (user input)
        query = text(f"SELECT * FROM {table_name} WHERE id = :ref_id")
        result = db.execute(query, {"ref_id": ref_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Item with id {ref_id} not found in {ref_type}"
            )
        
        # Convert to dict
        columns = result.keys()
        data = dict(zip(columns, row))
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching reference item {ref_type}/{ref_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ref_type}/search")
async def search_reference(
    ref_type: str = Path(..., description="Тип справочника"),
    q: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Поиск в справочнике по названию
    """
    # Validate reference type against whitelist
    if ref_type not in REFERENCE_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Reference type '{ref_type}' not found"
        )
    
    table_name = REFERENCE_TABLES[ref_type]
    
    # Additional security: validate table name format
    if not table_name.replace('_', '').isalnum():
        logger.error(f"Invalid table name format: {table_name}")
        raise HTTPException(status_code=500, detail="Invalid table configuration")
    
    if not q:
        raise HTTPException(
            status_code=400,
            detail="Search query 'q' is required"
        )
    
    try:
        # Using parameterized query for search_term (user input)
        query = text(f"""
            SELECT * FROM {table_name}
            WHERE name ILIKE :search_term
            ORDER BY name
            LIMIT :limit
        """)
        
        result = db.execute(query, {
            "search_term": f"%{q}%",
            "limit": limit
        })
        
        # Convert to list of dicts
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in result]
        
        return {
            "ref_type": ref_type,
            "query": q,
            "count": len(data),
            "results": data
        }
        
    except Exception as e:
        logger.error(f"Error searching in {ref_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

