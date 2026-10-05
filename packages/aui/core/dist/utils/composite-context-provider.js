import { mergeModelContexts } from "../model-context/types.js";
import { notifySubscribers } from "../subscribable/subscribable.js";
//#region src/utils/composite-context-provider.ts
var CompositeContextProvider = class {
	_providers = /* @__PURE__ */ new Map();
	_providerUnsubscribes = /* @__PURE__ */ new Map();
	getModelContext() {
		return mergeModelContexts(new Set(this._providers.values()));
	}
	registerModelContextProvider(provider) {
		const id = Symbol();
		this._providers.set(id, provider);
		let unsubscribe;
		try {
			unsubscribe = provider.subscribe?.(() => {
				this.notifySubscribers();
			});
		} catch (error) {
			this._providers.delete(id);
			try {
				this.notifySubscribers();
			} catch (notifyError) {
				console.error(notifyError);
			}
			throw error;
		}
		this._providerUnsubscribes.set(id, unsubscribe);
		this.notifySubscribers();
		let released = false;
		return () => {
			if (released) return;
			released = true;
			this._providers.delete(id);
			const unsubscribe = this._providerUnsubscribes.get(id);
			this._providerUnsubscribes.delete(id);
			let cleanupFailed = false;
			let cleanupError;
			const runCleanup = (cleanup) => {
				try {
					cleanup();
				} catch (error) {
					if (cleanupFailed) console.error(error);
					else {
						cleanupFailed = true;
						cleanupError = error;
					}
				}
			};
			if (unsubscribe) runCleanup(unsubscribe);
			runCleanup(() => this.notifySubscribers());
			if (cleanupFailed) throw cleanupError;
		};
	}
	_subscribers = /* @__PURE__ */ new Set();
	notifySubscribers() {
		notifySubscribers(this._subscribers);
	}
	subscribe(callback) {
		this._subscribers.add(callback);
		return () => {
			this._subscribers.delete(callback);
		};
	}
};
//#endregion
export { CompositeContextProvider };
