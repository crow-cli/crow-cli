import { type HostTarget } from "./useHostCell.js";
import type { HostCell, ResourceFiber } from "../../core/types.js";
export declare const useHostLifecycle: (target: HostTarget) => HostCell | null;
export declare const useResourceFiberHost: () => {
    version: number;
    createFiber: <R, A extends readonly any[]>(hook: (...props: A) => R, _key: string | number | undefined, onDirty?: () => void) => ResourceFiber<R>;
};