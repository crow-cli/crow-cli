import type { AssistantEventName, AssistantEventPayload } from "../types/events.js";
import type { AssistantClient, ClientNames } from "../types/client.js";
import { type ClientStack } from "./tap-client-stack-context.js";
type EmitFn = <TEvent extends Exclude<AssistantEventName, "*">>(event: TEvent, payload: AssistantEventPayload[TEvent], clientStack: ClientStack) => void;
export type AssistantTapContextValue = {
    clientRef: {
        parent: AssistantClient;
        current: AssistantClient | null;
    };
    emit: EmitFn;
};
export declare const useAssistantTapContextProvider: <TResult>(value: AssistantTapContextValue, fn: () => TResult) => TResult;
export declare const useAssistantClientRef: () => {
    parent: AssistantClient;
    current: AssistantClient | null;
};
/**
 * Runs a registration effect that follows the bound client instance of one
 * scope: when a structural change remounts or replaces that instance, the
 * previous cleanup runs and the effect runs again against the replacement.
 * Value updates on the same instance do not re-run it, and while the scope
 * is unavailable only cleanup runs, so the effect always executes against a
 * bound scope. A migration whose effect throws stays unapplied, so the next
 * notification retries it. The client ref is committed before effects run,
 * so reads through it inside the effect see the finalized client.
 */
export declare const useAssistantScopeEffect: (scope: ClientNames, effect: () => (() => void) | void, deps: readonly unknown[]) => void;
export declare const useAssistantEmit: () => <TEvent extends Exclude<AssistantEventName, "*">>(event: TEvent, payload: AssistantEventPayload[TEvent]) => void;
export {};