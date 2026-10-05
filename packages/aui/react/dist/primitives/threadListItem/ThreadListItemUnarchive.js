"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useThreadListItemUnarchive } from "@assistant-ui/core/react";
//#region src/primitives/threadListItem/ThreadListItemUnarchive.ts
const useThreadListItemUnarchive$1 = () => {
	const { unarchive } = useThreadListItemUnarchive();
	return unarchive;
};
const ThreadListItemPrimitiveUnarchive = createActionButton("ThreadListItemPrimitive.Unarchive", useThreadListItemUnarchive$1);
//#endregion
export { ThreadListItemPrimitiveUnarchive };
