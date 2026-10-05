import type { HostCell, ResourceFiber } from "../../core/types.js";
export type HostTarget = ResourceFiber<unknown> | NonNullable<HostCell["fibers"]>;
export declare const useHostCell: (target: HostTarget) => HostCell;