import { type Resource } from "@assistant-ui/tap";
import type { ClientMethods, InferClientState } from "./types/client.js";
export declare const useClientList: <TData, TMethods extends ClientMethods>(props: useClientList.Props<TData, TMethods>) => {
    state: InferClientState<TMethods>[];
    get: (lookup: {
        index: number;
    } | {
        key: string;
    }) => TMethods;
    add: (initialData: TData) => void;
};
export declare namespace useClientList {
    type ResourceProps<TData> = {
        key: string;
        getInitialData: () => TData;
        remove: () => void;
    };
    type Props<TData, TMethods extends ClientMethods> = {
        initialValues: TData[];
        getKey: (data: TData) => string;
        resource: Resource<TMethods, [ResourceProps<TData>]>;
    };
}