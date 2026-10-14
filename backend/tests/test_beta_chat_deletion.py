"""Delete real persisted synthetic chats, with no LLM or production data.

Run only through the repository's guarded disposable DB/Redis test runner.
"""
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_password
from app.models.chat import AiChatMessage, AiChatSession
from app.models.user import AuthCredential, User
from tests.conftest import csrf_headers


async def _account(db_session, label):
    user = User(name=f"beta-chat-{label}")
    db_session.add(user)
    await db_session.flush()
    email = f"beta-chat-{label}-{user.id}@example.com"
    password = "Disposable-chat-fixture-42!"
    db_session.add(AuthCredential(user_id=user.id, email=email,
        password_hash=hash_password(password), role="friend"))
    await db_session.commit()
    return user.id, email, password


async def _chat(db_session, user_id, label):
    now = datetime.now(UTC)
    row = AiChatSession(user_id=user_id, title=label,
        started_at=now, last_activity_at=now)
    db_session.add(row)
    await db_session.flush()
    db_session.add_all([
        AiChatMessage(session_id=row.id, role="user", content=f"Synthetic question {label}"),
        AiChatMessage(session_id=row.id, role="assistant", content=f"Synthetic answer {label}"),
    ])
    await db_session.commit()
    return row.id


async def _login(client, account):
    client.cookies.clear()
    assert (await client.post("/auth/login", json={"email": account[1], "password": account[2]})).status_code == 200


async def test_delete_removes_session_and_messages_and_preserves_other_chats(client, db_session):
    account = await _account(db_session, "delete-owner")
    victim = await _chat(db_session, account[0], "Delete this synthetic chat")
    survivor = await _chat(db_session, account[0], "Preserve this synthetic chat")
    await _login(client, account)
    assert (await client.get(f"/coach/chats/{victim}")).json()["message_count"] == 2
    result = await client.delete(f"/coach/chats/{victim}", headers=csrf_headers(client))
    assert result.status_code == 204
    assert result.content == b""
    assert (await client.get(f"/coach/chats/{victim}")).status_code == 404
    assert (await client.post("/coach/chats", json={"text": "Resume deleted", "session_id": victim}, headers=csrf_headers(client))).status_code == 404
    assert (await client.delete(f"/coach/chats/{victim}", headers=csrf_headers(client))).status_code == 404
    assert [row["id"] for row in (await client.get("/coach/chats")).json()] == [survivor]
    assert (await client.get(f"/coach/chats/{survivor}")).json()["message_count"] == 2
    assert await db_session.scalar(select(AiChatSession.id).where(AiChatSession.id == victim)) is None
    assert (await db_session.scalars(select(AiChatMessage.id).where(AiChatMessage.session_id == victim))).all() == []


async def test_foreign_chat_get_resume_and_delete_are_hidden_and_unchanged(client, db_session):
    owner = await _account(db_session, "foreign-owner")
    outsider = await _account(db_session, "outsider")
    private = await _chat(db_session, owner[0], "Private synthetic chat")
    outsider_chat = await _chat(db_session, outsider[0], "Outsider synthetic chat")
    await _login(client, outsider)
    assert [row["id"] for row in (await client.get("/coach/chats")).json()] == [outsider_chat]
    assert (await client.get(f"/coach/chats/{private}")).status_code == 404
    assert (await client.delete(f"/coach/chats/{private}", headers=csrf_headers(client))).status_code == 404
    assert (await client.post("/coach/chats", json={"text": "Unauthorized resume", "session_id": private}, headers=csrf_headers(client))).status_code == 404
    await _login(client, owner)
    assert (await client.get(f"/coach/chats/{private}")).json()["message_count"] == 2


async def test_chat_delete_enforces_csrf_and_keeps_transcript_on_rejection(client, db_session):
    account = await _account(db_session, "csrf")
    chat = await _chat(db_session, account[0], "CSRF protected synthetic chat")
    await _login(client, account)
    assert (await client.delete(f"/coach/chats/{chat}")).status_code == 403
    assert (await client.delete(f"/coach/chats/{chat}", headers={"X-CSRF-Token": "invalid"})).status_code == 403
    assert (await client.get(f"/coach/chats/{chat}")).json()["message_count"] == 2
