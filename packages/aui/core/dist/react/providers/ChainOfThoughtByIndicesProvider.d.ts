import { type FC, type PropsWithChildren } from "react";
export declare const ChainOfThoughtPartsContext: import("react").Context<{
    partKeys: readonly string[];
    startIndex: number;
} | null>;
export declare const ChainOfThoughtByIndicesProvider: FC<PropsWithChildren<{
    startIndex: number;
    endIndex: number;
}>>;