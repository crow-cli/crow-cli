import { TriggerDetectionResource } from "./triggerDetectionResource.js";
import { TriggerKeyboardResource } from "./triggerKeyboardResource.js";
import { TriggerNavigationResource } from "./triggerNavigationResource.js";
import { TriggerSelectionResource } from "./triggerSelectionResource.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffectEvent } from "@assistant-ui/tap/react-shim";
import { resource, useResource } from "@assistant-ui/tap";
//#region src/primitives/composer/trigger/TriggerPopoverResource.ts
/** Composes detection, navigation, keyboard, and selection sub-resources. */
const useTriggerPopoverResource = (t0) => {
	const $ = c(47);
	const { adapter, text, triggerChar, matcher, behavior, aui, popoverId, isLoading } = t0;
	let t1;
	if ($[0] !== matcher || $[1] !== text || $[2] !== triggerChar) {
		t1 = TriggerDetectionResource({
			text,
			triggerChar,
			matcher
		});
		$[0] = matcher;
		$[1] = text;
		$[2] = triggerChar;
		$[3] = t1;
	} else t1 = $[3];
	const detection = useResource(t1);
	const open = detection.trigger !== null && adapter !== void 0 && behavior !== void 0;
	let t2;
	if ($[4] !== adapter || $[5] !== detection.query || $[6] !== open) {
		t2 = TriggerNavigationResource({
			adapter,
			query: detection.query,
			open
		});
		$[4] = adapter;
		$[5] = detection.query;
		$[6] = open;
		$[7] = t2;
	} else t2 = $[7];
	const navigation = useResource(t2);
	let t3;
	if ($[8] !== navigation) {
		t3 = () => {
			navigation.goBack();
		};
		$[8] = navigation;
		$[9] = t3;
	} else t3 = $[9];
	const onSelected = useEffectEvent(t3);
	let t4;
	if ($[10] !== aui || $[11] !== behavior || $[12] !== detection.setCursorPosition || $[13] !== detection.trigger || $[14] !== onSelected || $[15] !== triggerChar) {
		t4 = TriggerSelectionResource({
			behavior,
			trigger: detection.trigger,
			aui,
			triggerChar,
			setCursorPosition: detection.setCursorPosition,
			onSelected
		});
		$[10] = aui;
		$[11] = behavior;
		$[12] = detection.setCursorPosition;
		$[13] = detection.trigger;
		$[14] = onSelected;
		$[15] = triggerChar;
		$[16] = t4;
	} else t4 = $[16];
	const selection = useResource(t4);
	let t5;
	if ($[17] !== detection.query || $[18] !== navigation.activeCategoryId || $[19] !== navigation.goBack || $[20] !== navigation.isSearchMode || $[21] !== navigation.navigableList || $[22] !== navigation.selectCategory || $[23] !== open || $[24] !== popoverId || $[25] !== selection.close || $[26] !== selection.selectItem) {
		t5 = TriggerKeyboardResource({
			navigableList: navigation.navigableList,
			isSearchMode: navigation.isSearchMode,
			activeCategoryId: navigation.activeCategoryId,
			query: detection.query,
			popoverId,
			open,
			selectItem: selection.selectItem,
			selectCategory: navigation.selectCategory,
			goBack: navigation.goBack,
			close: selection.close
		});
		$[17] = detection.query;
		$[18] = navigation.activeCategoryId;
		$[19] = navigation.goBack;
		$[20] = navigation.isSearchMode;
		$[21] = navigation.navigableList;
		$[22] = navigation.selectCategory;
		$[23] = open;
		$[24] = popoverId;
		$[25] = selection.close;
		$[26] = selection.selectItem;
		$[27] = t5;
	} else t5 = $[27];
	const keyboard = useResource(t5);
	let t6;
	if ($[28] !== detection.query || $[29] !== detection.setCursorPosition || $[30] !== isLoading || $[31] !== keyboard.handleKeyDown || $[32] !== keyboard.highlightIndex || $[33] !== keyboard.highlightedIndex || $[34] !== keyboard.highlightedItemId || $[35] !== navigation.activeCategoryId || $[36] !== navigation.categories || $[37] !== navigation.goBack || $[38] !== navigation.isSearchMode || $[39] !== navigation.items || $[40] !== navigation.selectCategory || $[41] !== open || $[42] !== popoverId || $[43] !== selection.close || $[44] !== selection.registerSelectItemOverride || $[45] !== selection.selectItem) {
		t6 = {
			open,
			query: detection.query,
			activeCategoryId: navigation.activeCategoryId,
			categories: navigation.categories,
			items: navigation.items,
			highlightedIndex: keyboard.highlightedIndex,
			isSearchMode: navigation.isSearchMode,
			isLoading,
			popoverId,
			highlightedItemId: keyboard.highlightedItemId,
			selectCategory: navigation.selectCategory,
			goBack: navigation.goBack,
			selectItem: selection.selectItem,
			close: selection.close,
			highlightIndex: keyboard.highlightIndex,
			handleKeyDown: keyboard.handleKeyDown,
			setCursorPosition: detection.setCursorPosition,
			registerSelectItemOverride: selection.registerSelectItemOverride
		};
		$[28] = detection.query;
		$[29] = detection.setCursorPosition;
		$[30] = isLoading;
		$[31] = keyboard.handleKeyDown;
		$[32] = keyboard.highlightIndex;
		$[33] = keyboard.highlightedIndex;
		$[34] = keyboard.highlightedItemId;
		$[35] = navigation.activeCategoryId;
		$[36] = navigation.categories;
		$[37] = navigation.goBack;
		$[38] = navigation.isSearchMode;
		$[39] = navigation.items;
		$[40] = navigation.selectCategory;
		$[41] = open;
		$[42] = popoverId;
		$[43] = selection.close;
		$[44] = selection.registerSelectItemOverride;
		$[45] = selection.selectItem;
		$[46] = t6;
	} else t6 = $[46];
	return t6;
};
const TriggerPopoverResource = resource(useTriggerPopoverResource);
//#endregion
export { TriggerPopoverResource };
