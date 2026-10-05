import type { FC, PropsWithChildren } from "react";
export type QueueItemByIndexProviderProps = PropsWithChildren<{
    index: number;
}>;
export declare const QueueItemByIndexProvider: FC<QueueItemByIndexProviderProps>;