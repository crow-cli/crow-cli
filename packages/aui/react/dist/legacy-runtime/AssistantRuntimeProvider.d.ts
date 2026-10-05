import { type FC, type PropsWithChildren } from "react";
import { type AssistantClient, type AuiConfig } from "@assistant-ui/store";
import type { AssistantRuntime } from "./runtime/AssistantRuntime.js";
export declare namespace AssistantRuntimeProvider {
    type Props = PropsWithChildren<{
        /**
         * The assistant runtime to expose to descendants. Build one with
         * `useLocalRuntime`, `useExternalStoreRuntime`, or
         * `useAssistantTransportRuntime`.
         */
        runtime: AssistantRuntime;
        /**
         * Optional parent `AssistantClient` whose scopes are inherited by the
         * client created for this runtime. Use this when nesting an
         * `AssistantRuntimeProvider` inside another assistant context. Omit this
         * prop when there is no parent client.
         * @defaultValue undefined
         */
        aui?: AssistantClient;
        /**
         * Optional extra scopes provided alongside the runtime's `threads`
         * scope; build with `AuiConfig`.
         */
        config?: AuiConfig;
    }>;
}
export declare const AssistantRuntimeProviderImpl: FC<AssistantRuntimeProvider.Props>;
export declare const AssistantRuntimeProvider: import("react").NamedExoticComponent<AssistantRuntimeProvider.Props>;