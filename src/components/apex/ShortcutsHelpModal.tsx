"use client";

/**
 * Apex Health — Keyboard Shortcuts Help modal.
 *
 * Opens with "?" (Shift+/) or via the dedicated button in the Command Palette
 * footer. Shows all available keyboard shortcuts grouped by category.
 *
 * Visual law: monochrome modal with eyebrow section headers, mono kbd hints,
 * and a brief explanation under each shortcut.
 */

import { useEffect } from "react";
import { X, Command, Navigation, Search, Activity, TextCursor } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { ApexButton, Eyebrow, Hairline } from "@/components/apex/kit";

interface ShortcutGroup {
  title: string;
  icon: typeof Command;
  shortcuts: { keys: string; desc: string }[];
}

const GROUPS: ShortcutGroup[] = [
  {
    title: "Global",
    icon: Command,
    shortcuts: [
      { keys: "⌘K / Ctrl+K", desc: "Open Command Palette" },
      { keys: "?", desc: "Open this keyboard shortcuts help" },
      { keys: "Esc", desc: "Close any open modal / dropdown" },
    ],
  },
  {
    title: "Navigation",
    icon: Navigation,
    shortcuts: [
      { keys: "g o", desc: "Go to Overview" },
      { keys: "g a", desc: "Go to Activities" },
      { keys: "g s", desc: "Go to Sleep" },
      { keys: "g b", desc: "Go to Biometrics" },
      { keys: "g t", desc: "Go to Training" },
      { keys: "g c", desc: "Go to Coach" },
      { keys: "g h", desc: "Go to Challenges" },
      { keys: "g e", desc: "Go to Settings" },
    ],
  },
  {
    title: "Pages",
    icon: Activity,
    shortcuts: [
      { keys: "/", desc: "Focus search on Activities list" },
      { keys: "Enter", desc: "Execute highlighted command in palette" },
      { keys: "↑ ↓", desc: "Navigate command palette items" },
    ],
  },
  {
    title: "Text input",
    icon: TextCursor,
    shortcuts: [
      { keys: "Enter", desc: "Send Coach message" },
      { keys: "Shift+Enter", desc: "New line in Coach message" },
      { keys: "Mic button", desc: "Voice input on Coach (speech-to-text)" },
    ],
  },
];

export function ShortcutsHelpModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();

  // Close on Esc
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[10vh]"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      <div
        className="relative w-full max-w-[640px] overflow-hidden rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
              <Command size={16} />
            </div>
            <div>
              <div className="eyebrow">Help</div>
              <div className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
                Keyboard Shortcuts
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface2 hover:text-ink"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="scroll-area max-h-[68vh] overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {GROUPS.map((group) => {
              const Icon = group.icon;
              return (
                <section key={group.title}>
                  <Eyebrow>
                    <span className="flex items-center gap-1.5">
                      <Icon size={11} className="text-primaryText" />
                      {group.title}
                    </span>
                  </Eyebrow>
                  <ul className="mt-2 space-y-1.5">
                    {group.shortcuts.map((sc, i) => (
                      <li key={i} className="flex items-center justify-between gap-3">
                        <span className="text-[12px] text-ink2">{sc.desc}</span>
                        <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1.5 py-0.5 text-[10px] font-semibold text-ink2">
                          {sc.keys}
                        </kbd>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>

          <Hairline className="my-4 opacity-60" />

          <p className="text-[11px] leading-[1.55] text-muted">
            Shortcuts are active across the Apex Health SPA. The "g" prefix is a
            vim-style chord: press and release <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1 py-0.5 text-[10px] font-semibold text-ink2">g</kbd>,
            then press the target letter within 800ms. Press{" "}
            <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1 py-0.5 text-[10px] font-semibold text-ink2">Esc</kbd>{" "}
            to cancel a chord mid-sequence.
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3">
          <div className="num text-[10px] text-faint">
            Apex Health · {GROUPS.reduce((s, g) => s + g.shortcuts.length, 0)} shortcuts
          </div>
          <ApexButton variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            {t("common.close")}
          </ApexButton>
        </div>
      </div>
    </div>
  );
}
