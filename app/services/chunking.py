from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from app.models.db_models import Message
from app.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.models.db_models import ChunkEmbedding, User, Media
from tortoise.functions import Count
from app.utils.logging_config import logger, log_exception, log_function_call

async def get_unchunked_messages(chat_id: int) -> List[str]:
    """Return formatted messages in a chat not yet associated with any chunk, ordered by date."""
    messages = await Message.filter(chat_id=chat_id)\
        .annotate(num_chunks=Count("chunks"))\
        .filter(num_chunks=0)\
        .order_by("date")\
        .prefetch_related(\
            'from_user',\
            'chat',\
            'forward_from_user',\
            'forward_from_chat',\
            'reply_to_message',\
            'reply_to_message__from_user',\
            'media'\
        )\
        .all()
    return [format_message_for_display(m) for m in messages]

def get_chunk_windows(total: int, size: int, overlap: int):
    """Yield (start, end) indices for chunking with overlap."""
    step = max(1, size - overlap)
    for idx in range(0, total - size + 1, step):
        yield idx, idx + size

from app.utils.message_formatting import format_message_for_display

async def auto_chunk_chat(chat_id: int):
    """Create new chunks for a chat from unchunked messages, using configured size and overlap."""
    # Get all messages that haven't been chunked yet with all necessary relations
    messages = await Message.filter(chat_id=chat_id)\
        .annotate(num_chunks=Count("chunks"))\
        .filter(num_chunks=0)\
        .order_by("date")\
        .prefetch_related(\
            'from_user',\
            'chat',\
            'forward_from_user',\
            'forward_from_chat',\
            'reply_to_message',\
            'reply_to_message__from_user',\
            'media'\
        )\
        .all()
    
    n = len(messages)
    if n == 0:
        return
        
    # Format messages for chunk text
    formatted_messages = [format_message_for_display(m) for m in messages]
    windows = list(get_chunk_windows(n, CHUNK_SIZE, CHUNK_OVERLAP))
    
    for start, end in windows:
        chunk_msgs = messages[start:end]
        chunk_text = "\n".join(formatted_messages[start:end])
        
        # Create chunk with basic info
        chunk = await ChunkEmbedding.create(
            chat_id=chat_id,
            chunk_text=chunk_text,
            from_time=chunk_msgs[0].date.timestamp() if chunk_msgs else None,
            to_time=chunk_msgs[-1].date.timestamp() if chunk_msgs else None
        )
        
        # Add messages to chunk
        if chunk_msgs:
            await chunk.messages.add(*chunk_msgs)
            
            # Add users
            users = {m.from_user for m in chunk_msgs if m.from_user}
            if users:
                await chunk.users.add(*users)
                
            # Add media
            medias = [m.media for m in chunk_msgs if m.media]
            if medias:
                await chunk.medias.add(*medias)
        
        # Log the chunk creation
        msg_ids = [m.id for m in chunk_msgs]
        start_id = msg_ids[0] if msg_ids else 0
        end_id = msg_ids[-1] if msg_ids else 0
        logging.info(f"[CHUNK] New chunk created for chat {chat_id}: messages {start_id}-{end_id}, chunk_id={chunk.id}")

@log_function_call
async def refresh_latest_chunk_for_chat(chat_id: int):
    '''
    Refresh (recreate) the latest chunk for a chat if enough new messages have arrived to slide the chunk window.
    Efficient sliding window: only fetch/process minimal set of messages.
    '''
    from app.models.db_models import ChunkEmbedding, Message
    from app.utils.message_formatting import format_message_for_display

    # Get the latest chunk for this chat
    latest_chunk = await ChunkEmbedding.filter(chat_id=chat_id).order_by('-to_time').prefetch_related('messages').first()
    if latest_chunk:
        # Get the last message in the latest chunk
        last_msg = await latest_chunk.messages.order_by('-date').first()
        if not last_msg:
            return
        # Count new messages after the last message in the chunk
        new_messages_count = await Message.filter(chat_id=chat_id, date__gt=last_msg.date).count()
        if new_messages_count >= (CHUNK_SIZE - CHUNK_OVERLAP):
            # Fetch only the last CHUNK_SIZE messages for the new chunk
            chunk_msgs = await Message.filter(chat_id=chat_id).order_by('-date').limit(CHUNK_SIZE).prefetch_related(
                'from_user', 'chat', 'forward_from_user', 'forward_from_chat', 'reply_to_message', 'reply_to_message__from_user', 'media'
            ).all()
            chunk_msgs = list(reversed(chunk_msgs))
            # Format and create new chunk
            chunk_text = '\n'.join([format_message_for_display(m) for m in chunk_msgs])
            from_time = chunk_msgs[0].date.timestamp() if chunk_msgs else None
            to_time = chunk_msgs[-1].date.timestamp() if chunk_msgs else None
            chunk = await ChunkEmbedding.create(
                chat_id=chat_id,
                chunk_text=chunk_text,
                from_time=from_time,
                to_time=to_time
            )
            await chunk.messages.add(*chunk_msgs)
            users = [m.from_user for m in chunk_msgs if m.from_user]
            if users:
                await chunk.users.add(*users)
            medias = [m.media for m in chunk_msgs if m.media]
            if medias:
                await chunk.medias.add(*medias)
            msg_ids = [m.id for m in chunk_msgs]
            start_id = msg_ids[0] if msg_ids else 0
            end_id = msg_ids[-1] if msg_ids else 0
            logger.info(f"[CHUNK] New chunk created for chat {chat_id}: messages {start_id}-{end_id}, chunk_id={chunk.id}")

    else:
        # No existing chunk, create the first one if enough messages
        chunk_msgs = await Message.filter(chat_id=chat_id).order_by('-date').limit(CHUNK_SIZE).prefetch_related(
            'from_user', 'chat', 'forward_from_user', 'forward_from_chat', 'reply_to_message', 'reply_to_message__from_user', 'media'
        ).all()
        chunk_msgs = list(reversed(chunk_msgs))
        if len(chunk_msgs) == CHUNK_SIZE:
            await create_or_update_chunk(chunk_msgs)

# For testing: create chunks for all chats
def get_all_chat_ids():
    return Message.all().distinct().values_list('chat_id', flat=True)

async def auto_chunk_all_chats():
    chat_ids = await get_all_chat_ids()
    for chat_id in chat_ids:
        await auto_chunk_chat(chat_id)
