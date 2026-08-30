#!/usr/bin/env python3
"""Mostra os chats que iniciaram conversa com o bot de empregos."""
from __future__ import annotations

import json
import os
from urllib.request import urlopen

token = (os.getenv("TELEGRAM_JOBS_BOT_TOKEN") or "").strip()
if not token:
    raise SystemExit("Configure TELEGRAM_JOBS_BOT_TOKEN antes de executar este workflow.")

with urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30) as response:
    updates = json.loads(response.read())

if not updates.get("ok"):
    raise SystemExit("O Telegram recusou o token do bot de empregos.")

chats = {}
for update in updates.get("result", []):
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    if chat.get("id"):
        chats[str(chat["id"])] = chat.get("title") or chat.get("username") or chat.get("first_name") or "chat sem nome"

if not chats:
    raise SystemExit("Nenhum chat encontrado. Abra o novo bot no Telegram, envie /start e execute novamente.")

for chat_id, label in chats.items():
    print(f"TELEGRAM_JOBS_CHAT_ID={chat_id}  ({label})")
