"use client";
import { acpExtras } from "./acpExtras.js";
//#region src/hooks.ts
const rejectWithoutRuntime = async () => {
	throw new Error("No ACP runtime is active, so no config option can change.");
};
/** Current ACP connection state. */
const useAcpConnectionState = () => acpExtras.use((e) => e.connectionState, "disconnected");
/** The ACP session id for the current connection, once created. */
const useAcpSessionId = () => acpExtras.use((e) => e.sessionId, void 0);
/** Agent identity returned by the `initialize` handshake. */
const useAcpAgentInfo = () => acpExtras.use((e) => e.agentInfo, void 0);
/** Capabilities the agent advertised in the `initialize` handshake. */
const useAcpAgentCapabilities = () => acpExtras.use((e) => e.agentCapabilities, void 0);
/** The agent's plan for the current turn, when it emits one. */
const useAcpPlan = () => acpExtras.use((e) => e.plan, void 0);
/** Session title, when the agent provides one. */
const useAcpSessionTitle = () => acpExtras.use((e) => e.sessionTitle, void 0);
/** The agent's current mode id, when it reports modes. */
const useAcpCurrentModeId = () => acpExtras.use((e) => e.currentModeId, void 0);
/** Slash-style commands the agent makes available, when it reports them. */
const useAcpAvailableCommands = () => acpExtras.use((e) => e.availableCommands, void 0);
/** Session configuration options, when the agent reports them. */
const useAcpConfigOptions = () => acpExtras.use((e) => e.configOptions, void 0);
/**
* Change one of the session's config options — the write half of
* {@link useAcpConfigOptions}, and how a model picker moves the session's
* model. The returned action is stable across renders; outside an ACP runtime
* it rejects rather than silently doing nothing.
*/
const useAcpSetConfigOption = () => acpExtras.use((e) => e.setConfigOption, rejectWithoutRuntime);
/** Context-window and cost usage, when the agent reports it. */
const useAcpUsage = () => acpExtras.use((e) => e.usage, void 0);
//#endregion
export { useAcpAgentCapabilities, useAcpAgentInfo, useAcpAvailableCommands, useAcpConfigOptions, useAcpConnectionState, useAcpCurrentModeId, useAcpPlan, useAcpSessionId, useAcpSessionTitle, useAcpSetConfigOption, useAcpUsage };
