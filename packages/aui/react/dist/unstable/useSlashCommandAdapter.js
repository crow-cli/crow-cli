"use client";
import { matchesTriggerItemQuery } from "../primitives/composer/trigger/matchesTriggerItemQuery.js";
import { useLayoutEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
//#region src/unstable/useSlashCommandAdapter.ts
/**
* @deprecated Under active development and may change without notice.
*
* Bundles slash command definitions (with inline `execute` callbacks) into
* `{adapter, action}` that plug directly into `ComposerTriggerPopover`.
* `execute` stays in the hook closure and is never attached to the returned
* `TriggerItem`, keeping items serializable.
*
* @example
* ```tsx
* const slash = unstable_useSlashCommandAdapter({
*   commands: [
*     { id: "summarize", execute: () => runSummarize(), icon: "FileText" },
*     { id: "translate", execute: () => runTranslate(), icon: "Languages" },
*   ],
* });
*
* <ComposerTriggerPopover char="/" {...slash} />
* ```
*/
function unstable_useSlashCommandAdapter(options) {
	const { commands, removeOnExecute } = options;
	const commandsRef = useRef(commands);
	const committedItemsRef = useRef(void 0);
	const nextItems = commands.map(toItem);
	const items = areTriggerItemsEqual(committedItemsRef.current, nextItems) ? committedItemsRef.current : nextItems;
	useLayoutEffect(() => {
		commandsRef.current = commands;
		committedItemsRef.current = items;
	}, [commands, items]);
	const adapter = useMemo(() => ({
		categories: () => [],
		categoryItems: () => [],
		search: (query) => {
			const lower = query.toLowerCase();
			return items.filter((item) => matchesTriggerItemQuery(item, lower));
		}
	}), [items]);
	const action = useMemo(() => ({
		onExecute: (item) => {
			commandsRef.current.find((c) => c.id === item.id)?.execute();
		},
		...removeOnExecute !== void 0 ? { removeOnExecute } : {}
	}), [removeOnExecute]);
	return useMemo(() => ({
		adapter,
		action,
		...options.iconMap ? { iconMap: options.iconMap } : {},
		...options.fallbackIcon ? { fallbackIcon: options.fallbackIcon } : {}
	}), [
		adapter,
		action,
		options.iconMap,
		options.fallbackIcon
	]);
}
function toItem(cmd) {
	return {
		id: cmd.id,
		type: "command",
		label: cmd.label ?? `/${cmd.id}`,
		...cmd.description !== void 0 ? { description: cmd.description } : {},
		...cmd.icon !== void 0 ? { metadata: { icon: cmd.icon } } : {}
	};
}
function areTriggerItemsEqual(previous, next) {
	if (!previous || previous.length !== next.length) return false;
	return previous.every((item, index) => {
		const nextItem = next[index];
		return nextItem !== void 0 && item.id === nextItem.id && item.label === nextItem.label && item.description === nextItem.description && item.metadata?.icon === nextItem.metadata?.icon;
	});
}
//#endregion
export { unstable_useSlashCommandAdapter };
