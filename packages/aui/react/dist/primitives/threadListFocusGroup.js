"use client";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
import { Collection } from "radix-ui/internal";
//#region src/primitives/threadListFocusGroup.ts
const [collection, useThreadListCollection] = Collection.createCollection("ThreadList");
const ThreadListCollection = collection;
const ThreadListItemFocusContext = createContext(null);
const ThreadListItemFocusProvider = ThreadListItemFocusContext.Provider;
const useThreadListItemFocus = () => {
	return useContext(ThreadListItemFocusContext);
};
//#endregion
export { ThreadListCollection, ThreadListItemFocusProvider, useThreadListCollection, useThreadListItemFocus };
