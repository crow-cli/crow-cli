/**
 * Builds a dictionary with no prototype from the own entries of its arguments.
 * Bracket assignment on a plain object routes a `__proto__` key through the
 * `Object.prototype` setter instead of defining an own property, so a record
 * assigned into by a key the app does not control is built this way.
 */
export declare const nullProtoRecord: <T>(base?: Readonly<Record<string, T>>, ...rest: readonly (Readonly<Record<string, NoInfer<T>>> | undefined)[]) => Record<string, T>;