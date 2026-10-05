import type { ThreadRuntimeCore } from "../interfaces/thread-runtime-core.js";
export declare const captureThreadRuntimeGeneration: (runtime: ThreadRuntimeCore) => AbortSignal;
/** Aborts only when the runtime is disposed for good, never on invalidation. */
export declare const captureThreadRuntimeDisposal: (runtime: ThreadRuntimeCore) => AbortSignal;
export declare const invalidateThreadRuntime: (runtime: ThreadRuntimeCore) => void;
export declare const supersedeThreadRuntime: (runtime: ThreadRuntimeCore) => void;
export declare const disposeThreadRuntime: (runtime: ThreadRuntimeCore) => void;