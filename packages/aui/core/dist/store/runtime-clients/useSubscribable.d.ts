import type { SubscribableWithState } from "../../subscribable/subscribable.js";
export declare const useSubscribable: <T>(subscribable: Omit<SubscribableWithState<T, any>, "path"> & {
    getServerSnapshot?: () => T;
}) => T;