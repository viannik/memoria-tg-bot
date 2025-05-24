from tortoise import fields, models
from tortoise_vector.field import VectorField

# chats: id type title username
class Chat(models.Model):
    id = fields.BigIntField(pk=True)
    type = fields.CharField(max_length=32, null=True)
    title = fields.CharField(max_length=255, null=True)
    username = fields.CharField(max_length=32, null=True)
    class Meta:
        table = "chats"

# users: id first_name last_name username language_code
class User(models.Model):
    id = fields.BigIntField(pk=True)
    first_name = fields.CharField(max_length=64, null=True)
    last_name = fields.CharField(max_length=64, null=True)
    username = fields.CharField(max_length=32, null=True)
    language_code = fields.CharField(max_length=8, null=True)
    class Meta:
        table = "users"

# messages: id from_user chat text entities media_type media reply_to forward_from forward_from_chat forward_from_message_id
class Message(models.Model):
    id = fields.BigIntField(pk=True)
    from_user = fields.ForeignKeyField('models.User', related_name='messages')
    chat = fields.ForeignKeyField('models.Chat', related_name='messages')
    date = fields.DatetimeField(null=False)
    text = fields.TextField(null=True)
    entities = fields.JSONField(null=True)
    media = fields.ForeignKeyField('models.Media', related_name='messages', null=True)

    # Forwarded message fields
    forward_from_user = fields.ForeignKeyField('models.User', related_name='forwarded_from_user_messages', null=True)
    forward_from_chat = fields.ForeignKeyField('models.Chat', related_name='forwarded_from_chat_messages', null=True)
    forward_from_message = fields.ForeignKeyField('models.Message', related_name='forwarded_from_messages', null=True)
    forward_sender_name = fields.CharField(max_length=255, null=True)

    # Reply field
    reply_to_message = fields.ForeignKeyField('models.Message', related_name='replies', null=True)

    class Meta:
        table = "messages"
        indexes = [
            ('chat', 'date'),
        ]


class Media(models.Model):
    file_unique_id = fields.CharField(max_length=255, pk=True, unique=True)
    media_type = fields.CharField(max_length=32, null=True)
    file_id = fields.CharField(max_length=255, null=True)
    caption = fields.TextField(null=True)
    mime_type = fields.CharField(max_length=64, null=True)
    file_size = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, null=True)
    width = fields.IntField(null=True)
    height = fields.IntField(null=True)
    duration = fields.IntField(null=True)
    class Meta:
        table = "media"

# chunks_embeddings: id messages(один до багатьох) chunk_text embedding from_time to_time users(один до багатьох) medias(один до багатьох)
class ChunkEmbedding(models.Model):
    id = fields.IntField(pk=True)
    chunk_text = fields.TextField(null=True)
    embedding = VectorField(vector_size=1536, null=True)
    from_time = fields.FloatField(null=True)
    to_time = fields.FloatField(null=True)
    messages = fields.ManyToManyField('models.Message', related_name='chunks_embeddings')
    users = fields.ManyToManyField('models.User', related_name='chunks_embeddings')
    medias = fields.ManyToManyField('models.Media', related_name='chunks_embeddings')

    class Meta:
        table = "chunks_embeddings"

    class Meta:
        table = "chunk"
        indexes = ["embedding"]  # This enables pgvector indexing

    def __str__(self):
        return f"Chunk {self.id}: {self.text[:50]}..."