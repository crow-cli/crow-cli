import type { Unsubscribe } from "../types/unsubscribe.js";
export declare namespace SpeechSynthesisAdapter {
    type Status = {
        type: "starting" | "running";
    } | {
        type: "ended";
        reason: "finished" | "cancelled" | "error";
        error?: unknown;
    };
    type Utterance = {
        status: Status;
        cancel: () => void;
        subscribe: (callback: () => void) => Unsubscribe;
    };
}
export type SpeechSynthesisAdapter = {
    speak: (text: string) => SpeechSynthesisAdapter.Utterance;
};
export declare namespace DictationAdapter {
    type Status = {
        type: "starting" | "running";
    } | {
        type: "ended";
        reason: "stopped" | "cancelled" | "error";
    };
    type Result = {
        transcript: string;
        isFinal?: boolean;
    };
    type Session = {
        status: Status;
        stop: () => Promise<void>;
        cancel: () => void;
        onSpeechStart: (callback: () => void) => Unsubscribe;
        onSpeechEnd: (callback: (result: Result) => void) => Unsubscribe;
        onSpeech: (callback: (result: Result) => void) => Unsubscribe;
    };
}
export type DictationAdapter = {
    listen: () => DictationAdapter.Session;
    disableInputDuringDictation?: boolean;
};
export declare class WebSpeechSynthesisAdapter implements SpeechSynthesisAdapter {
    speak(text: string): SpeechSynthesisAdapter.Utterance;
}
interface SpeechRecognitionInstance extends EventTarget {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    start(): void;
    stop(): void;
    abort(): void;
}
interface SpeechRecognitionConstructor {
    new (): SpeechRecognitionInstance;
}
declare global {
    interface Window {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
    }
}
export declare class WebSpeechDictationAdapter implements DictationAdapter {
    private _language;
    private _continuous;
    private _interimResults;
    constructor(options?: {
        language?: string;
        continuous?: boolean;
        interimResults?: boolean;
    });
    static isSupported(): boolean;
    listen(): DictationAdapter.Session;
}
export {};