import os
from typing import Optional
from tortoise import Tortoise
from tortoise.expressions import F

from app.config import (
    DATABASE_URL,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_HOST,
    POSTGRES_PORT,
    EMBEDDING_DIM,
)

# Check if we should use DATABASE_URL or build it from components
if not DATABASE_URL:
    DATABASE_URL = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

async def init_db():
    """Initialize database connection and set up pgvector extension"""
    await Tortoise.init(
        db_url=DATABASE_URL,
        modules={"models": ["app.models.db_models"]},
    )
    
    # Enable pgvector extension if not already enabled
    conn = Tortoise.get_connection("default")
    await conn.execute_query("CREATE EXTENSION IF NOT EXISTS vector")
    
    # Generate the schema
    await Tortoise.generate_schemas(safe=True)

async def close_db():
    """Close database connections"""
    await Tortoise.close_connections()

def get_db_url() -> str:
    """Get the database URL"""
    return DATABASE_URL
