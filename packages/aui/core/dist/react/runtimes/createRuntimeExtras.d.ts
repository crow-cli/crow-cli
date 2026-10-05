import type { AssistantClient } from "@assistant-ui/store";
import { type RuntimeExtrasBrand } from "../../runtime/utils/runtime-extras-brand.js";
/** @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice. */
export type RuntimeExtras<T extends object> = {
    provide: (value: T) => T;
    is: (extras: unknown) => extras is T;
    tryGet: (extras: unknown) => T | undefined;
    get: (client: AssistantClient) => T;
    use: {
        (): T;
        <S>(select: (extras: T) => S): S;
        <S>(select: (extras: T) => S, fallback: S): S;
    };
};
/** @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice. */
export declare const unstable_createRuntimeExtrasFromBrand: <T extends object>(brand: RuntimeExtrasBrand<T>) => RuntimeExtras<T>;
/** @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice. */
export declare const createRuntimeExtras: <T extends object>(runtimeName: string) => RuntimeExtras<T>;