"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useThreadListItemArchive } from "@assistant-ui/core/react";
//#region src/primitives/threadListItem/ThreadListItemArchive.ts
const useThreadListItemArchive$1 = () => {
	const { archive } = useThreadListItemArchive();
	return archive;
};
const ThreadListItemPrimitiveArchive = createActionButton("ThreadListItemPrimitive.Archive", useThreadListItemArchive$1);
//#endregion
export { ThreadListItemPrimitiveArchive };
