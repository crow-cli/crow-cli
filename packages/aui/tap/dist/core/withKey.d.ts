import type { Resource, ResourceElement } from "./types.js";
export declare function withKey<E extends ResourceElement<any>>(key: string | number, element: E, deps?: readonly unknown[]): E;
export declare function withKey<F extends Resource<any, any[]>>(key: string | number, resource: F): F;