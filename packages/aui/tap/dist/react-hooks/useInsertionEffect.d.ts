export declare namespace useInsertionEffect {
    type Destructor = () => void;
    type EffectCallback = () => Destructor | undefined;
}
export declare function useInsertionEffect(effect: useInsertionEffect.EffectCallback, deps?: readonly unknown[]): void;