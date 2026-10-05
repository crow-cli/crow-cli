import { shallowEqual } from "./shallow-equal.js";
export { shallowEqual };
export declare const useShallowStable: <T extends object>(value: T) => T;
export declare const useShallowSelector: <TState, TResult extends object>(select: (state: TState) => TResult) => ((state: TState) => TResult);