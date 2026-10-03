"""Durable Technogym sync: scheduled fan-out and account-scoped retries."""

from app.tasks.provider_sync import register_tasks

sync_all_technogym, sync_user_technogym = register_tasks("technogym")
