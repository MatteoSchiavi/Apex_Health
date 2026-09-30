"use client";

/**
 * Apex Health — useGlobalShortcuts hook.
 *
 * Registers global keyboard shortcuts:
 *   - "?" → open the shortcuts help modal
 *   - "g" + letter (within 800ms) → vim-style chord navigation
 *       g o → Overview, g a → Activities, g s → Sleep, g b → Biometrics,
 *       g t → Training, g c → Coach, g h → Challenges (social), g e → Settings
 *
 * Ignores keystrokes when the active element is an input/textarea/contenteditable
 * (so typing in the Coach textarea or Activities search doesn't trigger nav).
 *
 * The host component passes setView + setHelpOpen callbacks.
 */

import { useEffect, useRef } from "react";
import type { ViewKey } from "@/lib/apex/types";

const CHORD_TIMEOUT_MS = 800;

const CHORD_MAP: Record<string, ViewKey> = {
  o: "overview",
  a: "activities",
  s: "sleep",
  b: "biometrics",
  t: "training",
  c: "coach",
  h: "social", // h for cHallenges
  e: "settings",
};

export function useGlobalShortcuts({
  setView,
  setHelpOpen,
  onFocusFirstField,
}: {
  setView: (v: ViewKey) => void;
  setHelpOpen: (v: boolean) => void;
  /** Optional: focus the first editable field on the current page (Settings). */
  onFocusFirstField?: () => void;
}) {
  const chordTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chordArmedRef = useRef(false);

  useEffect(() => {
    const isEditable = () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName.toLowerCase();
      return tag === "input" || tag === "textarea" || el.isContentEditable;
    };

    const onKey = (e: KeyboardEvent) => {
      // Help modal: "?" (Shift+/)
      if (e.key === "?" && !isEditable()) {
        e.preventDefault();
        setHelpOpen(true);
        return;
      }

      // "f" — focus the first editable field on the current page (Settings)
      if (e.key.toLowerCase() === "f" && !isEditable() && onFocusFirstField) {
        e.preventDefault();
        onFocusFirstField();
        return;
      }

      // Vim-style "g" chord
      if (e.key.toLowerCase() === "g" && !isEditable()) {
        // If already armed, ignore (double-g is meaningless)
        if (!chordArmedRef.current) {
          chordArmedRef.current = true;
          if (chordTimerRef.current) clearTimeout(chordTimerRef.current);
          chordTimerRef.current = setTimeout(() => {
            chordArmedRef.current = false;
            chordTimerRef.current = null;
          }, CHORD_TIMEOUT_MS);
        }
        return;
      }

      // If chord is armed, look up the next key
      if (chordArmedRef.current) {
        const target = CHORD_MAP[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          setView(target);
        }
        // Reset chord regardless
        chordArmedRef.current = false;
        if (chordTimerRef.current) {
          clearTimeout(chordTimerRef.current);
          chordTimerRef.current = null;
        }
        return;
      }

      // Esc cancels any pending chord
      if (e.key === "Escape" && chordArmedRef.current) {
        chordArmedRef.current = false;
        if (chordTimerRef.current) {
          clearTimeout(chordTimerRef.current);
          chordTimerRef.current = null;
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (chordTimerRef.current) clearTimeout(chordTimerRef.current);
    };
  }, [setView, setHelpOpen, onFocusFirstField]);
}
