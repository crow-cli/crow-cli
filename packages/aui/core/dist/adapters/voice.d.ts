import type { Unsubscribe } from "../types/unsubscribe.js";
export declare namespace RealtimeVoiceAdapter {
    type Status = {
        type: "starting" | "running";
    } | {
        type: "ended";
        reason: "finished" | "cancelled" | "error";
        error?: unknown;
    };
    type Mode = "listening" | "speaking";
    type TranscriptItem = {
        role: "user" | "assistant";
        text: string;
        isFinal?: boolean;
    };
    type Session = {
        status: Status;
        isMuted: boolean;
        disconnect: () => void;
        mute: () => void;
        unmute: () => void;
        /**
         * Delivers typed text into the connected session. The runtime records the typed turn in the thread itself, so the session must not echo it through `onTranscript`. A session without it takes audio only.
         */
        sendText?: ((text: string) => void | Promise<void>) | undefined;
        onStatusChange: (callback: (status: Status) => void) => Unsubscribe;
        onTranscript: (callback: (transcript: TranscriptItem) => void) => Unsubscribe;
        onModeChange: (callback: (mode: Mode) => void) => Unsubscribe;
        onVolumeChange: (callback: (volume: number) => void) => Unsubscribe;
    };
}
export type RealtimeVoiceAdapter = {
    connect: (options: {
        abortSignal?: AbortSignal;
    }) => RealtimeVoiceAdapter.Session;
};
export type VoiceSessionControls = {
    disconnect: () => void;
    mute: () => void;
    unmute: () => void;
    /**
     * Delivers typed text to the provider. The session exposes `sendText` once these controls resolve and repeats its running status when they land after it, so status listeners can re-read the session; the runtime records the typed turn itself.
     */
    sendText?: ((text: string) => void | Promise<void>) | undefined;
};
export type VoiceSessionHelpers = {
    setStatus: (status: RealtimeVoiceAdapter.Status) => void;
    end: (reason: "finished" | "cancelled" | "error", error?: unknown) => void;
    emitTranscript: (item: RealtimeVoiceAdapter.TranscriptItem) => void;
    emitMode: (mode: RealtimeVoiceAdapter.Mode) => void;
    emitVolume: (volume: number) => void;
    isDisposed: () => boolean;
};
export declare function createVoiceSession(options: {
    abortSignal?: AbortSignal;
}, setup: (helpers: VoiceSessionHelpers) => Promise<VoiceSessionControls>): RealtimeVoiceAdapter.Session;