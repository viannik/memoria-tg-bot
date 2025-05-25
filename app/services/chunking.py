import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from app.models.db_models import Message

from app.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.models.db_models import ChunkEmbedding, User, Media
from tortoise.functions import Count

async def get_unchunked_messages(chat_id: int) -> List[str]:
    """Return formatted messages in a chat not yet associated with any chunk, ordered by date."""
    messages = await Message.filter(chat_id=chat_id)\
        .annotate(num_chunks=Count("chunks_embeddings"))\
        .filter(num_chunks=0)\
        .order_by("date")\
        .prefetch_related('from_user', 'chat', 'forward_from_user', 'forward_from_chat', 'reply_to_message', 'media')\
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
    formatted_messages = await get_unchunked_messages(chat_id)
    n = len(formatted_messages)
    if n == 0:
        return
    windows = list(get_chunk_windows(n, CHUNK_SIZE, CHUNK_OVERLAP))
    # Re-fetch message objects for association
    messages = await Message.filter(chat_id=chat_id)\
        .annotate(num_chunks=Count("chunks_embeddings"))\
        .filter(num_chunks=0)\
        .order_by("date")\
        .all()
    for idx, (start, end) in enumerate(windows):
        chunk_text = "\n".join(formatted_messages[start:end])
        chunk = await ChunkEmbedding.create(
            chat_id=chat_id,
            text=chunk_text
        )
        await chunk.messages.add(*[m.id for m in messages[start:end]])
    if n < CHUNK_SIZE:
        return
    msg_ids = [m.id for m in messages]
    for start, end in get_chunk_windows(n, CHUNK_SIZE, CHUNK_OVERLAP):
        chunk_msgs = messages[start:end]
        chunk_text = '\n'.join(m.text or '' for m in chunk_msgs if m.text)
        chunk = await ChunkEmbedding.create(
            chat_id=chat_id,
            chunk_text=chunk_text,
            from_time=chunk_msgs[0].date.timestamp(),
            to_time=chunk_msgs[-1].date.timestamp()
        )
        await chunk.messages.add(*chunk_msgs)
        user_ids = {m.from_user_id for m in chunk_msgs}
        if user_ids:
            users = await User.filter(id__in=user_ids)
            await chunk.users.add(*users)
        media_ids = [m.media_id for m in chunk_msgs if m.media_id]
        if media_ids:
            medias = await Media.filter(file_unique_id__in=media_ids)
            await chunk.medias.add(*medias)
        logging.info(f"[CHUNK] New chunk created for chat {chat_id}: messages {msg_ids[start]}-{msg_ids[end-1]}, chunk_id={chunk.id}")

async def refresh_latest_chunk_for_chat(chat_id: int):
    '''
    Refresh (recreate) the latest chunk for a chat if enough new messages have arrived to slide the chunk window.
    '''
    from app.models.db_models import ChunkEmbedding, Message
    # Get all messages for this chat, ordered by date
    messages = await Message.filter(chat_id=chat_id).order_by('date').all()
    if len(messages) < CHUNK_SIZE:
        return  # Not enough messages to form a chunk
    # Find the latest chunk (by to_time)
    latest_chunk = await ChunkEmbedding.filter(messages__chat_id=chat_id).order_by('-to_time').first()
    if latest_chunk:
        # Find the index of the last message in the latest chunk
        last_msg_ids = await latest_chunk.messages.all().order_by('date').values_list('id', flat=True)
        if not last_msg_ids:
            return
        last_msg_id = last_msg_ids[-1]
        try:
            last_msg_idx = next(i for i, m in enumerate(messages) if m.id == last_msg_id)
        except StopIteration:
            return
        # If enough new messages have arrived to move the window
        if len(messages) - last_msg_idx >= (CHUNK_SIZE - CHUNK_OVERLAP):
            # Delete the latest chunk and recreate with the new window
            await latest_chunk.delete()
            # Use the last CHUNK_SIZE messages
            chunk_msgs = messages[-CHUNK_SIZE:]
            chunk_text = '\n'.join([format_message_for_display(m) for m in chunk_msgs])
            from_time = chunk_msgs[0].date.timestamp() if chunk_msgs else None
            to_time = chunk_msgs[-1].date.timestamp() if chunk_msgs else None
            chunk = await ChunkEmbedding.create(
                chunk_text=chunk_text,
                from_time=from_time,
                to_time=to_time
            )
            await chunk.messages.add(*chunk_msgs)
            user_ids = set(m.from_user_id for m in chunk_msgs)
            await chunk.users.add(*user_ids)
            media_ids = [m.media_id for m in chunk_msgs if m.media_id]
            if media_ids:
                await chunk.medias.add(*media_ids)
            logging.info(f"[CHUNK] New chunk created for chat {chat_id}: messages {chunk_msgs[0].id}-{chunk_msgs[-1].id}, chunk_id={chunk.id}")
    else:
        # No existing chunk, create the first one if enough messages
        chunk_msgs = messages[-CHUNK_SIZE:]
        if len(chunk_msgs) == CHUNK_SIZE:
            chunk_text = '\n'.join([format_message_for_display(m) for m in chunk_msgs])
            from_time = chunk_msgs[0].date.timestamp() if chunk_msgs else None
            to_time = chunk_msgs[-1].date.timestamp() if chunk_msgs else None
            chunk = await ChunkEmbedding.create(
                chunk_text=chunk_text,
                from_time=from_time,
                to_time=to_time
            )
            await chunk.messages.add(*chunk_msgs)
            user_ids = set(m.from_user_id for m in chunk_msgs)
            await chunk.users.add(*user_ids)
            media_ids = [m.media_id for m in chunk_msgs if m.media_id]
            if media_ids:
                await chunk.medias.add(*media_ids)
            logging.info(f"[CHUNK] New chunk created for chat {chat_id}: messages {chunk_msgs[0].id}-{chunk_msgs[-1].id}, chunk_id={chunk.id}")

# For testing: create chunks for all chats
def get_all_chat_ids():
    return Message.all().distinct().values_list('chat_id', flat=True)

async def auto_chunk_all_chats():
    chat_ids = await get_all_chat_ids()
    for chat_id in chat_ids:
        await auto_chunk_chat(chat_id)
