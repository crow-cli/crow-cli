"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useThreadListItemDelete } from "@assistant-ui/core/react";
//#region src/primitives/threadListItem/ThreadListItemDelete.ts
const useThreadListItemDelete$1 = () => {
	const { delete: deleteThread } = useThreadListItemDelete();
	return deleteThread;
};
const ThreadListItemPrimitiveDelete = createActionButton("ThreadListItemPrimitive.Delete", useThreadListItemDelete$1);
//#endregion
export { ThreadListItemPrimitiveDelete };
