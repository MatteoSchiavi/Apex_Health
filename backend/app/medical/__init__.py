"""Medical/lifestyle module (MASTER_SPEC §23 Phase 4)."""

from app.medical.labs import decrypt_notes, evaluate_ferritin_alert, record_lab_panel

__all__ = ["decrypt_notes", "evaluate_ferritin_alert", "record_lab_panel"]
