import type { ClientEvents, ClientMeta, ClientNames } from "./client.js";
type UnionToIntersection<U> = (U extends unknown ? (x: U) => void : never) extends (x: infer I) => void ? I : never;
type ClientEventMap = UnionToIntersection<{
    [K in ClientNames]: ClientEvents<K>;
}[ClientNames]>;
type WildcardPayload = {
    [K in keyof ClientEventMap]: {
        event: K;
        payload: ClientEventMap[K];
    };
}[keyof ClientEventMap];
export type AssistantEventPayload = ClientEventMap & {
    "*": WildcardPayload;
};
export type AssistantEventName = keyof AssistantEventPayload;
type EventSource<T extends AssistantEventName> = T extends `${infer Source}.${string}` ? Source : never;
type ParentOf<K extends ClientNames> = ClientMeta<K> extends {
    source: infer S;
} ? S extends ClientNames ? S : never : never;
type AncestorsOf<K extends ClientNames, Seen extends ClientNames = never> = K extends Seen ? never : ParentOf<K> extends never ? never : ParentOf<K> | AncestorsOf<ParentOf<K>, Seen | K>;
/** Valid scopes: `"*"` | event source | ancestors of event source */
export type AssistantEventScope<TEvent extends AssistantEventName> = "*" | EventSource<TEvent> | (EventSource<TEvent> extends ClientNames ? AncestorsOf<EventSource<TEvent>> : never);
export type AssistantEventSelector<TEvent extends AssistantEventName> = TEvent | {
    scope: AssistantEventScope<TEvent>;
    event: TEvent;
};
export declare const normalizeEventSelector: <TEvent extends AssistantEventName>(selector: AssistantEventSelector<TEvent>) => {
    scope: AssistantEventScope<TEvent>;
    event: TEvent;
};
export type AssistantEventCallback<TEvent extends AssistantEventName> = (payload: AssistantEventPayload[TEvent]) => void;
export {};