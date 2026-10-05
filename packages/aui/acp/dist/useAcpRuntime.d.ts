import { type AssistantRuntime, type AttachmentAdapter, type DictationAdapter, type ExternalStoreSharedOptions, type FeedbackAdapter, type RealtimeVoiceAdapter, type SpeechSynthesisAdapter } from "@assistant-ui/core";
import { AcpClient, type AcpWebSocketFactory } from "./AcpClient.js";
import { type AcpPermissionsMode } from "./AcpThreadController.js";
import type { AcpImplementation, AcpMcpServer } from "./types.js";
export type UseAcpRuntimeOptions = ExternalStoreSharedOptions & {
    /** Pre-built ACP client instance. Provide this OR `url`. */
    client?: AcpClient;
    /** WebSocket endpoint of the ACP agent, e.g. `ws://127.0.0.1:2770/`. */
    url?: string;
    /**
     * Working directory passed to `session/new`. ACP requires an absolute path;
     * defaults to `"/"`.
     */
    cwd?: string;
    /** MCP servers passed to `session/new`. */
    mcpServers?: readonly AcpMcpServer[];
    /** Client identity for the `initialize` handshake. */
    clientInfo?: AcpImplementation;
    /** Inject a WebSocket implementation (tests / custom transports). */
    webSocketFactory?: AcpWebSocketFactory;
    /**
     * Permission policy. `"ask"` (default) surfaces ACP permission requests as
     * tool-call approvals in the UI; `"auto-allow"` answers them with the
     * agent's first allow-family option.
     */
    permissions?: AcpPermissionsMode;
    /** Connect on mount. Defaults to true. */
    autoConnect?: boolean;
    /**
     * After connecting, open the agent's newest thread for this cwd — or mint
     * a session when it remembers none — so a session exists (and its id is
     * visible) before the first prompt. Defaults to false: hosts that prefer
     * a lazy `session/new` on the first prompt keep it.
     */
    restoreOnConnect?: boolean;
    /**
     * Let a send made while a turn is running wait in `composer.queue` and go
     * out as its own `session/prompt`, in order, as each turn settles. Off by
     * default: without it a mid-run send cancels the turn in flight, since an
     * ACP agent runs one turn per session and has no way to take a second
     * prompt while it works.
     */
    unstable_enableMessageQueue?: boolean;
    /** Called when an error occurs. */
    onError?: (error: Error) => void;
    /** Called when a run is cancelled. */
    onCancel?: () => void;
    /**
     * There is deliberately no `history` adapter: the agent owns an ACP
     * conversation, so a transcript restored from storage would show messages the
     * next `session/new` knows nothing about.
     */
    adapters?: {
        attachments?: AttachmentAdapter;
        speech?: SpeechSynthesisAdapter;
        dictation?: DictationAdapter;
        voice?: RealtimeVoiceAdapter;
        feedback?: FeedbackAdapter;
    };
};
export declare function useAcpRuntime(options: UseAcpRuntimeOptions): AssistantRuntime;