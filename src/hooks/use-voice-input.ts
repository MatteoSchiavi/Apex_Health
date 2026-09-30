"use client";

/**
 * Apex Health — useVoiceInput hook.
 *
 * Records audio from the user's microphone via MediaRecorder, then POSTs the
 * base64-encoded audio to /api/asr for transcription. Returns the transcript
 * text. Used by the Coach page for voice-driven chat input.
 *
 * States:
 *  - idle: not recording, no transcript
 *  - recording: capturing audio, UI shows red dot + Stop button
 *  - transcribing: sending to /api/asr, UI shows spinner
 *  - error: failed (permission denied, network error, empty transcript)
 *
 * Browser support: modern Chrome/Firefox/Safari with MediaRecorder + getUserMedia.
 */

import { useCallback, useEffect, useRef, useState } from "react";

type VoiceState = "idle" | "recording" | "transcribing" | "error";

export function useVoiceInput() {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopTracks();
    };
  }, []);

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const startRecording = useCallback(async () => {
    setError(null);
    setState("recording");
    chunksRef.current = [];

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone not supported in this browser");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        stopTracks();

        if (blob.size === 0) {
          setState("error");
          setError("No audio captured");
          return;
        }

        setState("transcribing");
        try {
          const reader = new FileReader();
          reader.onloadend = async () => {
            const base64 = reader.result as string;
            const resp = await fetch("/api/asr", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ audio: base64 }),
            });
            const json = await resp.json();
            if (!json.ok) throw new Error(json.error || "Transcription failed");
            const text = (json.text as string) || "";
            if (!text) throw new Error("Empty transcript");
            // Emit the transcript via a custom event the host component can listen for
            window.dispatchEvent(new CustomEvent("apex-voice-transcript", { detail: text }));
            setState("idle");
          };
          reader.readAsDataURL(blob);
        } catch (e) {
          setState("error");
          setError(e instanceof Error ? e.message : "Transcription failed");
        }
      };

      mr.start();
    } catch (e) {
      setState("error");
      setError(
        e instanceof Error
          ? e.name === "NotAllowedError"
            ? "Microphone permission denied"
            : e.message
          : "Failed to start recording"
      );
      stopTracks();
    }
  }, []);

  const stopRecording = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      mr.stop();
    }
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setError(null);
  }, []);

  return {
    state,
    error,
    startRecording,
    stopRecording,
    reset,
    isRecording: state === "recording",
    isTranscribing: state === "transcribing",
  };
}
