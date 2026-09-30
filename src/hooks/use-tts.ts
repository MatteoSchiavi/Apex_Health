"use client";

/**
 * Apex Health — useTTS hook.
 *
 * Calls /api/tts to convert text to speech, then plays the returned audio
 * via an HTMLAudioElement. Used by the Coach page to read assistant messages
 * aloud.
 *
 * States:
 *  - idle: no audio playing
 *  - loading: fetching TTS audio
 *  - playing: audio is playing
 *  - error: failed
 *
 * The hook caches the audio URL per text string so re-playing the same message
 * doesn't re-hit the API.
 */

import { useCallback, useEffect, useRef, useState } from "react";

type TTSState = "idle" | "loading" | "playing" | "error";

export function useTTS(opts?: { voice?: string; autoPlayText?: (text: string) => boolean }) {
  const [state, setState] = useState<TTSState>("idle");
  const [activeText, setActiveText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cacheRef = useRef<Map<string, string>>(new Map()); // text → objectURL
  const voiceRef = useRef(opts?.voice ?? "tongtong");
  const autoPlayRef = useRef(opts?.autoPlayText);

  // Keep refs in sync with latest props without re-running the speak effect
  useEffect(() => {
    voiceRef.current = opts?.voice ?? "tongtong";
  }, [opts?.voice]);
  useEffect(() => {
    autoPlayRef.current = opts?.autoPlayText;
  }, [opts?.autoPlayText]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      // Revoke all cached object URLs
      cacheRef.current.forEach((url) => URL.revokeObjectURL(url));
      cacheRef.current.clear();
    };
  }, []);

  const speak = useCallback(async (text: string) => {
    setError(null);

    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    if (!text.trim()) return;

    setActiveText(text);
    setState("loading");

    try {
      let url = cacheRef.current.get(text);
      if (!url) {
        const resp = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, voice: voiceRef.current, speed: 1.0 }),
        });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(errJson.error || `HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        url = URL.createObjectURL(blob);
        cacheRef.current.set(text, url);
      }

      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onplay = () => setState("playing");
      audio.onended = () => {
        setState("idle");
        setActiveText(null);
      };
      audio.onerror = () => {
        setState("error");
        setError("Audio playback failed");
        setActiveText(null);
      };
      await audio.play();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "TTS failed");
      setActiveText(null);
    }
  }, []);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setState("idle");
    setActiveText(null);
  }, []);

  /** If autoPlayText returns true, speak the text. Used by Coach to auto-play
   *  incoming assistant messages when the user has enabled it in Settings. */
  const maybeAutoPlay = useCallback((text: string) => {
    if (autoPlayRef.current?.(text)) {
      speak(text);
    }
  }, [speak]);

  return {
    state,
    error,
    activeText,
    speak,
    stop,
    maybeAutoPlay,
    isPlaying: state === "playing",
    isLoading: state === "loading",
  };
}
