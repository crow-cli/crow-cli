import type React from "react";
import type { AssistantClient } from "./types/client.js";
import { AuiConfig } from "./AuiConfig.js";
/**
 * Supplies an `AssistantClient` to the React tree.
 *
 * Place near the root of any subtree that uses {@link useAui} or the
 * primitives built on it. Components rendered outside an `AuiProvider`
 * receive a default client whose scope accessors throw on use, so
 * missing-provider mistakes surface at the point of use.
 *
 * `config` is required and must be built with {@link AuiConfig}. At the top
 * level, `config` alone creates this subtree's own client. Under a parent
 * provider, `extends` is mandatory: pass `extends={aui}` to extend the parent
 * client or `extends={null}` to isolate from it (enforced with a dev error).
 * Configs are identity-insensitive — a fresh object per render is safe.
 * A config whose scopes are all {@link Derived} keeps its scope set fixed
 * at mount (dev-enforced); configs with a root scope, and empty configs,
 * may grow and shrink scopes across renders. `ref` receives the resulting
 * client after mount.
 *
 * When mounting a runtime built with one of the runtime hooks, use
 * {@link AssistantRuntimeProvider} — it installs an `AuiProvider`
 * internally — rather than wiring `AuiProvider` yourself.
 *
 * @example
 * ```tsx
 * function MessageScope({ index, children }) {
 *   const aui = useAui();
 *   const config = AuiConfig({
 *     message: Derived({
 *       source: "thread",
 *       query: { index },
 *       get: (aui) => aui.thread.message({ index }),
 *     }),
 *   });
 *   return (
 *     <AuiProvider extends={aui} config={config}>
 *       {children}
 *     </AuiProvider>
 *   );
 * }
 * ```
 */
export declare const AuiProvider: {
    /**
     * Top-level root: creates this subtree's own client from `config`. Only
     * valid when no parent `AuiProvider` exists (dev-enforced); nested
     * providers must pass `extends`.
     */
    (props: {
        /** Scopes to create the client from; built with {@link AuiConfig}. */
        config: AuiConfig;
        /** Receives the resulting client after mount. */
        ref?: React.Ref<AssistantClient>;
        extends?: never;
        value?: never;
        /** Subtree that may read from the client. */
        children: React.ReactNode;
    }): React.ReactElement;
    /**
     * Extends a parent client with the configured scopes, or isolates with
     * `extends={null}`.
     */
    (props: {
        /**
         * Parent to extend: pass `extends={aui}` to extend the surrounding
         * client (the empty default client behaves as a root) or `extends={null}`
         * for an isolated fresh root that ignores context.
         */
        extends: AssistantClient | null;
        /** Scopes to create the client from; built with {@link AuiConfig}. */
        config: AuiConfig;
        /** Receives the resulting client after mount. */
        ref?: React.Ref<AssistantClient>;
        value?: never;
        /** Subtree that may read from the client. */
        children: React.ReactNode;
    }): React.ReactElement;
    (props: {
        /**
         * Assistant client to expose to descendants, or `null` for an isolated
         * empty root.
         *
         * @deprecated Pass an empty config built in the component body
         * (`const config = AuiConfig({})`) with `extends={client}` to expose a
         * client extending the given one, or with `extends={null}` for an
         * isolated empty root.
         */
        value: AssistantClient | null;
        extends?: never;
        config?: never;
        ref?: never;
        /** Subtree that may read from the client. */
        children: React.ReactNode;
    }): React.ReactElement;
};