"""Logging configuration"""
import logging
import sys
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("egr_aggregator")

def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(f"egr_aggregator.{name}")






