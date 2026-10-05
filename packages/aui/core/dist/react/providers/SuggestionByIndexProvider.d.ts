import type { FC, PropsWithChildren } from "react";
export type SuggestionByIndexProviderProps = PropsWithChildren<{
    index: number;
}>;
export declare const SuggestionByIndexProvider: FC<SuggestionByIndexProviderProps>;