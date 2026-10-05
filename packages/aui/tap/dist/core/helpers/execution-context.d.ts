import type { ResourceFiber } from "../types.js";
export declare function withResourceFiber<R>(fiber: ResourceFiber<R>, fn: () => void): void;
export declare function getCurrentResourceFiber(): ResourceFiber<unknown>;
export declare function peekResourceFiber(): ResourceFiber<unknown> | null;