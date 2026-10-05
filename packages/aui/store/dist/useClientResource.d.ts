import { type ResourceElement } from "@assistant-ui/tap";
import type { ClientMethods, InferClientState } from "./types/client.js";
export declare const getClientState: (client: ClientMethods) => any;
export declare const useClientResource: <TMethods extends ClientMethods>(element: ResourceElement<TMethods>) => {
    state: InferClientState<TMethods>;
    methods: TMethods;
    key: string | number | undefined;
};
export declare const ClientResource: <TMethods extends ClientMethods>(element: ResourceElement<TMethods>) => ResourceElement<{
    state: InferClientState<TMethods>;
    methods: TMethods;
    key: string | number | undefined;
}>;