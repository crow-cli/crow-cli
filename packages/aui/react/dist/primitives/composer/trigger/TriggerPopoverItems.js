"use client";
import { Primitive as Primitive$1 } from "../../../utils/Primitive.js";
import { useTriggerPopoverScopeContext } from "./TriggerPopover.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/composer/trigger/TriggerPopoverItems.tsx
/**
* Renders the list of items within a category or search results via a render function.
* Only renders when a category is active or search mode is on.
*/
const ComposerPrimitiveTriggerPopoverItems = forwardRef((t0, forwardedRef) => {
	const $ = c(12);
	let ariaLabel;
	let children;
	let props;
	if ($[0] !== t0) {
		({children, "aria-label": ariaLabel, ...props} = t0);
		$[0] = t0;
		$[1] = ariaLabel;
		$[2] = children;
		$[3] = props;
	} else {
		ariaLabel = $[1];
		children = $[2];
		props = $[3];
	}
	const { items, activeCategoryId, isSearchMode, open } = useTriggerPopoverScopeContext();
	if (!open || !activeCategoryId && !isSearchMode) return null;
	const t1 = ariaLabel ?? "Items";
	let t2;
	if ($[4] !== children || $[5] !== items) {
		t2 = children(items);
		$[4] = children;
		$[5] = items;
		$[6] = t2;
	} else t2 = $[6];
	let t3;
	if ($[7] !== forwardedRef || $[8] !== props || $[9] !== t1 || $[10] !== t2) {
		t3 = /* @__PURE__ */ jsx(Primitive$1.div, {
			role: "group",
			"aria-label": t1,
			...props,
			ref: forwardedRef,
			children: t2
		});
		$[7] = forwardedRef;
		$[8] = props;
		$[9] = t1;
		$[10] = t2;
		$[11] = t3;
	} else t3 = $[11];
	return t3;
});
ComposerPrimitiveTriggerPopoverItems.displayName = "ComposerPrimitive.TriggerPopoverItems";
/**
* A button that selects a trigger item.
* Automatically receives `data-highlighted` when keyboard-navigated.
*/
const ComposerPrimitiveTriggerPopoverItem = forwardRef((t0, forwardedRef) => {
	const $ = c(30);
	let indexProp;
	let item;
	let onClick;
	let onMouseMove;
	let props;
	if ($[0] !== t0) {
		({item, index: indexProp, onClick, onMouseMove, ...props} = t0);
		$[0] = t0;
		$[1] = indexProp;
		$[2] = item;
		$[3] = onClick;
		$[4] = onMouseMove;
		$[5] = props;
	} else {
		indexProp = $[1];
		item = $[2];
		onClick = $[3];
		onMouseMove = $[4];
		props = $[5];
	}
	const { selectItem, highlightIndex, items, highlightedIndex, activeCategoryId, isSearchMode, popoverId } = useTriggerPopoverScopeContext();
	let t1;
	if ($[6] !== item || $[7] !== selectItem) {
		t1 = () => {
			selectItem(item);
		};
		$[6] = item;
		$[7] = selectItem;
		$[8] = t1;
	} else t1 = $[8];
	const handleClick = t1;
	let t2;
	if ($[9] !== indexProp || $[10] !== item.id || $[11] !== items) {
		t2 = indexProp ?? items.findIndex((i) => i.id === item.id);
		$[9] = indexProp;
		$[10] = item.id;
		$[11] = items;
		$[12] = t2;
	} else t2 = $[12];
	const itemIndex = t2;
	const isHighlighted = (isSearchMode || activeCategoryId !== null) && itemIndex === highlightedIndex;
	let t3;
	if ($[13] !== highlightIndex || $[14] !== itemIndex) {
		t3 = () => {
			highlightIndex(itemIndex);
		};
		$[13] = highlightIndex;
		$[14] = itemIndex;
		$[15] = t3;
	} else t3 = $[15];
	const handleMouseMove = t3;
	const t4 = `${popoverId}-option-${item.id}`;
	const t5 = isHighlighted ? "" : void 0;
	let t6;
	if ($[16] !== handleClick || $[17] !== onClick) {
		t6 = composeEventHandlers(onClick, handleClick);
		$[16] = handleClick;
		$[17] = onClick;
		$[18] = t6;
	} else t6 = $[18];
	let t7;
	if ($[19] !== handleMouseMove || $[20] !== onMouseMove) {
		t7 = composeEventHandlers(onMouseMove, handleMouseMove);
		$[19] = handleMouseMove;
		$[20] = onMouseMove;
		$[21] = t7;
	} else t7 = $[21];
	let t8;
	if ($[22] !== forwardedRef || $[23] !== isHighlighted || $[24] !== props || $[25] !== t4 || $[26] !== t5 || $[27] !== t6 || $[28] !== t7) {
		t8 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			role: "option",
			id: t4,
			"aria-selected": isHighlighted,
			"data-highlighted": t5,
			...props,
			ref: forwardedRef,
			onClick: t6,
			onMouseMove: t7
		});
		$[22] = forwardedRef;
		$[23] = isHighlighted;
		$[24] = props;
		$[25] = t4;
		$[26] = t5;
		$[27] = t6;
		$[28] = t7;
		$[29] = t8;
	} else t8 = $[29];
	return t8;
});
ComposerPrimitiveTriggerPopoverItem.displayName = "ComposerPrimitive.TriggerPopoverItem";
//#endregion
export { ComposerPrimitiveTriggerPopoverItem, ComposerPrimitiveTriggerPopoverItems };
