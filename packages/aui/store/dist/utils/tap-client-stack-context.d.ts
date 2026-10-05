import type { ClientMethods } from "../types/client.js";
/**
 * Symbol used to get the client index from a ClientProxy.
 */
export declare const SYMBOL_CLIENT_INDEX: unique symbol;
/**
 * Get the index of a client (its position in the client stack when created).
 */
export declare const getClientIndex: (client: ClientMethods) => number;
/**
 * The client stack - an array of clients representing the current hierarchy.
 */
export type ClientStack = readonly ClientMethods[];
/**
 * Get the current client stack inside a tap resource.
 */
export declare const useClientStack: () => ClientStack;
/**
 * Execute a callback with a client pushed onto the stack.
 * The stack is duplicated, not mutated.
 */
export declare const useClientStackProvider: <T>(client: ClientMethods, callback: () => T) => T;