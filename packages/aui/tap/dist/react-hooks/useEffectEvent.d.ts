/**
 * Creates a stable function reference that always calls the most recent version of the callback.
 * Similar to React's useEffectEvent hook.
 *
 * @param callback - The callback function to wrap
 * @returns A stable function reference that always calls the latest callback
 *
 * @example
 * ```typescript
 * const handleClick = useEffectEvent((value: string) => {
 *   console.log(value);
 * });
 * // handleClick reference is stable, but always calls the latest version
 * ```
 */
export declare function useEffectEvent<T extends (...args: any[]) => any>(callback: T): T;