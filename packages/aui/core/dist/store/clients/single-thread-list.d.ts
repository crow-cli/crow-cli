import type { ClientElement, ClientOutput } from "@assistant-ui/store";
type SingleThreadListProps = {
    thread: ClientElement<"thread">;
};
export declare const SingleThreadList: import("@assistant-ui/tap").Resource<ClientOutput<"threads">, [SingleThreadListProps]>;
export {};