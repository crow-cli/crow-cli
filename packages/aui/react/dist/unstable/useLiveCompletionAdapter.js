"use client";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/unstable/useLiveCompletionAdapter.ts
/** Sentinel that no real query (including the empty string) equals, so the first query always fetches. */
const NO_QUERY = "\0";
/**
* @deprecated Under active development and may change without notice.
*
* Bridges an async completion source (a server search, a gateway RPC) into the
* synchronous `Unstable_TriggerAdapter` that `ComposerTriggerPopover` consumes.
* `search(query)` returns the last fetched items synchronously and schedules a
* debounced fetch when the query changes; when results arrive the returned
* `adapter` identity changes, which re-runs the popover's lookup so the fresh
* items render. This is a search-only adapter (`categories` are empty).
*
* `isLoading` is `true` while a fetch is in flight. Pass it to the popover's
* `isLoading` prop to render a loading state.
*
* @example
* ```tsx
* const mentions = unstable_useLiveCompletionAdapter({
*   fetcher: (query) => searchUsers(query),
* });
*
* <ComposerTriggerPopover
*   char="@"
*   adapter={mentions.adapter}
*   isLoading={mentions.isLoading}
*   directive={{ onInserted }}
* />
* ```
*/
function unstable_useLiveCompletionAdapter(options) {
	const { fetcher, cacheKey, debounceMs = 60, enabled = true } = options;
	const [state, setState] = useState({
		query: NO_QUERY,
		items: [],
		failed: false
	});
	const [isLoading, setIsLoading] = useState(false);
	const fetcherRef = useRef(fetcher);
	useLayoutEffect(() => {
		fetcherRef.current = fetcher;
	}, [fetcher]);
	const timerRef = useRef(null);
	const tokenRef = useRef(0);
	const pendingQueryRef = useRef(null);
	const retryableQueryRef = useRef(null);
	const pendingRetryQueryRef = useRef(null);
	const inactiveRef = useRef(true);
	const deferredQueryRef = useRef(null);
	const cancelTimer = useCallback(() => {
		if (timerRef.current !== null) {
			clearTimeout(timerRef.current);
			timerRef.current = null;
		}
	}, []);
	const rearmPendingRetry = useCallback(() => {
		const query = pendingRetryQueryRef.current;
		if (query === null) return;
		retryableQueryRef.current = query;
		pendingRetryQueryRef.current = null;
	}, []);
	const scheduleFetch = useCallback((query) => {
		if (!enabled) return;
		if (inactiveRef.current) {
			deferredQueryRef.current = query;
			return;
		}
		if (pendingQueryRef.current === query) return;
		rearmPendingRetry();
		if (retryableQueryRef.current === query) {
			retryableQueryRef.current = null;
			pendingRetryQueryRef.current = query;
		}
		pendingQueryRef.current = query;
		cancelTimer();
		const token = ++tokenRef.current;
		setIsLoading(true);
		timerRef.current = setTimeout(() => {
			timerRef.current = null;
			Promise.resolve().then(() => fetcherRef.current(query)).then((items) => {
				if (token !== tokenRef.current) return;
				pendingRetryQueryRef.current = null;
				setState({
					query,
					items,
					failed: false
				});
				setIsLoading(false);
			}, () => {
				if (token !== tokenRef.current) return;
				pendingQueryRef.current = null;
				pendingRetryQueryRef.current = null;
				setState({
					query,
					items: [],
					failed: true
				});
				setIsLoading(false);
			});
		}, debounceMs);
	}, [
		enabled,
		debounceMs,
		cancelTimer,
		rearmPendingRetry
	]);
	const scheduleFetchRef = useRef(scheduleFetch);
	useLayoutEffect(() => {
		scheduleFetchRef.current = scheduleFetch;
	}, [scheduleFetch]);
	const invalidatePending = useCallback(() => {
		rearmPendingRetry();
		cancelTimer();
		pendingQueryRef.current = null;
		tokenRef.current += 1;
		setIsLoading(false);
	}, [cancelTimer, rearmPendingRetry]);
	const cacheKeyRef = useRef(cacheKey);
	useLayoutEffect(() => {
		if (cacheKeyRef.current === cacheKey) return;
		cacheKeyRef.current = cacheKey;
		invalidatePending();
		retryableQueryRef.current = null;
		pendingRetryQueryRef.current = null;
		setState({
			query: NO_QUERY,
			items: [],
			failed: false
		});
	}, [cacheKey, invalidatePending]);
	useEffect(() => {
		if (enabled) return;
		invalidatePending();
		setState((s) => s.query === NO_QUERY ? s : {
			query: NO_QUERY,
			items: [],
			failed: false
		});
	}, [enabled, invalidatePending]);
	useLayoutEffect(() => {
		inactiveRef.current = false;
		const deferredQuery = deferredQueryRef.current;
		deferredQueryRef.current = null;
		if (deferredQuery !== null) scheduleFetchRef.current(deferredQuery);
		return () => {
			inactiveRef.current = true;
			invalidatePending();
		};
	}, [invalidatePending]);
	useEffect(() => {
		retryableQueryRef.current = state.failed ? state.query : null;
	}, [state]);
	return {
		adapter: useMemo(() => ({
			categories: () => [],
			categoryItems: () => [],
			search: (query) => {
				if (query !== state.query || retryableQueryRef.current === query) queueMicrotask(() => scheduleFetch(query));
				else queueMicrotask(() => {
					if (deferredQueryRef.current !== null && deferredQueryRef.current !== query) deferredQueryRef.current = null;
					if (pendingQueryRef.current !== null && pendingQueryRef.current !== query) invalidatePending();
				});
				return state.items;
			}
		}), [
			state,
			scheduleFetch,
			invalidatePending
		]),
		isLoading
	};
}
//#endregion
export { unstable_useLiveCompletionAdapter };
