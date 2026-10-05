import type { AssistantCloud } from "./AssistantCloud.js";
export declare function generateThreadTitle(cloud: AssistantCloud, options: {
    threadId: string;
    messages: readonly {
        role: string;
        content: readonly {
            type: "text";
            text: string;
        }[];
    }[];
}): Promise<string | null>;