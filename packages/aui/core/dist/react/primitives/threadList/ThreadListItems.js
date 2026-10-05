import { ThreadListItemByIndexProvider } from "../../providers/ThreadListItemByIndexProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/threadList/ThreadListItems.tsx
/**
* Renders a single thread list item at the specified index.
*/
const ThreadListPrimitiveItemByIndex = memo((t0) => {
	const $ = c(6);
	const { index, archived: t1, components } = t0;
	const archived = t1 === void 0 ? false : t1;
	const ThreadListItemComponent = components.ThreadListItem;
	let t2;
	if ($[0] !== ThreadListItemComponent) {
		t2 = /* @__PURE__ */ jsx(ThreadListItemComponent, {});
		$[0] = ThreadListItemComponent;
		$[1] = t2;
	} else t2 = $[1];
	let t3;
	if ($[2] !== archived || $[3] !== index || $[4] !== t2) {
		t3 = /* @__PURE__ */ jsx(ThreadListItemByIndexProvider, {
			index,
			archived,
			children: t2
		});
		$[2] = archived;
		$[3] = index;
		$[4] = t2;
		$[5] = t3;
	} else t3 = $[5];
	return t3;
}, (prev, next) => prev.index === next.index && prev.archived === next.archived && prev.components.ThreadListItem === next.components.ThreadListItem);
ThreadListPrimitiveItemByIndex.displayName = "ThreadListPrimitive.ItemByIndex";
const ThreadListPrimitiveItemsInner = ({ archived, children }) => {
	const threadIds = useAuiState(useShallowSelector((s) => archived ? s.threads.archivedThreadIds : s.threads.threadIds));
	return useMemo(() => threadIds.map((threadId, index) => /* @__PURE__ */ jsx(ThreadListItemByIndexProvider, {
		index,
		archived,
		children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
			getItemState: (aui) => aui.threads.item({
				index,
				archived
			}).getState(),
			children: (getItem) => children({ get threadListItem() {
				return getItem();
			} })
		})
	}, threadId)), [
		threadIds,
		archived,
		children
	]);
};
const ThreadListPrimitiveItems = (t0) => {
	const $ = c(8);
	const { archived: t1, components, children } = t0;
	const archived = t1 === void 0 ? false : t1;
	if (components) {
		const ThreadListItemComponent = components.ThreadListItem;
		let t2;
		if ($[0] !== ThreadListItemComponent) {
			t2 = () => /* @__PURE__ */ jsx(ThreadListItemComponent, {});
			$[0] = ThreadListItemComponent;
			$[1] = t2;
		} else t2 = $[1];
		let t3;
		if ($[2] !== archived || $[3] !== t2) {
			t3 = /* @__PURE__ */ jsx(ThreadListPrimitiveItemsInner, {
				archived,
				children: t2
			});
			$[2] = archived;
			$[3] = t2;
			$[4] = t3;
		} else t3 = $[4];
		return t3;
	}
	let t2;
	if ($[5] !== archived || $[6] !== children) {
		t2 = /* @__PURE__ */ jsx(ThreadListPrimitiveItemsInner, {
			archived,
			children
		});
		$[5] = archived;
		$[6] = children;
		$[7] = t2;
	} else t2 = $[7];
	return t2;
};
ThreadListPrimitiveItems.displayName = "ThreadListPrimitive.Items";
//#endregion
export { ThreadListPrimitiveItemByIndex, ThreadListPrimitiveItems };
