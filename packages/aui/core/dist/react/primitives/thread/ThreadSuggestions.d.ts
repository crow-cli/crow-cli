import { type ComponentType, type FC, type ReactNode } from "react";
import type { SuggestionState } from "../../../store/scopes/suggestion.js";
type SuggestionsComponentConfig = {
    /** Component used to render each suggestion */
    Suggestion: ComponentType;
};
export declare namespace ThreadPrimitiveSuggestions {
    type Props = {
        /** @deprecated Use the children render function instead. */
        components: SuggestionsComponentConfig;
        children?: never;
    } | {
        /** Render function called for each suggestion. Receives the suggestion. */
        children: (value: {
            suggestion: SuggestionState;
        }) => ReactNode;
        components?: never;
    };
}
export declare namespace ThreadPrimitiveSuggestionByIndex {
    type Props = {
        index: number;
        components: SuggestionsComponentConfig;
    };
}
/**
 * Renders a single suggestion at the specified index.
 */
export declare const ThreadPrimitiveSuggestionByIndex: FC<ThreadPrimitiveSuggestionByIndex.Props>;
/**
 * Renders all suggestions.
 */
export declare const ThreadPrimitiveSuggestionsImpl: FC<ThreadPrimitiveSuggestions.Props>;
export declare const ThreadPrimitiveSuggestions: import("react").NamedExoticComponent<ThreadPrimitiveSuggestions.Props>;
export {};