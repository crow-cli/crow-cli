import type { VoiceSessionState } from "../../runtime/interfaces/thread-runtime-core.js";
export declare const useVoiceState: () => VoiceSessionState | undefined;
export declare const useVoiceVolume: () => number;
export declare const useVoiceControls: () => {
    connect: () => void;
    disconnect: () => void;
    mute: () => void;
    unmute: () => void;
};