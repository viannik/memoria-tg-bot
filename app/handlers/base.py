import logging
from aiogram import types, F, Router, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.services.chunking import auto_chunk_all_chats
from app.services.message_processor import process_message

# Create router
router = Router()
logger = logging.getLogger(__name__)

def register_handlers(dispatcher: Dispatcher):
    """Register all base command and message handlers"""
    dispatcher.include_router(router)

@router.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    """Handle /start and /help commands"""
    welcome_text = (
        "👋 Welcome to Memoria Bot!\n\n"
        "I can help you remember and retrieve information from your conversations.\n\n"
        "Just chat with me normally, and I'll remember the important parts.\n"
        "You can ask me about previous conversations, and I'll try to help!"
    )
    await message.answer(welcome_text)

@router.message(Command("chunk"))
async def cmd_chunk(message: types.Message):
    """Handle /chunk command"""
    await auto_chunk_all_chats()
    await message.answer("Chunking completed!")

@router.message()
async def handle_message(message: types.Message, state: FSMContext):
    """Handle incoming messages"""
    try:
        # Process the message (save to DB, create embeddings, etc.)
        response = await process_message(message)
        
        # If we have a response, send it back
        if response:
            await message.answer(response)
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        #await message.answer("Sorry, I encountered an error processing your message. Please try again later.")
