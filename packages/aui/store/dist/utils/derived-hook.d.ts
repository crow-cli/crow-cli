type Hook = (...args: any[]) => any;
export declare const markDerivedHook: (hook: Hook) => void;
export declare const isDerivedHook: (hook: Hook) => boolean;
export {};