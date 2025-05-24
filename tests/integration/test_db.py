import asyncio
import logging
from tortoise import Tortoise
from app.db import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_connection():
    try:
        # Initialize the database connection
        await init_db()
        logger.info("Successfully connected to the database")
        
        # Test creating a simple table
        await Tortoise.generate_schemas()
        logger.info("Successfully generated database schema")
        
        # Test vector extension
        conn = Tortoise.get_connection("default")
        result = await conn.execute_query(
            "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'vector'"
        )
        logger.info(f"pgvector extension info: {result}")
        
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
    finally:
        await close_db()

if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection())
        if success:
            print("[SUCCESS] Database connection test passed!")
        else:
            print("[ERROR] Database connection test failed!")
            exit(1)
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")
        exit(1)
