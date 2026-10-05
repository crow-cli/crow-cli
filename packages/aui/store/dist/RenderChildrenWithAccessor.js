"use client";
import { useAui } from "./useAui.js";
import { useAuiState } from "./useAuiState.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useMemo, useRef } from "@assistant-ui/tap/react-shim";
//#region src/RenderChildrenWithAccessor.tsx
const useGetItemAccessor = (getItemState) => {
	const aui = useAui();
	const accessedRef = useRef(false);
	const currentValue = accessedRef.current ? null : getItemState(aui);
	useAuiState(() => {
		if (!accessedRef.current) return currentValue;
		return getItemState(aui);
	});
	return () => {
		accessedRef.current = true;
		return getItemState(aui);
	};
};
const EMPTY_OBJECT = Object.freeze({});
/**
* Component that sets up a lazy item accessor and memoizes propless children.
*
* For the common pattern where children returns a component without props
* (e.g. `<Foo />`), the output is memoized and not re-created on parent re-renders.
*
* @example
* ```tsx
* <RenderChildrenWithAccessor
*   getItemState={(aui) => aui.fooList().foo({ index }).getState()}
* >
*   {() => <Foo />}
* </RenderChildrenWithAccessor>
* ```
*/
function RenderChildrenWithAccessor(t0) {
	const $ = c(3);
	const { getItemState, children } = t0;
	const getItem = useGetItemAccessor(getItemState);
	let t1;
	if ($[0] !== children || $[1] !== getItem) {
		t1 = children(getItem);
		$[0] = children;
		$[1] = getItem;
		$[2] = t1;
	} else t1 = $[2];
	return useMemoizedProplessComponent(t1);
}
const useMemoizedProplessComponent = (node) => {
	const el = typeof node === "object" && node != null && "type" in node ? node : null;
	const resultType = el?.type;
	const resultKey = el?.key;
	const resultProps = typeof el?.props === "object" && el.props != null && Object.entries(el.props).length === 0 ? EMPTY_OBJECT : el?.props;
	return useMemo(() => el, [
		resultType,
		resultKey,
		resultProps
	]) ?? node;
};
//#endregion
export { RenderChildrenWithAccessor, useGetItemAccessor };
