export declare const openAbortableIterable: <T>(source: AsyncIterable<T> | Promise<AsyncIterable<T>>, signal: AbortSignal) => Promise<AsyncIterable<T> | undefined>;
/**
 * Presents a stream as exhausted once the signal aborts, so a consumer stops
 * waiting on it.
 *
 * A caller's stream is free to ignore the abort signal it is handed. One that
 * also stops yielding, because it is awaiting its own work, leaves `for await`
 * parked on `next()` with nothing left to wake it: the run never settles and
 * whatever is serialized behind it never starts. Reporting the stream as
 * exhausted ends the loop at cancellation instead.
 *
 * The source is finalized on the way out, but never awaited, since a stream
 * that is already parked would not settle that either.
 */
export declare const abortableIterable: <T>(source: AsyncIterable<T>, signal: AbortSignal) => AsyncIterable<T>;