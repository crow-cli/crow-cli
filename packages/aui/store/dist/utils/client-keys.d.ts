import type { AssistantClient } from "../types/client.js";
export declare const isIgnoredClientKey: (key: string | symbol) => key is "optional" | "subscribe" | "on" | "__proto__" | symbol;
export declare const clientScopeKeys: (client: AssistantClient) => string[];