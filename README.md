# 🧠 Telegram Chatbot with Embeddings and Context Memory

This bot is implemented on the basis of `aiogram', `Tortoise ORM', `LangChain' and `pgvector'. It stores all messages, media, and metadata from Telegram chats, generates chunks (contextual blocks), creates embeddings for semantic search, and responds to messages based on the previous context.

---

## 📦 Technologies

- [aiogram](https://docs.aiogram.dev/) — асинхронний Telegram бот-фреймворк
- [Tortoise ORM](https://tortoise-orm.readthedocs.io/) — ORM для async Python
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) — зберігання embedding-ів
- [LangChain](https://python.langchain.com/) — LLM інтеграція та семантичний пошук
- OpenAI / інша модель для генерації embedding-ів

---

## 📁 Project structure

memoria-tg-bot/
│
├── app/                            # Main business logic
│   ├── __init__.py
│   ├── config.py                   # Loading .env or other configurations
│   ├── main.py                     # Bot launch
│   ├── handlers/                  # Message and command handlers
│   │   ├── __init__.py
│   │   ├── base.py                # Handlers for reminders / commands
│   │   └── media.py               # Media processing
│   ├── services/                  # Services: logic that doesn't belong to handlers
│   │   ├── __init__.py
│   │   ├── chunking.py            # Grouping messages into chunks
│   │   ├── embeddings.py          # Embedding generation
│   │   ├── langchain_integration.py  # LangChain integration
│   │   └── reply_generator.py     # Response generation
│   ├── models/                    # ORM models Tortoise
│   │   ├── __init__.py
│   │   └── db_models.py
│   └── db/
│       ├── __init__.py
│       └── schema.sql             # SQL-structure of tables (as in canvas)
│
├── migrations/                    # Alembic or Tortoise migration generator
│   └── ...
│
├── scripts/                       # Scripts for generating embeddings, checks etc.
│   ├── generate_embeddings.py
│   └── populate_dummy_data.py
│
├── tests/                         # Unit tests
│   ├── __init__.py
│   ├── test_embeddings.py
│   └── test_chunking.py
│
├── .env                           # Environment configuration
├── .gitignore
├── Dockerfile                     # Containerization
├── docker-compose.yml             # For DB + bot
├── README.md                      # Documentation
└── requirements.txt               # Dependencies


---

## 🗃️ Database schema

![alt text](assets/image.png)
