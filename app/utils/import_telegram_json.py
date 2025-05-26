"""
Telegram JSON Import Utility

This module provides functionality to import Telegram chat history from a JSON export file
into the database. It handles message processing, user creation, and chat management.

Expected JSON structure:
{
    "id": int,                  # Chat ID
    "name": str,                # Chat title
    "type": str,                # Chat type (e.g., "private", "group", "channel")
    "messages": [               # List of messages
        {
            "id": int,          # Message ID
            "type": str,        # Message type (e.g., "message")
            "date_unixtime": str,# Message timestamp
            "from_id": str,     # Sender ID (e.g., "user123")
            "text": str or List[Dict],  # Message text or list of text entities
            "text_entities": List[Dict], # Formatting entities
            "photo": Any,       # Optional: Photo data
            "media_type": str,  # Optional: Type of media
            "forwarded_from": str,  # Optional: Forwarded from username
            "reply_to_message_id": int   # Optional: ID of the message being replied to
        },
        ...
    ]
}
"""
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tortoise import Tortoise, transactions
from tqdm import tqdm
from app.models.db_models import User, Message, Media, Chat
from app.db import init_db
from app.utils.logging_config import logger

# Constants
EXPORT_FILE = str(Path(__file__).parent / 'data' / 'result.json')  # Path to exported Telegram JSON
BATCH_SIZE = 5000  # Number of messages to process in a single transaction


def extract_id(val: Any) -> Optional[int]:
    """
    Extract integer ID from Telegram 'user123', 'channel456', or plain int.
    Returns None if not valid.
    """
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith('user'):
            val = val[4:]
        elif val.startswith('channel'):
            val = val[7:]
        try:
            return int(val)
        except Exception:
            return None
    return None


def update_progress_bar(pbar: tqdm, n: int, step: int = 1000) -> None:
    """Update tqdm progress bar in steps of `step` messages."""
    full_steps = n // step
    remainder = n % step
    for _ in range(full_steps):
        pbar.update(step)
    if remainder:
        pbar.update(remainder)


async def build_user_cache(messages: List[Dict[str, Any]]) -> Dict[int, User]:
    """Build a user cache from all unique user IDs in messages, preloading from DB."""
    user_ids = {extract_id(msg.get('from_id')) for msg in messages if extract_id(msg.get('from_id')) is not None}
    user_cache = {}
    if user_ids:
        users = await User.filter(id__in=user_ids)
        for user in users:
            user_cache[user.id] = user
    return user_cache

def process_text_and_entities(text_entities: List[Dict[str, Any]]) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """
    Process text segments and their formatting entities from Telegram message.
    
    Args:
        text_entities: List of message segments with text and formatting information.
        
    Returns:
        Tuple of (full_text, entities) where entities is None if no rich formatting is found.
        Entities are formatted as Telegram API style entities.
    """
    text = ''
    entities = []
    has_rich_entities = False
    offset = 0
    
    for segment in text_entities:
        if not isinstance(segment, dict):
            logger.warning(f"Skipping invalid text segment: {segment}")
            continue
            
        segment_text = segment.get('text', '')
        text += segment_text
        
        # Only track non-plain entities
        if segment.get('type') != 'plain':
            has_rich_entities = True
            entities.append({
                "url": segment.get('href'),
                "type": segment.get('type'),
                "user": segment.get('user_id'),
                "length": len(segment_text),
                "offset": offset,
                "language": segment.get('language'),
                "custom_emoji_id": segment.get('custom_emoji_id'),
            })
        offset += len(segment_text)
    
    return text, (entities if has_rich_entities else None)

async def process_message(msg: Dict[str, Any], chat_obj: Chat, user_cache: Dict[int, User], db_counters: Dict[str, int]) -> Optional[Message]:
    """
    Process a single message from Telegram export and return a Message instance if valid.
    
    Args:
        msg: Raw message data from Telegram export.
        chat_obj: The Chat instance this message belongs to.
        
    Returns:
        Message instance if message is valid and should be imported, None otherwise.
    """
    if msg.get('type') != 'message':
        logger.debug(f"Skipping non-message type: {msg.get('type')}")
        return None
        
    msg_id = msg.get('id')
    if not msg_id:
        logger.warning("Message missing ID, skipping")
        return None
        
    logger.debug(f"Processing message ID: {msg_id}")

    # Process user
    from_user_obj = None
    forward_sender_name = None

    # Handle user/channel messages using extract_id and cache
    from_id_val = msg.get('from_id')
    user_id = extract_id(from_id_val)
    if user_id is not None:
        if user_id in user_cache:
            from_user_obj = user_cache[user_id]
        else:
            from_user_obj = await User.get_or_none(id=user_id)
            if not from_user_obj:
                from_user_obj = await User.create(id=user_id)
            user_cache[user_id] = from_user_obj
            db_counters['user'] += 1
    # Optionally handle forward_sender_name for channels
    if from_id_val and isinstance(from_id_val, str) and from_id_val.startswith('channel'):
        forward_sender_name = msg.get('from')

    if not from_user_obj:
        logger.warning(f"Message {msg_id} has no valid user, skipping")
        return None

    # Process text and entities
    text_entities = msg.get('text_entities', [])
    if not text_entities and 'text' in msg:
        text_entities = msg['text'] if isinstance(msg['text'], list) else [{'text': msg['text'], 'type': 'plain'}]
    
    text, entities = process_text_and_entities(text_entities)
    
    # Handle media
    media_prefix = None
    if 'photo' in msg:
        media_prefix = '(photo)'
    elif 'media_type' in msg:
        media_prefix = f'({msg["media_type"]})'
    
    if media_prefix:
        text = f"{media_prefix} {text}"
    
    # Handle forwarded messages (if not already handled as channel message)
    if not forward_sender_name and (forward_from := msg.get('forwarded_from')):
        forward_sender_name = forward_from
        text = f"(forwarded from {forward_sender_name}): {text}"

    try:
        message_date = datetime.fromtimestamp(int(msg['date_unixtime']))
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Invalid date for message {msg_id}: {e}")
        message_date = datetime.now()
    
    return Message(
        id=msg_id,
        chat=chat_obj,
        from_user=from_user_obj,
        text=text,
        date=message_date,
        entities=entities,
        reply_to_message_id=msg.get('reply_to_message_id'),
        forward_sender_name=forward_sender_name or msg.get('forward_sender_name')
    )

async def get_existing_message_ids(chat_obj: Chat, message_ids: List[int]) -> Set[int]:
    """
    Get set of message IDs that already exist in the database for a specific chat.
    
    Args:
        chat_obj: Chat instance to check messages in.
        message_ids: List of message IDs to check.
        
    Returns:
        Set of message IDs that already exist in the database.
    """
    if not message_ids:
        return set()
        
    try:
        existing = await Message.filter(chat=chat_obj).values_list('id', flat=True)
        return set(existing)
    except Exception as e:
        logger.error(f"Error fetching existing message IDs: {e}")
        return set()

async def process_messages_batch(messages_batch: List[Dict[str, Any]], chat_obj: Chat, user_cache, db_counters) -> List[Message]:
    """Process a batch of messages in parallel with user cache."""
    async def process_single(msg):
        try:
            result = await process_message(msg, chat_obj, user_cache, db_counters)
            return result
        except Exception as e:
            logger.error(f"Error processing message {msg.get('id')}: {e}")
            return None
    tasks = [process_single(msg) for msg in messages_batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if r is not None and not isinstance(r, Exception)]


async def import_telegram_json(export_file: str = EXPORT_FILE) -> None:
    """
    Import messages from a Telegram JSON export file into the database.
    
    Args:
        export_file: Path to the Telegram JSON export file.
    """
    # Initialize database connection
    await init_db()
    
    try:
        # Load and validate export file
        export_path = Path(export_file)
        if not export_path.exists():
            raise FileNotFoundError(f"Export file not found: {export_file}")
            
        logger.info(f"Loading Telegram export from {export_file}")
        with export_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate required fields
        chat_id = data.get('id')
        if chat_id and str(chat_id).isdigit() and int(chat_id) > 0:
            chat_id = int(f"-100{chat_id}")
        chat_title = data.get('name', 'Unknown')
        chat_type = data.get('type', 'private')
        messages = data.get('messages', [])

        imported_count = 0

        # --- Preload user and chat caches ---
        user_cache = await build_user_cache(messages)

        if not messages:
            logger.warning("No messages found in export file")
            return

        # Create or get chat
        try:
            async with transactions.in_transaction():
                chat_obj, created = await Chat.get_or_create(
                    id=chat_id,
                    defaults={'title': chat_title, 'type': chat_type}
                )
                if created:
                    logger.info(f"Created new chat: {chat_title} ({chat_type})")
                else:
                    logger.info(f"Found existing chat: {chat_title}")
        except Exception as e:
            logger.error(f"Error creating/updating chat: {e}")
            return

        # Filter and process messages
        messages = [msg for msg in messages if msg.get('type') == 'message']
        if not messages:
            logger.warning("No valid messages to import")
            return

        # Process messages in batches
        # Get all existing message IDs in one query
        all_message_ids = {msg['id'] for msg in messages if 'id' in msg}
        existing_ids = await get_existing_message_ids(chat_obj, all_message_ids)

        # Filter out existing messages
        new_messages = [msg for msg in messages if msg.get('id') not in existing_ids]
        logger.info(f"Found {len(existing_ids)} existing messages, {len(new_messages)} new messages to import")

        # Process only new messages in batches
        db_counters = {'user': 0, 'chat': 0, 'message': 0}
        with tqdm(total=len(new_messages), desc="Importing messages", unit="msg") as pbar:
            for i in range(0, len(new_messages), BATCH_SIZE):
                batch_messages = new_messages[i:i + BATCH_SIZE]
                
                # Process batch in parallel with progress updates
                processed_batch = await process_messages_batch(batch_messages, chat_obj, user_cache, db_counters)

                # Update progress every 1000 messages
                update_progress_bar(pbar, len(batch_messages), step=1000)

                # Save batch
                if processed_batch:
                    try:
                        async with transactions.in_transaction():
                            await Message.bulk_create(processed_batch)
                        imported_count += len(processed_batch)
                        db_counters['message'] += 1  # One bulk write per batch
                    except Exception as e:
                        logger.error(f"Error saving batch: {e}")
                        # Fall back to individual saves
                        for msg_obj in processed_batch:
                            try:
                                await msg_obj.save()
                                imported_count += 1
                                db_counters['message'] += 1  # One write per message
                            except Exception:
                                pass
        
        logger.info(f"Successfully imported {imported_count} messages to chat {chat_title} (id={chat_id})")
        logger.info(f"DB usage: User lookups: {db_counters['user']}, Chat lookups: {db_counters['chat']}, Message writes: {db_counters['message']}")
        
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in export file: {export_file}")
    except Exception as e:
        logger.error(f"Error during import: {e}", exc_info=True)
    finally:
        await Tortoise.close_connections()

if __name__ == "__main__":
    import asyncio
    asyncio.run(import_telegram_json())