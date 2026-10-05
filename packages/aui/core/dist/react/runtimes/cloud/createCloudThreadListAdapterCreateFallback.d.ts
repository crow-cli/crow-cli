type ThreadData = {
    externalId: string | undefined;
};
type ThreadListItem = {
    source: unknown;
    initialize: () => Promise<ThreadData>;
};
export declare const createCloudThreadListAdapterCreateFallback: (create: (() => Promise<ThreadData>) | undefined, threadListItem: ThreadListItem) => (() => Promise<ThreadData>);
export {};