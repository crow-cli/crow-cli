type EventListener<T> = (payload: T) => unknown;
export declare const notifyEventListeners: <T>(listeners: Iterable<EventListener<T>>, payloadOrFactory: T | (() => T), errorContext: string) => void;
export {};