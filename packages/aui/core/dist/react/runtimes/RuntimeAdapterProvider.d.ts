import { type FC, type ReactNode } from "react";
import type { RuntimeAdapters } from "../../runtimes/remote-thread-list/types.js";
import { useRuntimeAdapters, useRuntimeAdaptersProvider } from "./useRuntimeAdapters.js";
export type { RuntimeAdapters };
export { useRuntimeAdapters, useRuntimeAdaptersProvider };
export declare namespace RuntimeAdapterProvider {
    type Props = {
        adapters: RuntimeAdapters;
        children: ReactNode;
    };
}
export declare const RuntimeAdapterProvider: FC<RuntimeAdapterProvider.Props>;