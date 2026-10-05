import type { ChangelogRecord, ReducerCell, ResourceFiber, TapRoot } from "../types.js";
export declare const createResourceFiberRoot: (dispatchUpdate: (evaluate: () => boolean, apply: () => boolean) => void) => TapRoot;
export declare const commitRoot: (root: TapRoot) => void;
export declare const setRootVersion: (root: TapRoot, version: number) => void;
export declare const applyChangelogRecord: (record: ChangelogRecord) => void;
export declare const addCommit: (fiber: ResourceFiber<any>, callback: () => void) => void;
export declare const addRollback: (root: TapRoot, callback: () => void) => void;
export declare const markReducerDirty: (fiber: ResourceFiber<any>, cell: ReducerCell) => void;