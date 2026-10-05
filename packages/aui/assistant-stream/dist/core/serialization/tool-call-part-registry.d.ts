import type { ToolCallStreamController } from "../modules/tool-call.js";
export declare const createToolCallPartRegistry: () => {
    start: (toolCallId: string, create: () => ToolCallStreamController) => ToolCallStreamController;
    get: (toolCallId: string) => ToolCallStreamController;
    tryGet: (toolCallId: string) => ToolCallStreamController | undefined;
    appendArgsText: (toolCallController: ToolCallStreamController, argsTextDelta: string) => void;
    closeArgsText: (toolCallController: ToolCallStreamController) => void;
    isArgsTextClosed: (toolCallController: ToolCallStreamController) => boolean;
    setResponse: (toolCallController: ToolCallStreamController, response: Parameters<ToolCallStreamController["setResponse"]>[0]) => void;
    closeOpenArgsText: () => void;
    closeAll: () => void;
};