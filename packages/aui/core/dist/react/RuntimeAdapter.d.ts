import type { AssistantClient, ScopesConfig } from "@assistant-ui/store";
import type { AssistantRuntime } from "../index.js";
export declare const RuntimeAdapter: import("@assistant-ui/tap").Resource<import("@assistant-ui/store").ClientOutput<"threads">, [runtime: AssistantRuntime]>;
/**
 * The scope defaults `RuntimeAdapter` installs when it is used as the `threads`
 * config entry. Adapter packages that wrap a runtime in their own config entry
 * attach this to the wrapping resource for scope parity with `RuntimeAdapter`.
 */
export declare const runtimeAdapterTransformScopes: (scopes: ScopesConfig, parent: AssistantClient) => void;