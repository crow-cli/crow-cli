/**
 * Handles common proxy introspection properties.
 * Returns the appropriate value for toStringTag, toJSON, and props that should return undefined.
 * Returns `false` if the prop should be handled by the subclass.
 */
export declare const handleIntrospectionProp: (prop: string | symbol, name: string) => unknown | false;
export declare abstract class BaseProxyHandler implements ProxyHandler<object> {
    abstract get(_: unknown, prop: string | symbol, receiver?: unknown): unknown;
    abstract ownKeys(): ArrayLike<string | symbol>;
    abstract has(_: unknown, prop: string | symbol): boolean;
    getOwnPropertyDescriptor(_: unknown, prop: string | symbol): {
        value: {} | null;
        writable: boolean;
        enumerable: boolean;
        configurable: boolean;
    } | undefined;
    set(): boolean;
    setPrototypeOf(): boolean;
    defineProperty(): boolean;
    deleteProperty(): boolean;
    preventExtensions(): boolean;
}