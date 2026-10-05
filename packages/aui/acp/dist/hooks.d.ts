/** Current ACP connection state. */
export declare const useAcpConnectionState: () => import("./types.js").AcpConnectionState;
/** The ACP session id for the current connection, once created. */
export declare const useAcpSessionId: () => string | undefined;
/** Agent identity returned by the `initialize` handshake. */
export declare const useAcpAgentInfo: () => import("./types.js").AcpImplementation | undefined;
/** Capabilities the agent advertised in the `initialize` handshake. */
export declare const useAcpAgentCapabilities: () => import("./types.js").AcpAgentCapabilities | undefined;
/** The agent's plan for the current turn, when it emits one. */
export declare const useAcpPlan: () => readonly import("./types.js").AcpPlanEntry[] | undefined;
/** Session title, when the agent provides one. */
export declare const useAcpSessionTitle: () => string | undefined;
/** The agent's current mode id, when it reports modes. */
export declare const useAcpCurrentModeId: () => string | undefined;
/** Slash-style commands the agent makes available, when it reports them. */
export declare const useAcpAvailableCommands: () => readonly import("./types.js").AcpAvailableCommand[] | undefined;
/** Session configuration options, when the agent reports them. */
export declare const useAcpConfigOptions: () => readonly import("./types.js").AcpSessionConfigOption[] | undefined;
/**
 * Change one of the session's config options — the write half of
 * {@link useAcpConfigOptions}, and how a model picker moves the session's
 * model. The returned action is stable across renders; outside an ACP runtime
 * it rejects rather than silently doing nothing.
 */
export declare const useAcpSetConfigOption: () => (configId: string, value: string) => Promise<void>;
/** Context-window and cost usage, when the agent reports it. */
export declare const useAcpUsage: () => import("./types.js").AcpUsage | undefined;