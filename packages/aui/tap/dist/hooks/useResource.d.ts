import type { ExtractResourceReturnType, ResourceElement } from "../core/types.js";
export declare function useResource<E extends ResourceElement<any>>(element: E): ExtractResourceReturnType<E>;