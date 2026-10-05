import type { ResourceFiber, TapRoot } from "./types.js";
export declare function createResourceFiber<R>(hook: (...args: any[]) => R, root: TapRoot, markDirty: (() => void) | undefined, strictMode: "root" | "child" | null): ResourceFiber<R>;
export declare function discardWipRender<R>(fiber: ResourceFiber<R>): void;
export declare function unmountResourceFiber<R>(fiber: ResourceFiber<R>, permanent?: boolean): void;
export declare function unmountResourceFibers(fibers: readonly ResourceFiber<unknown>[]): void;
export declare function renderResourceFiber<R>(fiber: ResourceFiber<R>, args: readonly unknown[]): R;
export declare function commitResourceFiber<R>(fiber: ResourceFiber<R>): void;