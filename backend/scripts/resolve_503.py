#!/usr/bin/env python3
"""ArchSchool CLI: Force resolve any Telegram chats whose last message received a 503 error."""

import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.services import telegram_bot


async def main() -> None:
    print("==================================================")
    print("  ArchSchool Telegram 503 Backlog Resolver")
    print("==================================================")
    with SessionLocal() as db:
        count = await telegram_bot.resolve_pending_503_chats(db)
        print(f"Done! Resolved and delivered answers to {count} conversations.")


if __name__ == "__main__":
    asyncio.run(main())
