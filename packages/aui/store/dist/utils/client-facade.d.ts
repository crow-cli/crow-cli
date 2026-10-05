import type { AssistantClient } from "../types/client.js";
import type { AssistantClientSource } from "../createAssistantClient.js";
/**
 * Creates a stable `AssistantClient` facade over a source.
 *
 * The client object changes identity on structural updates; the facade keeps
 * one stable object that always forwards to the source's current client, so a
 * binding can hand consumers a single reference for the provider's lifetime.
 */
export declare const createClientFacade: (source: AssistantClientSource) => AssistantClient;