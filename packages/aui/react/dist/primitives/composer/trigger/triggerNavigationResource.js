import { matchesTriggerItemQuery } from "./matchesTriggerItemQuery.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffectEvent, useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/primitives/composer/trigger/triggerNavigationResource.ts
/**
* Computes categories, items, search results, and navigation state from the
* adapter + current query. Pure derivation — no side effects on the composer.
*/
const useTriggerNavigationResource = (t0) => {
	const $ = c(35);
	const { adapter, query, open } = t0;
	const [activeCategoryId, setActiveCategoryId] = useState(null);
	const [wasOpen, setWasOpen] = useState(open);
	if (wasOpen !== open) {
		setWasOpen(open);
		if (!open) setActiveCategoryId(null);
	}
	let t1;
	bb0: {
		if (!open || !adapter) {
			let t2;
			if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
				t2 = [];
				$[0] = t2;
			} else t2 = $[0];
			t1 = t2;
			break bb0;
		}
		let t2;
		if ($[1] !== adapter) {
			t2 = adapter.categories();
			$[1] = adapter;
			$[2] = t2;
		} else t2 = $[2];
		t1 = t2;
	}
	const categories = t1;
	const effectiveActiveCategoryId = open ? activeCategoryId : null;
	let t2;
	bb1: {
		if (!effectiveActiveCategoryId || !adapter) {
			let t3;
			if ($[3] === Symbol.for("react.memo_cache_sentinel")) {
				t3 = [];
				$[3] = t3;
			} else t3 = $[3];
			t2 = t3;
			break bb1;
		}
		let t3;
		if ($[4] !== adapter || $[5] !== effectiveActiveCategoryId) {
			t3 = adapter.categoryItems(effectiveActiveCategoryId);
			$[4] = adapter;
			$[5] = effectiveActiveCategoryId;
			$[6] = t3;
		} else t3 = $[6];
		t2 = t3;
	}
	const allItems = t2;
	let t3;
	bb2: {
		if (!open || !adapter || effectiveActiveCategoryId) {
			t3 = null;
			break bb2;
		}
		if (!query && categories.length > 0) {
			t3 = null;
			break bb2;
		}
		if (adapter.search) {
			let t4;
			if ($[7] !== adapter || $[8] !== query) {
				t4 = adapter.search(query);
				$[7] = adapter;
				$[8] = query;
				$[9] = t4;
			} else t4 = $[9];
			t3 = t4;
			break bb2;
		}
		let all;
		if ($[10] !== adapter || $[11] !== categories || $[12] !== query) {
			all = [];
			const lower = query.toLowerCase();
			for (const cat of categories) for (const item of adapter.categoryItems(cat.id)) if (matchesTriggerItemQuery(item, lower)) all.push(item);
			$[10] = adapter;
			$[11] = categories;
			$[12] = query;
			$[13] = all;
		} else all = $[13];
		t3 = all;
	}
	const searchResults = t3;
	const isSearchMode = searchResults !== null;
	let t4;
	bb3: {
		if (isSearchMode) {
			let t5;
			if ($[14] === Symbol.for("react.memo_cache_sentinel")) {
				t5 = [];
				$[14] = t5;
			} else t5 = $[14];
			t4 = t5;
			break bb3;
		}
		if (!query) {
			t4 = categories;
			break bb3;
		}
		let t5;
		if ($[15] !== categories || $[16] !== query) {
			const lower_0 = query.toLowerCase();
			t5 = categories.filter((cat_0) => cat_0.label.toLowerCase().includes(lower_0));
			$[15] = categories;
			$[16] = query;
			$[17] = t5;
		} else t5 = $[17];
		t4 = t5;
	}
	const filteredCategories = t4;
	let t5;
	bb4: {
		if (isSearchMode) {
			let t6;
			if ($[18] !== searchResults) {
				t6 = searchResults ?? [];
				$[18] = searchResults;
				$[19] = t6;
			} else t6 = $[19];
			t5 = t6;
			break bb4;
		}
		if (!query) {
			t5 = allItems;
			break bb4;
		}
		let t6;
		if ($[20] !== allItems || $[21] !== query) {
			const lower_1 = query.toLowerCase();
			t6 = allItems.filter((item_0) => matchesTriggerItemQuery(item_0, lower_1));
			$[20] = allItems;
			$[21] = query;
			$[22] = t6;
		} else t6 = $[22];
		t5 = t6;
	}
	const filteredItems = t5;
	let t6;
	bb5: {
		if (isSearchMode) {
			let t7;
			if ($[23] !== searchResults) {
				t7 = searchResults ?? [];
				$[23] = searchResults;
				$[24] = t7;
			} else t7 = $[24];
			t6 = t7;
			break bb5;
		}
		if (effectiveActiveCategoryId) {
			t6 = filteredItems;
			break bb5;
		}
		t6 = filteredCategories;
	}
	const navigableList = t6;
	let t7;
	if ($[25] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = (categoryId) => {
			setActiveCategoryId(categoryId);
		};
		$[25] = t7;
	} else t7 = $[25];
	const selectCategory = useEffectEvent(t7);
	let t8;
	if ($[26] === Symbol.for("react.memo_cache_sentinel")) {
		t8 = () => {
			setActiveCategoryId(null);
		};
		$[26] = t8;
	} else t8 = $[26];
	const goBack = useEffectEvent(t8);
	let t9;
	if ($[27] !== effectiveActiveCategoryId || $[28] !== filteredCategories || $[29] !== filteredItems || $[30] !== goBack || $[31] !== isSearchMode || $[32] !== navigableList || $[33] !== selectCategory) {
		t9 = {
			categories: filteredCategories,
			items: filteredItems,
			isSearchMode,
			activeCategoryId: effectiveActiveCategoryId,
			navigableList,
			selectCategory,
			goBack
		};
		$[27] = effectiveActiveCategoryId;
		$[28] = filteredCategories;
		$[29] = filteredItems;
		$[30] = goBack;
		$[31] = isSearchMode;
		$[32] = navigableList;
		$[33] = selectCategory;
		$[34] = t9;
	} else t9 = $[34];
	return t9;
};
const TriggerNavigationResource = resource(useTriggerNavigationResource);
//#endregion
export { TriggerNavigationResource };
