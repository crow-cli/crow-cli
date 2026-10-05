import { type ResourceElement } from "@assistant-ui/tap";
import type { AssistantClient, ClientOutput, ScopesConfig } from "@assistant-ui/store";
export type InMemoryThreadListProps = {
    /**
     * Creates the selected thread resource. The list keys the returned element
     * by `threadId`, so thread-owned state does not survive a selection change.
     */
    thread: (threadId: string) => ResourceElement<ClientOutput<"thread">>;
    onSwitchToThread?: (threadId: string) => void;
    onSwitchToNewThread?: () => void;
    onDelete?: (threadId: string) => void;
};
export declare const InMemoryThreadList: import("@assistant-ui/tap").Resource<ClientOutput<"threads">, [props: InMemoryThreadListProps]>;
/**
 * The scope defaults `InMemoryThreadList` installs when it is used as the
 * `threads` config entry. Adapter packages that wrap it in their own config
 * entry attach this to the wrapping resource for scope parity.
 */
export declare const inMemoryThreadListTransformScopes: (scopes: ScopesConfig, parent: AssistantClient) => void;