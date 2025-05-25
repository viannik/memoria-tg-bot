from datetime import datetime
from typing import Optional

def format_username(user) -> str:
    """Return username if available, else full_name (no links, plain text)."""
    return user.username if getattr(user, 'username', None) else user.full_name if getattr(user, 'full_name', None) else user.id

def format_entities(text: str, entities: Optional[list]) -> str:
    """
    Applies Markdown formatting to text according to Telegram entities.
    Supported: bold, italic, underline, strikethrough, blockquote, pre, spoiler, text_link.
    """
    if not entities:
        return text
    # Sort entities by offset (descending) so that inserting tags doesn't shift text for later entities
    entities = sorted(entities, key=lambda e: e['offset'], reverse=True)
    for ent in entities:
        offset = ent['offset']
        length = ent['length']
        etype = ent['type']
        segment = text[offset:offset+length]
        if etype == 'bold':
            segment = f"**{segment}**"
        elif etype == 'italic':
            segment = f"*{segment}*"
        elif etype == 'underline':
            segment = f"__{segment}__"
        elif etype == 'strikethrough':
            segment = f"~~{segment}~~"
        elif etype == 'blockquote':
            segment = f"> {segment}"
        elif etype == 'pre':
            segment = f"`{segment}`"
        elif etype == 'spoiler':
            segment = f"||{segment}||"
        elif etype == 'text_link' and ent.get('url'):
            segment = f"[{segment}]({ent['url']})"
        # Replace in text
        text = text[:offset] + segment + text[offset+length:]
    return text

from app.utils.logging_config import logger, log_exception, log_function_call

@log_function_call
def format_message_for_display(message) -> str:
    """
    Formats a DB Message object into a readable string for display/chunking.
    Supports: date, user, forward (from user/chat), reply, entities, media.
    Optimized for clarity and efficiency.
    """
    dt = message.date.strftime("%d.%m.%Y %H:%M")
    from_user = getattr(message, 'from_user', None)
    user_str = format_username(from_user) if from_user else "Unknown"

    # Forwarded
    forward_user = getattr(message, 'forward_from_user', None)
    forward_chat = getattr(message, 'forward_from_chat', None)
    forward_sender_name = getattr(message, 'forward_sender_name', None)
    forward_str = ""
    if forward_user and (not (hasattr(forward_user, 'id') and hasattr(from_user, 'id') and forward_user.id == from_user.id)):
        forward_str = f" (forwarded from {format_username(forward_user)})"
    elif forward_chat:
        forward_str = f" (forwarded from chat: {getattr(forward_chat, 'title', forward_chat.id)})"
    elif forward_sender_name:
        forward_str = f" (forwarded from {forward_sender_name})"

    # Reply
    reply_msg = getattr(message, 'reply_to_message', None)
    reply_str = ""
    if reply_msg:
        reply_user = getattr(reply_msg, 'from_user', None)
        reply_str = f" (reply to {format_username(reply_user)})" if reply_user else " (reply)"

    # Entities
    text = format_entities(getattr(message, 'text', '') or '', getattr(message, 'entities', None))

    # Media
    media = getattr(message, 'media', None)
    media_str = f" ({media.media_type})" if media and getattr(media, 'media_type', None) else ""

    return f"{dt} {user_str}{forward_str}{reply_str}:{media_str} {text}"

# (Optional) aiogram support can be added here if needed in the future.
