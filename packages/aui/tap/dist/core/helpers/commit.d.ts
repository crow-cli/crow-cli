import type { CommitCallbacks, EffectCell, ResourceFiber } from "../types.js";
export declare function commitAllCallbacks(callbacks: CommitCallbacks): void;
export declare function reconcileEffects<R>(fiber: ResourceFiber<R>, includeInsertion?: boolean): void;
export declare function cleanupCells(cells: EffectCell[]): void;