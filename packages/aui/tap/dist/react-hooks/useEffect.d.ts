import type { EffectCell } from "../core/types.js";
export declare namespace useEffect {
    type Destructor = () => void;
    type EffectCallback = () => Destructor | undefined;
}
export declare function useEffectImpl(effect: useEffect.EffectCallback, deps: readonly unknown[] | undefined, type: EffectCell["type"]): void;
export declare function useEffect(effect: useEffect.EffectCallback): void;
export declare function useEffect(effect: useEffect.EffectCallback, deps: readonly unknown[]): void;