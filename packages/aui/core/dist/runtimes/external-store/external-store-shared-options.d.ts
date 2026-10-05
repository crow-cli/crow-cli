import type { ExternalStoreAdapter } from "./external-store-adapter.js";
export type ExternalStoreSharedOptions = Pick<ExternalStoreAdapter, "isDisabled" | "isSendDisabled" | "unstable_capabilities" | "suggestions">;
export declare const pickExternalStoreSharedOptions: (options: ExternalStoreSharedOptions) => ExternalStoreSharedOptions;