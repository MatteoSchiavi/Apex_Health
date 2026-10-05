"""Account export includes owned AI records without crossing account boundaries."""

import json
import os
from datetime import date

from sqlalchemy import delete

from app.models.ai import AiReport
from app.models.chat import AiChatMessage, AiChatSession
from app.models.user import AuthCredential, User
from tests.conftest import login


async def test_account_export_scopes_profile_chat_and_reports(client, db_session):
    signed_in = await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])
    assert signed_in.status_code == 200
    owner_id = signed_in.json()["user_id"]

    other = User(name="foreign-export-user")
    db_session.add(other)
    await db_session.flush()
    db_session.add(AuthCredential(
        user_id=other.id,
        email="validemail@example.com",
        password_hash="foreign-password-hash-must-not-export",
        role="friend",
    ))
    owner_chat = AiChatSession(user_id=owner_id, title="owned-chat-title")
    foreign_chat = AiChatSession(user_id=other.id, title="foreign-chat-title")
    db_session.add_all([owner_chat, foreign_chat])
    await db_session.flush()
    db_session.add_all([
        AiChatMessage(session_id=owner_chat.id, role="user", content="owned-chat-content"),
        AiChatMessage(session_id=foreign_chat.id, role="user", content="foreign-chat-content"),
        AiReport(
            user_id=owner_id,
            report_type="daily",
            period_start=date(2026, 10, 4),
            period_end=date(2026, 10, 4),
            content_md="owned-report-content",
        ),
        AiReport(
            user_id=other.id,
            report_type="daily",
            period_start=date(2026, 10, 4),
            period_end=date(2026, 10, 4),
            content_md="foreign-report-content",
        ),
    ])
    await db_session.commit()

    try:
        response = await client.get("/lab/export/account.json")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        exported = response.json()
        assert exported["profile"]["id"] == owner_id
        assert exported["profile"]["email"] == os.environ["OWNER_EMAIL"]
        assert owner_chat.id in {row["id"] for row in exported["ai_chat_sessions"]}
        assert foreign_chat.id not in {row["id"] for row in exported["ai_chat_sessions"]}
        assert owner_chat.id in {row["session_id"] for row in exported["ai_chat_messages"]}
        assert foreign_chat.id not in {row["session_id"] for row in exported["ai_chat_messages"]}
        assert "owned-chat-content" in {row["content"] for row in exported["ai_chat_messages"]}
        assert "owned-report-content" in {row["content_md"] for row in exported["ai_reports"]}
        body = json.dumps(exported)
        for forbidden in (
            "foreign-chat-title",
            "foreign-chat-content",
            "foreign-report-content",
            "validemail@example.com",
            "foreign-password-hash-must-not-export",
            "password_hash",
            "token_hash",
            "credentials_encrypted",
        ):
            assert forbidden not in body
        assert "sessions" not in exported
        assert "auth_credentials" not in exported
    finally:
        await db_session.execute(delete(AiChatMessage).where(
            AiChatMessage.session_id.in_([owner_chat.id, foreign_chat.id])
        ))
        await db_session.execute(delete(AiChatSession).where(
            AiChatSession.id.in_([owner_chat.id, foreign_chat.id])
        ))
        await db_session.execute(delete(AiReport).where(
            AiReport.user_id.in_([owner_id, other.id]),
            AiReport.content_md.in_(["owned-report-content", "foreign-report-content"]),
        ))
        await db_session.execute(delete(AuthCredential).where(AuthCredential.user_id == other.id))
        await db_session.execute(delete(User).where(User.id == other.id))
        await db_session.commit()
