declare function useReactEffectEventShim<T extends (...args: any[]) => any>(callback: T): T;
export declare const useReactEffectEvent: typeof useReactEffectEventShim;
export {};