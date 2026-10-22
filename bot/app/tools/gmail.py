"""
Обёртка над Gmail API (создание/чтение/обновление/удаление черновиков), аналог
MCP-инструментов create_draft/list_drafts/get_draft/update_draft/delete_draft,
которыми пользовался тот же skill внутри Claude Code.

Аутентификация — через refresh token, который пользователь получает ОДИН РАЗ
локально (см. bot/gmail_oauth_setup.py) и сам вводит в переменные окружения
хостинга. Бот никогда не видит пароль/логин Google — только refresh token с
ограниченным scope (gmail.compose), который можно отозвать в любой момент
в настройках Google-аккаунта.
"""
from __future__ import annotations

import base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import (
    GMAIL_CONFIGURED,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REFRESH_TOKEN,
)

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def _not_configured() -> dict:
    return {
        "error": (
            "Gmail не настроен — в переменных окружения бота нет "
            "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN. "
            "Пользователь должен один раз выполнить bot/gmail_oauth_setup.py "
            "на своём компьютере и задать эти переменные на хостинге."
        )
    }


def _service():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _build_mime(to, subject, body_text, html_body=None, cc=None, bcc=None, attachments=None) -> bytes:
    if html_body:
        msg = MIMEMultipart("mixed" if attachments else "alternative")
        alt = MIMEMultipart("alternative") if attachments else msg
        alt.attach(MIMEText(body_text or "", "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        if attachments:
            msg.attach(alt)
    else:
        msg = MIMEMultipart("mixed") if attachments else MIMEText(body_text or "", "plain", "utf-8")

    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject

    for att in attachments or []:
        part = MIMEBase(*(att.get("mime_type", "application/octet-stream").split("/", 1)))
        part.set_payload(base64.b64decode(att["content_base64"]))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att.get("filename", "attachment"))
        msg.attach(part)

    return msg.as_bytes()


def create_draft(
    to: list[str],
    subject: str,
    body_text: str,
    html_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """attachments: [{"filename": str, "mime_type": str, "content_base64": str}, ...]"""
    if not GMAIL_CONFIGURED:
        return _not_configured()
    raw = _build_mime(to, subject, body_text, html_body, cc, bcc, attachments)
    encoded = base64.urlsafe_b64encode(raw).decode()
    service = _service()
    draft = service.users().drafts().create(userId="me", body={"message": {"raw": encoded}}).execute()
    return {"id": draft["id"], "message_id": draft.get("message", {}).get("id")}


def list_drafts(query: str | None = None, max_results: int = 20) -> dict:
    if not GMAIL_CONFIGURED:
        return _not_configured()
    service = _service()
    resp = service.users().drafts().list(userId="me", q=query, maxResults=max_results).execute()
    items = []
    for d in resp.get("drafts", []):
        full = service.users().drafts().get(userId="me", id=d["id"], format="metadata").execute()
        headers = {h["name"]: h["value"] for h in full["message"]["payload"].get("headers", [])}
        items.append({
            "id": d["id"],
            "subject": headers.get("Subject", ""),
            "to": headers.get("To", ""),
            "snippet": full["message"].get("snippet", ""),
        })
    return {"drafts": items}


def get_draft(draft_id: str) -> dict:
    if not GMAIL_CONFIGURED:
        return _not_configured()
    service = _service()
    full = service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in full["message"]["payload"].get("headers", [])}

    def _walk(part):
        texts = {}
        if part.get("parts"):
            for p in part["parts"]:
                texts.update(_walk(p))
        else:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if data and mime in ("text/plain", "text/html"):
                texts[mime] = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return texts

    bodies = _walk(full["message"]["payload"])
    return {
        "id": draft_id,
        "subject": headers.get("Subject", ""),
        "to": headers.get("To", ""),
        "body_text": bodies.get("text/plain", ""),
        "body_html": bodies.get("text/html", ""),
    }


def update_draft(
    draft_id: str,
    to: list[str],
    subject: str,
    body_text: str,
    html_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Полная замена содержимого черновика (как update_draft в Gmail MCP) - вложения не сохраняются, если не передать их снова."""
    if not GMAIL_CONFIGURED:
        return _not_configured()
    raw = _build_mime(to, subject, body_text, html_body, cc, bcc, attachments)
    encoded = base64.urlsafe_b64encode(raw).decode()
    service = _service()
    draft = service.users().drafts().update(
        userId="me", id=draft_id, body={"message": {"raw": encoded}}
    ).execute()
    return {"id": draft["id"]}


def delete_draft(draft_id: str) -> dict:
    if not GMAIL_CONFIGURED:
        return _not_configured()
    service = _service()
    service.users().drafts().delete(userId="me", id=draft_id).execute()
    return {"deleted": draft_id}
