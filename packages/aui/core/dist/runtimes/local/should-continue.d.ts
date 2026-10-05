import type { ThreadAssistantMessage } from "../../types/message.js";
export declare const shouldContinue: (result: ThreadAssistantMessage, humanToolNames: string[] | undefined) => boolean;