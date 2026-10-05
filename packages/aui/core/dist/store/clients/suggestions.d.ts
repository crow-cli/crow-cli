import type { ClientOutput } from "@assistant-ui/store";
import type { ThreadSuggestion } from "../../runtime/interfaces/thread-runtime-core.js";
export type SuggestionConfig = string | {
    title: string;
    label: string;
    prompt: string;
};
export declare const Suggestions: import("@assistant-ui/tap").Resource<ClientOutput<"suggestions">, [suggestions?: SuggestionConfig[] | undefined]>;
export declare const ThreadSuggestions: import("@assistant-ui/tap").Resource<ClientOutput<"suggestions">, [suggestions: readonly ThreadSuggestion[]]>;