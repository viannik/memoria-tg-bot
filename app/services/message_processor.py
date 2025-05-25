from app.utils.logging_config import logger, log_exception, log_function_call
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from aiogram import types
from tortoise.transactions import in_transaction

from app.models.db_models import User, Chat, Message, Media, ChunkEmbedding
from app.services.chunking import refresh_latest_chunk_for_chat

@log_function_call
async def process_message(message: types.Message) -> Optional[str]:
    """Process an incoming message and return a response if needed"""
    try:
        # Save the message to the database
        saved_msg = await save_message(message)
        # Refresh chunk for this chat
        await refresh_latest_chunk_for_chat(saved_msg.chat_id)
        logger.info(f"Message {message.message_id} from {message.from_user.username} processed successfully")
        return None
    except Exception as e:
        log_exception(e)
        logger.error(f"Error processing message {message.message_id}: {str(e)}")
        return None

async def save_message(message: types.Message) -> Message:
    """Save a message to the database with full support for new DB structure."""
    # Get or create user
    user, _ = await User.get_or_create(
        id=message.from_user.id,
        defaults={
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'username': message.from_user.username,
            'language_code': getattr(message.from_user, 'language_code', None)
        }
    )

    # Get or create chat
    chat, _ = await Chat.get_or_create(
        id=message.chat.id,
        defaults={
            'type': message.chat.type,
            'title': getattr(message.chat, 'title', None),
            'username': getattr(message.chat, 'username', None)
        }
    )

    # Prepare FK for reply and forward fields
    reply_to_message = None
    if message.reply_to_message:
        reply_to_message = await Message.get_or_none(id=message.reply_to_message.message_id)

    forward_from_user = None
    if getattr(message, 'forward_from', None):
        forward_from_user = await User.get_or_none(id=message.forward_from.id)

    forward_from_chat = None
    if getattr(message, 'forward_from_chat', None):
        forward_from_chat = await Chat.get_or_none(id=message.forward_from_chat.id)

    forward_from_message = None
    if getattr(message, 'forward_from_message_id', None):
        forward_from_message = await Message.get_or_none(id=message.forward_from_message_id)

    # Handle media
    media_obj = None
    media_type = None
    media_content = None

    # Telegram message can have only one media type at a time
    if message.photo:
        media_type = 'photo'
        photo = message.photo[-1]
        media_obj, _ = await Media.get_or_create(
            file_unique_id=photo.file_unique_id,
            defaults={
                'media_type': 'photo',
                'file_id': photo.file_id,
                'file_size': photo.file_size,
                'width': photo.width,
                'height': photo.height,
                'caption': message.caption,
            }
        )
    elif message.animation:
        media_type = 'animation'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.animation.file_unique_id,
            defaults={
                'media_type': 'animation',
                'file_id': message.animation.file_id,
                'file_size': message.animation.file_size,
                'duration': message.animation.duration,
                'caption': message.caption,
            }
        )
    elif message.audio:
        media_type = 'audio'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.audio.file_unique_id,
            defaults={
                'media_type': 'audio',
                'file_id': message.audio.file_id,
                'file_size': message.audio.file_size,
                'duration': message.audio.duration,
                'mime_type': getattr(message.audio, 'mime_type', None),
                'caption': message.caption,
            }
        )
    elif message.document:
        media_type = 'document'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.document.file_unique_id,
            defaults={
                'media_type': 'document',
                'file_id': message.document.file_id,
                'file_size': message.document.file_size,
                'mime_type': getattr(message.document, 'mime_type', None),
                'caption': message.caption,
            }
        )
    elif message.video:
        media_type = 'video'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.video.file_unique_id,
            defaults={
                'media_type': 'video',
                'file_id': message.video.file_id,
                'file_size': message.video.file_size,
                'width': message.video.width,
                'height': message.video.height,
                'duration': message.video.duration,
                'caption': message.caption,
            }
        )
    elif message.voice:
        media_type = 'voice'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.voice.file_unique_id,
            defaults={
                'media_type': 'voice',
                'file_id': message.voice.file_id,
                'file_size': message.voice.file_size,
                'duration': message.voice.duration,
            }
        )
    elif message.sticker:
        media_type = 'sticker'
        media_obj, _ = await Media.get_or_create(
            file_unique_id=message.sticker.file_unique_id,
            defaults={
                'media_type': 'sticker',
                'file_id': message.sticker.file_id,
                'width': message.sticker.width,
                'height': message.sticker.height,
            }
        )
    # Prepare message data
    # Serialize entities/caption_entities if present
    def serialize_entities(entities):
        if not entities:
            return None
        return [entity.model_dump() if hasattr(entity, 'model_dump') else entity.__dict__ for entity in entities]

    message_data = {
        'id': message.message_id,
        'from_user': user,
        'chat': chat,
        'date': message.date if hasattr(message, 'date') else datetime.now(timezone.utc),
        'text': message.text or message.caption,
        'entities': serialize_entities(message.entities or getattr(message, 'caption_entities', None)),
        'media': media_obj,
        'reply_to_message': reply_to_message,
        'forward_from_user': forward_from_user,
        'forward_from_chat': forward_from_chat,
        'forward_from_message': forward_from_message,
        'forward_sender_name': getattr(message, 'forward_sender_name', None),
    }

    # Save the message
    message_obj, _ = await Message.get_or_create(id=message.message_id, defaults=message_data)
    return message_obj

async def create_chunks_for_chat(chat_id: int):
    """Create chunks for messages in a chat"""
    return None
