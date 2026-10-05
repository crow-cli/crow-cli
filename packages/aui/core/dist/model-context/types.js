import { nullProtoRecord } from "../utils/record.js";
//#region src/model-context/types.ts
const stripOverwrite = (tool) => {
	if (!tool.overwrite) return tool;
	const { overwrite: _, ...rest } = tool;
	return rest;
};
const mergeModelContexts = (configSet) => {
	const configs = Array.from(configSet).map((c) => c.getModelContext()).sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
	const toolPriorities = nullProtoRecord();
	return configs.reduce((acc, config) => {
		const priority = config.priority ?? 0;
		if (config.system) {
			if (acc.system) acc.system += `\n\n${config.system}`;
			else acc.system = config.system;
		}
		if (config.tools) for (const [name, tool] of Object.entries(config.tools)) {
			const existing = acc.tools !== void 0 && Object.hasOwn(acc.tools, name) ? acc.tools[name] : void 0;
			if (existing && existing !== tool) {
				const existingPriority = toolPriorities[name];
				if (existingPriority === priority) {
					if (!tool.overwrite) throw new Error(`You tried to define a tool with the name ${name}, but it already exists.`);
					acc.tools[name] = stripOverwrite(tool);
					continue;
				}
				const higherPriorityTool = existingPriority > priority ? existing : tool;
				const lowerPriorityTool = existingPriority > priority ? tool : existing;
				acc.tools[name] = stripOverwrite({
					...lowerPriorityTool,
					...higherPriorityTool
				});
				toolPriorities[name] = Math.max(existingPriority, priority);
				continue;
			}
			if (!acc.tools) acc.tools = nullProtoRecord();
			acc.tools[name] = stripOverwrite(tool);
			if (!Object.hasOwn(toolPriorities, name)) toolPriorities[name] = priority;
		}
		if (config.config) acc.config = {
			...config.config,
			...acc.config
		};
		if (config.callSettings) acc.callSettings = {
			...config.callSettings,
			...acc.callSettings
		};
		if (config.unstable_composerMetadata) acc.unstable_composerMetadata = {
			...config.unstable_composerMetadata,
			...acc.unstable_composerMetadata
		};
		return acc;
	}, {});
};
//#endregion
export { mergeModelContexts };
