import type { RuntimeAdapters } from "../../runtimes/remote-thread-list/types.js";
declare const RuntimeAdaptersContext: import("react").Context<RuntimeAdapters | null>;
export declare const useRuntimeAdaptersProvider: <T>(adapters: RuntimeAdapters | null, fn: () => T) => T;
export declare const useRuntimeAdapters: () => RuntimeAdapters | null;
export declare const useStableRuntimeAdapters: (adapters: RuntimeAdapters | null | undefined) => RuntimeAdapters | null;
export { RuntimeAdaptersContext };