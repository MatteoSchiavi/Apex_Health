from app.tasks.provider_sync import register_tasks

sync_all_coros, sync_user_coros = register_tasks("coros")
