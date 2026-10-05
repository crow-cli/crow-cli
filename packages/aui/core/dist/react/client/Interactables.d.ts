import type { ClientOutput } from "@assistant-ui/store";
import type { Unstable_InteractablesConfig } from "../types/scopes/interactables.js";
/**
 * Registers the unstable interactables store scope.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare const unstable_Interactables: import("@assistant-ui/tap").Resource<ClientOutput<"unstable_interactables">, [(Unstable_InteractablesConfig | undefined)?]>;