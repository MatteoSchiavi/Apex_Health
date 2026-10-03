"""Durable Oura sync: scheduled fan-out and account-scoped retries."""

from app.tasks.provider_sync import register_tasks

sync_all_oura, sync_user_oura = register_tasks("oura")
