"use client";
import { Primitive as Primitive$1 } from "../../../utils/Primitive.js";
import { useTriggerPopoverScopeContext } from "./TriggerPopover.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/composer/trigger/TriggerPopoverCategories.tsx
/**
* Renders the top-level category list via a render function.
* Only renders when no category is active and search mode is off.
*/
const ComposerPrimitiveTriggerPopoverCategories = forwardRef((t0, forwardedRef) => {
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
	const { categories, activeCategoryId, isSearchMode, open } = useTriggerPopoverScopeContext();
	if (!open || activeCategoryId || isSearchMode) return null;
	const t1 = ariaLabel ?? "Categories";
	let t2;
	if ($[4] !== categories || $[5] !== children) {
		t2 = children(categories);
		$[4] = categories;
		$[5] = children;
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
ComposerPrimitiveTriggerPopoverCategories.displayName = "ComposerPrimitive.TriggerPopoverCategories";
/**
* A button that selects a category and triggers drill-down navigation.
* Automatically receives `data-highlighted` when keyboard-navigated.
*/
const ComposerPrimitiveTriggerPopoverCategoryItem = forwardRef((t0, forwardedRef) => {
	const $ = c(30);
	let categoryId;
	let onClick;
	let onMouseMove;
	let props;
	if ($[0] !== t0) {
		({categoryId, onClick, onMouseMove, ...props} = t0);
		$[0] = t0;
		$[1] = categoryId;
		$[2] = onClick;
		$[3] = onMouseMove;
		$[4] = props;
	} else {
		categoryId = $[1];
		onClick = $[2];
		onMouseMove = $[3];
		props = $[4];
	}
	const { selectCategory, highlightIndex, categories, highlightedIndex, activeCategoryId, isSearchMode, popoverId } = useTriggerPopoverScopeContext();
	let t1;
	if ($[5] !== categoryId || $[6] !== selectCategory) {
		t1 = () => {
			selectCategory(categoryId);
		};
		$[5] = categoryId;
		$[6] = selectCategory;
		$[7] = t1;
	} else t1 = $[7];
	const handleClick = t1;
	let t2;
	if ($[8] !== categories || $[9] !== categoryId) {
		let t3;
		if ($[11] !== categoryId) {
			t3 = (c) => c.id === categoryId;
			$[11] = categoryId;
			$[12] = t3;
		} else t3 = $[12];
		t2 = categories.findIndex(t3);
		$[8] = categories;
		$[9] = categoryId;
		$[10] = t2;
	} else t2 = $[10];
	const categoryIndex = t2;
	const isHighlighted = !activeCategoryId && !isSearchMode && categoryIndex === highlightedIndex;
	let t3;
	if ($[13] !== categoryIndex || $[14] !== highlightIndex) {
		t3 = () => {
			highlightIndex(categoryIndex);
		};
		$[13] = categoryIndex;
		$[14] = highlightIndex;
		$[15] = t3;
	} else t3 = $[15];
	const handleMouseMove = t3;
	const t4 = `${popoverId}-option-${categoryId}`;
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
ComposerPrimitiveTriggerPopoverCategoryItem.displayName = "ComposerPrimitive.TriggerPopoverCategoryItem";
//#endregion
export { ComposerPrimitiveTriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem };
