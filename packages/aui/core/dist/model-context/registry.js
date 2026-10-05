import { nullProtoRecord } from "../utils/record.js";
import { notifySubscribers } from "../subscribable/subscribable.js";
import { CompositeContextProvider } from "../utils/composite-context-provider.js";
//#region src/model-context/registry.ts
var ModelContextRegistry = class {
	_tools = /* @__PURE__ */ new Map();
	_instructions = /* @__PURE__ */ new Map();
	_contextProviders = new CompositeContextProvider();
	_subscribers = /* @__PURE__ */ new Set();
	constructor() {
		this._contextProviders.subscribe(() => {
			this.notifySubscribers();
		});
	}
	getModelContext() {
		const instructions = Array.from(this._instructions.values()).filter(Boolean);
		const system = instructions.length > 0 ? instructions.join("\n\n") : void 0;
		const tools = nullProtoRecord();
		for (const toolProps of this._tools.values()) {
			const { toolName, render, ...tool } = toolProps;
			tools[toolName] = tool;
		}
		const providerContexts = this._contextProviders.getModelContext();
		const context = {
			system,
			tools: Object.keys(tools).length > 0 ? tools : void 0
		};
		if (providerContexts.system) context.system = context.system ? `${context.system}\n\n${providerContexts.system}` : providerContexts.system;
		if (providerContexts.tools) context.tools = nullProtoRecord(context.tools, providerContexts.tools);
		if (providerContexts.callSettings) context.callSettings = providerContexts.callSettings;
		if (providerContexts.config) context.config = providerContexts.config;
		if (providerContexts.unstable_composerMetadata) context.unstable_composerMetadata = providerContexts.unstable_composerMetadata;
		return context;
	}
	subscribe(callback) {
		this._subscribers.add(callback);
		return () => this._subscribers.delete(callback);
	}
	notifySubscribers() {
		notifySubscribers(this._subscribers);
	}
	addTool(tool) {
		const id = Symbol();
		this._tools.set(id, tool);
		this.notifySubscribers();
		return {
			update: (newTool) => {
				if (this._tools.has(id)) {
					this._tools.set(id, newTool);
					this.notifySubscribers();
				}
			},
			remove: () => {
				this._tools.delete(id);
				this.notifySubscribers();
			}
		};
	}
	addInstruction(config) {
		const id = Symbol();
		const instruction = typeof config === "string" ? config : config.instruction;
		if (!(typeof config === "object" ? config.disabled : false)) {
			this._instructions.set(id, instruction);
			this.notifySubscribers();
		}
		return {
			update: (newConfig) => {
				const newInstruction = typeof newConfig === "string" ? newConfig : newConfig.instruction;
				if (typeof newConfig === "object" ? newConfig.disabled : false) this._instructions.delete(id);
				else this._instructions.set(id, newInstruction);
				this.notifySubscribers();
			},
			remove: () => {
				this._instructions.delete(id);
				this.notifySubscribers();
			}
		};
	}
	addProvider(provider) {
		return { remove: this._contextProviders.registerModelContextProvider(provider) };
	}
};
//#endregion
export { ModelContextRegistry };
