"""Durable Garmin sync: scheduled fan-out and account-scoped retries."""

from app.tasks.provider_sync import register_tasks

sync_all_garmin, sync_user_garmin = register_tasks("garmin")
