import asyncio
import time
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from app.config import TELEGRAM_BOT_TOKEN
from app.db import init_db, close_db
from app.utils.logging_config import logger

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Use a unique session name to prevent conflicts
session_name = f"bot_{int(time.time())}"
logger.info(f"Starting bot with session: {session_name}")

storage = MemoryStorage()
dp = Dispatcher(
    storage=storage,
    fsm_strategy=FSMStrategy.USER_IN_CHAT,
    name=session_name  # Add a unique name for this session
)

# Register handlers
from app.handlers import register_handlers

async def on_startup():
    """Actions to perform on bot startup"""
    logger.info("Starting Memoria Bot...")
    await init_db()
    logger.info("Bot started successfully")

async def on_shutdown():
    """Actions to perform on bot shutdown"""
    logger.info("Shutting down Memoria Bot...")
    await close_db()
    await dp.storage.close()
    logger.info("Bot shut down successfully")

async def main():
    """Main function to run the bot"""
    # Register handlers
    register_handlers(dp)
    
    # Start the bot
    try:
        await on_startup()
        
        # Delete any existing webhook
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Start polling with explicit parameters
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"Error in polling: {e}")
        raise
    finally:
        await on_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
