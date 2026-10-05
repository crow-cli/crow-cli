import { MEMO_CACHE_SENTINEL, createMemoCache } from "../react-hooks/useMemoCache.js";
import React, { useMemo } from "react";
//#region src/react-shim/useReactMemoCache.ts
const ReactRuntime = React;
const useReactMemoCacheShim = (size) => useMemo(() => {
	const $ = createMemoCache(size);
	$[MEMO_CACHE_SENTINEL] = true;
	return $;
}, []);
const reactC = ReactRuntime.__COMPILER_RUNTIME?.c ?? useReactMemoCacheShim;
//#endregion
export { reactC, useReactMemoCacheShim };
