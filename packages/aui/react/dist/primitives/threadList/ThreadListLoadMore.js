"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useThreadListLoadMore } from "@assistant-ui/core/react";
//#region src/primitives/threadList/ThreadListLoadMore.tsx
const useThreadListLoadMore$1 = () => {
	const { loadMore, disabled } = useThreadListLoadMore();
	if (disabled) return null;
	return loadMore;
};
const ThreadListPrimitiveLoadMore = createActionButton("ThreadListPrimitive.LoadMore", useThreadListLoadMore$1);
//#endregion
export { ThreadListPrimitiveLoadMore };
