"use client";
import { matchesTriggerItemQuery } from "../primitives/composer/trigger/matchesTriggerItemQuery.js";
import { shallowEqualRecords, useModelContextSnapshot } from "./useModelContextSnapshot.js";
import { useMemo } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { unstable_defaultDirectiveFormatter } from "@assistant-ui/core";
//#region src/unstable/useMentionAdapter.ts
const EMPTY_TOOL_MENTIONS = Object.freeze({});
const toolMentionSource = {
	empty: EMPTY_TOOL_MENTIONS,
	read: (aui) => {
		const tools = aui.thread.getModelContext().tools;
		if (!tools) return EMPTY_TOOL_MENTIONS;
		const mentions = Object.create(null);
		for (const [name, tool] of Object.entries(tools)) mentions[name] = tool.description;
		return mentions;
	},
	subscribe: (aui, onChange) => {
		const unsubscribeContext = aui.on("thread.modelContextUpdate", onChange);
		const unsubscribeSelection = aui.on({
			scope: "*",
			event: "threads.selectionChanged"
		}, onChange);
		return () => {
			unsubscribeContext();
			unsubscribeSelection();
		};
	},
	isEqual: shallowEqualRecords
};
/**
* @deprecated Under active development and might change without notice.
*
* Creates a spreadable `{ adapter, directive }` bundle for `@` mentions.
* Supports tools registered in model context, explicit items, or both —
* flat or categorized.
*
* @example
* ```tsx
* const mention = unstable_useMentionAdapter();
* <ComposerTriggerPopover char="@" {...mention} />
* ```
*/
function unstable_useMentionAdapter(options) {
	const aui = useAui();
	const items = options?.items;
	const categories = options?.categories;
	const includeTools = options?.includeModelContextTools ?? (!items && !categories);
	const toolsConfig = typeof includeTools === "object" ? includeTools : void 0;
	const wantsTools = includeTools !== false;
	const formatter = options?.formatter;
	const onInserted = options?.onInserted;
	const isCategorized = categories !== void 0 || toolsConfig?.category !== void 0 && items === void 0;
	const toolMentions = useModelContextSnapshot(aui, wantsTools, toolMentionSource);
	return {
		adapter: useMemo(() => {
			const formatLabel = toolsConfig?.formatLabel;
			const defaultIcon = toolsConfig?.icon;
			const toolItems = wantsTools ? Object.entries(toolMentions).map(([name, description]) => toTriggerItem({
				id: name,
				type: "tool",
				label: formatLabel ? formatLabel(name) : name,
				description,
				icon: defaultIcon
			})) : [];
			if (isCategorized) {
				const groups = (categories ?? []).map((cat) => ({
					id: cat.id,
					label: cat.label,
					items: cat.items.map(toTriggerItem)
				}));
				const allGroups = toolItems.length > 0 ? [...groups, {
					id: toolsConfig?.category?.id ?? "tools",
					label: toolsConfig?.category?.label ?? "Tools",
					items: toolItems
				}] : groups;
				return {
					categories: () => allGroups.map(({ id, label }) => ({
						id,
						label
					})),
					categoryItems: (id) => allGroups.find((g) => g.id === id)?.items ?? [],
					search: (query) => {
						const lower = query.toLowerCase();
						return allGroups.flatMap((g) => g.items).filter((item) => matchesTriggerItemQuery(item, lower));
					}
				};
			}
			const flatItems = (items ?? []).map(toTriggerItem);
			const seen = new Set(flatItems.map((i) => i.id));
			const flatPool = [...flatItems, ...toolItems.filter((t) => !seen.has(t.id))];
			return {
				categories: () => [],
				categoryItems: () => [],
				search: (query) => {
					const lower = query.toLowerCase();
					return flatPool.filter((item) => matchesTriggerItemQuery(item, lower));
				}
			};
		}, [
			items,
			categories,
			wantsTools,
			toolsConfig,
			isCategorized,
			toolMentions
		]),
		directive: useMemo(() => ({
			formatter: formatter ?? unstable_defaultDirectiveFormatter,
			...onInserted ? { onInserted } : {}
		}), [formatter, onInserted]),
		...options?.iconMap ? { iconMap: options.iconMap } : {},
		...options?.fallbackIcon ? { fallbackIcon: options.fallbackIcon } : {}
	};
}
function toTriggerItem(m) {
	const metadata = m.icon !== void 0 ? {
		...m.metadata ?? {},
		icon: m.icon
	} : m.metadata;
	return {
		id: m.id,
		type: m.type,
		label: m.label,
		...m.description !== void 0 ? { description: m.description } : {},
		...metadata !== void 0 ? { metadata } : {}
	};
}
//#endregion
export { unstable_useMentionAdapter };
