import type { AssistantRuntime, UserCommands as CoreUserCommands } from "@assistant-ui/core";
import type { AssistantTransportCommand as CoreAssistantTransportCommand, AssistantTransportConnectionMetadata as CoreAssistantTransportConnectionMetadata, AssistantTransportOptions as CoreAssistantTransportOptions, AssistantTransportProtocol, SendCommandsRequestBody as CoreSendCommandsRequestBody } from "@assistant-ui/core/react";
import type { UserCommands, UserExternalState } from "./augmentations.js";
export type { AssistantTransportProtocol };
export type SendCommandsRequestBody = {
    [K in keyof CoreSendCommandsRequestBody as K extends "commands" ? never : K]: CoreSendCommandsRequestBody[K];
} & {
    commands: AssistantTransportCommand[];
};
export type AssistantTransportCommand = Exclude<CoreAssistantTransportCommand, CoreUserCommands> | UserCommands;
export type AssistantTransportConnectionMetadata = Omit<CoreAssistantTransportConnectionMetadata, "pendingCommands"> & {
    pendingCommands: AssistantTransportCommand[];
};
export type AssistantTransportStateConverter<T> = (state: T, connectionMetadata: AssistantTransportConnectionMetadata) => ReturnType<CoreAssistantTransportOptions<T>["converter"]>;
export type AssistantTransportOptions<T> = Omit<CoreAssistantTransportOptions<T>, "converter" | "prepareSendCommandsRequest" | "onError" | "onCancel"> & {
    converter: AssistantTransportStateConverter<T>;
    prepareSendCommandsRequest?: (body: SendCommandsRequestBody) => Record<string, unknown> | Promise<Record<string, unknown>>;
    onError?: (error: Error, params: {
        commands: AssistantTransportCommand[];
        updateState: (updater: (state: T) => T) => void;
    }) => void | Promise<void>;
    onCancel?: (params: {
        commands: AssistantTransportCommand[];
        updateState: (updater: (state: T) => T) => void;
        error?: Error;
    }) => void;
};
export declare const useAssistantTransportRuntime: <T>(options: AssistantTransportOptions<T>) => AssistantRuntime;
export declare const useAssistantTransportSendCommand: () => (command: AssistantTransportCommand) => void;
export declare function useAssistantTransportState(): UserExternalState;
export declare function useAssistantTransportState<T>(selector: (state: UserExternalState) => T): T;