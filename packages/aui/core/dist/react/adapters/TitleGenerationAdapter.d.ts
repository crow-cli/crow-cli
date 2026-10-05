import type { ThreadMessage } from "../../types/message.js";
export type TitleGenerationAdapter = {
    generateTitle(messages: readonly ThreadMessage[]): Promise<string>;
};
export declare const createSimpleTitleAdapter: () => TitleGenerationAdapter;