"""Durable Whoop sync: scheduled fan-out and account-scoped retries."""

from app.tasks.provider_sync import register_tasks

sync_all_whoop, sync_user_whoop = register_tasks("whoop")
