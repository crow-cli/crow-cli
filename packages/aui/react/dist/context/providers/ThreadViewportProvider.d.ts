import { type FC, type PropsWithChildren } from "react";
import { type ThreadViewportStoreOptions } from "../stores/ThreadViewport.js";
export type ThreadViewportProviderProps = PropsWithChildren<{
    options?: ThreadViewportStoreOptions;
}>;
export declare const ThreadPrimitiveViewportProvider: FC<ThreadViewportProviderProps>;