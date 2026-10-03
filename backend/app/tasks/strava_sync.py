"""Durable Strava sync: scheduled fan-out and account-scoped retries."""

from app.tasks.provider_sync import register_tasks

sync_all_strava, sync_user_strava = register_tasks("strava")
