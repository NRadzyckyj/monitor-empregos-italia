#!/usr/bin/env python3
"""Coleta vagas públicas de hospitalidade na Itália, guarda o histórico e alerta um bot próprio."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "jobs.json"
DATA = ROOT / "data" / "jobs.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ItalyJobsMonitor/1.0)", "Accept": "text/plain"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def today_in_sao_paulo() -> date:
    try:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone(timedelta(hours=-3))).date()


def fetch(url: str) -> str:
    readable = "https://r.jina.ai/http://" + url.removeprefix("https://").removeprefix("http://")
    with urlopen(Request(readable, headers=HEADERS), timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def job(source: dict, title: str, url: str, details: str) -> dict:
    url = url.split("#", 1)[0].rstrip("/")
    return {"id": hashlib.sha256(url.encode()).hexdigest()[:20], "source": source["name"], "confidence": source["trust"], "title": clean(title), "url": url, "details": clean(details)}


def parse_restworld(page: str, source: dict) -> list[dict]:
    pattern = r"^\*\s+\[(?P<label>.*)\]\((?P<url>https?://www\.restworld\.it/posizione/[^)]+)\)$"
    return [job(source, clean(match.group("label")).split("€", 1)[0], match.group("url"), match.group("label")) for match in re.finditer(pattern, page, re.M)]


def parse_rysto(page: str, source: dict) -> list[dict]:
    pattern = r"Star\[(?P<title>[^\]]+)\]\((?P<url>https?://www\.rysto\.com/it/[^)]+)\)\s*(?P<company>[^\n|]+)\|\s*(?P<location>[^\n]+)\s*(?P<contract>[^\n]+)\s*Pubblicata il\s*(?P<published>\d{2}/\d{2}/\d{4})"
    return [job(source, m.group("title"), m.group("url"), " | ".join(m.group(k) for k in ("company", "location", "contract", "published"))) for m in re.finditer(pattern, page, re.S)]


def parse_restartgo(page: str, source: dict) -> list[dict]:
    pattern = r"###\s+\[(?P<title>[^\]]+)\]\((?P<url>https?://www\.restartgo\.com/it/offerta-lavoro/[^)]+)\)\s*(?P<company>.*?)\s*Mansione:\s*\*\*(?P<role>[^*]+)\*\*\s*Posizione:\s*\*\*(?P<location>[^*]+)\*\*\s*Pubblicato il:\s*\*\*(?P<published>[^*]+)\*\*\s*(?P<description>.*?)(?:\n\s*SOS|\n\s*\[Vedi annuncio\])"
    return [job(source, m.group("title"), m.group("url"), " | ".join(clean(m.group(k)) for k in ("company", "role", "location", "published", "description"))) for m in re.finditer(pattern, page, re.S)]


PARSERS = {"restworld": parse_restworld, "rysto": parse_rysto, "restartgo": parse_restartgo}


def published_on(details: str) -> date | None:
    for raw in re.findall(r"\b(\d{2}/\d{2}/\d{2,4})\b", details):
        for fmt in ("%d/%m/%y", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None


def evaluate(item: dict, config: dict, today: date) -> tuple[int, list[str]] | None:
    text = f"{item['title']} {item['details']}".lower()
    if any(term in text for term in config["exclude_terms"] + config["non_italy_terms"]):
        return None
    if not any(term in text for term in config["include_terms"]):
        return None
    published = published_on(item["details"])
    if published and published < today - timedelta(days=int(config["max_listing_age_days"])):
        return None
    if date.fromisoformat(config["available_from"]) > today and re.search(r"inizio\s+immediato|disponibilit[àa]\s+immediata|stagione\s+.*2026", text):
        return None
    score, reasons = 0, []
    if re.search(r"part[ -]?time|tempo determinato|stagionale|extra|verticale", text):
        score += 3; reasons.append("temporário/part-time")
    if re.search(r"vitto|alloggio", text):
        score += 3; reasons.append("menciona moradia ou refeições")
    if re.search(r"apprendistat|senza esperienza|prima esperienza", text):
        score += 2; reasons.append("entrada/aprendizado")
    if not re.search(r"esperienz[ae].{0,18}(anni|obbligatoria|richiesta)", text):
        score += 1; reasons.append("sem experiência longa explícita")
    if item["confidence"] == "alta":
        score += 2; reasons.append("fonte verificada")
    return score, reasons


def alert_text(items: list[dict], test: bool) -> str:
    header = "🧪 TESTE — vagas na Itália" if test else "🇮🇹 Novas vagas na Itália"
    blocks = []
    for item in items:
        blocks.append(f"• {item['title']}\n{item['details'][:260]}\nPor que entrou: {', '.join(item['reasons'])} (prioridade {item['priority']}/10).\n{item['url']}")
    return header + "\n\n" + "\n\n".join(blocks) + "\n\n⚠️ Confirme italiano exigido, data de início, contrato, turnos e moradia antes de se candidatar."


def notify(text: str, dry_run: bool) -> bool:
    if dry_run:
        try: print("\n--- PRÉVIA ---\n" + text)
        except UnicodeEncodeError: print("\n--- PREVIA ---\n" + text.encode("ascii", "replace").decode())
        return True
    token = (os.getenv("TELEGRAM_JOBS_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_JOBS_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("Bot de empregos ainda sem secrets; dados foram salvos, mas nada foi enviado.", file=sys.stderr)
        return False
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=30) as response:
            return bool(json.loads(response.read()).get("ok"))
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"Falha no Telegram: {error}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-alert", action="store_true")
    args = parser.parse_args()
    config, saved = json.loads(CONFIG.read_text(encoding="utf-8")), json.loads(DATA.read_text(encoding="utf-8"))
    today, now = today_in_sao_paulo(), datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = {item["id"]: item for item in saved.get("jobs", [])}
    collected, coverage = {}, {}
    for source in config["sources"]:
        try:
            found = PARSERS[source["parser"]](fetch(source["url"]), source)
            coverage[source["name"]] = {"status": "público concluído", "checked_at": now, "found": len(found)}
            collected.update({item["id"]: item for item in found})
            print(f"OK {source['name']}: {len(found)} anúncio(s).")
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            coverage[source["name"]] = {"status": "falhou", "checked_at": now, "detail": str(error)}
            print(f"AVISO {source['name']}: {error}", file=sys.stderr)
    candidates = []
    for item in collected.values():
        result = evaluate(item, config, today)
        if not result: continue
        priority, reasons = result
        old = existing.get(item["id"], {})
        item.update({"priority": priority, "reasons": reasons, "status": "início/idioma a confirmar", "first_seen": old.get("first_seen", now), "last_seen": now, "active": True, "alerted_at": old.get("alerted_at")})
        existing[item["id"]] = item
        if args.test_alert or not old.get("alerted_at"):
            candidates.append(item)
    for item_id, item in existing.items():
        if item_id not in collected: item["active"] = False
    candidates.sort(key=lambda item: (-item["priority"], item["title"]))
    selected = candidates[:int(config["max_alerts_per_run"])]
    sent = notify(alert_text(selected, args.test_alert), args.dry_run) if selected else False
    if sent and not args.test_alert:
        for item in selected: existing[item["id"]]["alerted_at"] = now
    if not args.test_alert:
        saved = {"updated_at": now, "coverage": coverage, "jobs": sorted(existing.values(), key=lambda item: (not item.get("active", False), -item.get("priority", 0), item["title"]))[:500]}
        DATA.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Concluído: {len(collected)} coletadas, {len(selected)} alertas, enviado={sent}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
