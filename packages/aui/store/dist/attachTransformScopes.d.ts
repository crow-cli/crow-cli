import type { AssistantClient, ClientElement, ClientNames } from "./types/client.js";
import type { DerivedElement } from "./Derived.js";
export type ScopesConfig = {
    [K in ClientNames]?: ClientElement<K> | DerivedElement<K>;
};
type TransformScopesFn = (scopes: ScopesConfig, parent: AssistantClient) => void;
type Hook = (...args: any[]) => any;
export declare function attachTransformScopes(hook: Hook, transform: TransformScopesFn): void;
export declare function forwardTransformScopes(target: Hook, source: Hook): void;
export declare function getTransformScopes(hook: Hook): TransformScopesFn | undefined;
export {};