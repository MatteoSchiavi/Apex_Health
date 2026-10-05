export interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

declare global {
  interface WindowEventMap {
    beforeinstallprompt: InstallPromptEvent;
    appinstalled: Event;
  }
}

let pending: InstallPromptEvent | null = null;
export const getInstallPrompt = () => pending;

// Capture this before Settings mounts: browsers can offer installation while
// the user is still on the dashboard.
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  pending = event;
});
window.addEventListener("appinstalled", () => { pending = null; });
export const clearInstallPrompt = () => { pending = null; };
