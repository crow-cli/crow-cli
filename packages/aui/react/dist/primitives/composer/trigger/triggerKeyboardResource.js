import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffectEvent, useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/primitives/composer/trigger/triggerKeyboardResource.ts
/** Relies on `Unstable_TriggerCategory` never carrying a `type` field. */
function isTriggerItem(x) {
	return "type" in x;
}
/**
* Owns keyboard-driven highlight state for the popover. Delegates selection,
* category drill-in, back, and close to the callbacks supplied by the parent.
*/
const useTriggerKeyboardResource = (t0) => {
	const $ = c(22);
	const { navigableList, isSearchMode, activeCategoryId, query, popoverId, open, selectItem, selectCategory, goBack, close } = t0;
	const [highlightedIndex, setHighlightedIndex] = useState(0);
	let t1;
	if ($[0] !== activeCategoryId || $[1] !== isSearchMode || $[2] !== navigableList) {
		t1 = {
			navigableList,
			isSearchMode,
			activeCategoryId
		};
		$[0] = activeCategoryId;
		$[1] = isSearchMode;
		$[2] = navigableList;
		$[3] = t1;
	} else t1 = $[3];
	const [highlightScope, setHighlightScope] = useState(t1);
	if (highlightScope.navigableList !== navigableList || highlightScope.isSearchMode !== isSearchMode || highlightScope.activeCategoryId !== activeCategoryId) {
		setHighlightScope({
			navigableList,
			isSearchMode,
			activeCategoryId
		});
		setHighlightedIndex(0);
	}
	let t2;
	if ($[4] !== highlightedIndex || $[5] !== navigableList.length) {
		t2 = (index) => {
			if (index < 0 || index >= navigableList.length) return;
			if (index === highlightedIndex) return;
			setHighlightedIndex(index);
		};
		$[4] = highlightedIndex;
		$[5] = navigableList.length;
		$[6] = t2;
	} else t2 = $[6];
	const highlightIndex = useEffectEvent(t2);
	let t3;
	if ($[7] !== activeCategoryId || $[8] !== close || $[9] !== goBack || $[10] !== highlightedIndex || $[11] !== navigableList || $[12] !== open || $[13] !== query || $[14] !== selectCategory || $[15] !== selectItem) {
		t3 = (e) => {
			if (!open) return false;
			switch (e.key) {
				case "ArrowDown":
					e.preventDefault();
					setHighlightedIndex((prev_0) => {
						const len_0 = navigableList.length;
						if (len_0 === 0) return 0;
						return prev_0 < len_0 - 1 ? prev_0 + 1 : 0;
					});
					return true;
				case "ArrowUp":
					e.preventDefault();
					setHighlightedIndex((prev) => {
						const len = navigableList.length;
						if (len === 0) return 0;
						return prev > 0 ? prev - 1 : len - 1;
					});
					return true;
				case "Enter":
				case "Tab": {
					if (e.shiftKey) return false;
					e.preventDefault();
					const item = navigableList[highlightedIndex];
					if (!item) return true;
					if (isTriggerItem(item)) selectItem(item);
					else selectCategory(item.id);
					return true;
				}
				case "Escape":
					e.preventDefault();
					close();
					return true;
				case "Backspace":
					if (activeCategoryId && query === "") {
						e.preventDefault();
						goBack();
						return true;
					}
					return false;
				default: return false;
			}
		};
		$[7] = activeCategoryId;
		$[8] = close;
		$[9] = goBack;
		$[10] = highlightedIndex;
		$[11] = navigableList;
		$[12] = open;
		$[13] = query;
		$[14] = selectCategory;
		$[15] = selectItem;
		$[16] = t3;
	} else t3 = $[16];
	const handleKeyDown = useEffectEvent(t3);
	const highlightedEntry = navigableList[highlightedIndex];
	const highlightedItemId = open && highlightedEntry ? `${popoverId}-option-${highlightedEntry.id}` : void 0;
	let t4;
	if ($[17] !== handleKeyDown || $[18] !== highlightIndex || $[19] !== highlightedIndex || $[20] !== highlightedItemId) {
		t4 = {
			highlightedIndex,
			highlightedItemId,
			highlightIndex,
			handleKeyDown
		};
		$[17] = handleKeyDown;
		$[18] = highlightIndex;
		$[19] = highlightedIndex;
		$[20] = highlightedItemId;
		$[21] = t4;
	} else t4 = $[21];
	return t4;
};
const TriggerKeyboardResource = resource(useTriggerKeyboardResource);
//#endregion
export { TriggerKeyboardResource };
