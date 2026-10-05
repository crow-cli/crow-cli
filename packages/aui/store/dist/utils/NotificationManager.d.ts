import type { ClientStack } from "./tap-client-stack-context.js";
import type { AssistantEventName, AssistantEventPayload } from "../types/events.js";
import type { Unsubscribe } from "../types/client.js";
export type NotificationManager = {
    on<TEvent extends AssistantEventName>(event: TEvent, callback: (payload: AssistantEventPayload[TEvent], clientStack: ClientStack) => void): Unsubscribe;
    emit<TEvent extends Exclude<AssistantEventName, "*">>(event: TEvent, payload: AssistantEventPayload[TEvent], clientStack: ClientStack): void;
    subscribe(callback: () => void): Unsubscribe;
    notifySubscribers(): void;
};
export declare const createNotificationManager: () => NotificationManager;
export declare const useNotificationManager: () => NotificationManager;