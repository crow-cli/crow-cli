import { notifyEventListeners } from "../utils/notify-event-listeners.js";
import { shallowEqual } from "@assistant-ui/store/client";
//#region src/subscribable/subscribable.ts
const SKIP_UPDATE = Symbol("skip-update");
const notifySubscribers = (subscribers, ...args) => {
	const errors = [];
	for (const callback of subscribers) try {
		callback(...args);
	} catch (error) {
		errors.push(error);
	}
	if (errors.length === 1) throw errors[0];
	if (errors.length > 1) {
		for (const error of errors) console.error(error);
		throw new AggregateError(errors);
	}
};
const runCleanups = (cleanups) => {
	notifySubscribers(cleanups);
};
const rollbackSubscription = (cleanup, connectionError) => {
	try {
		cleanup();
	} catch (cleanupError) {
		console.error("[assistant-ui] Subscription rollback cleanup threw", cleanupError);
	}
	throw connectionError;
};
const shallowEqualOrUndefined = (a, b) => a === void 0 || b === void 0 ? a === b : shallowEqual(a, b);
var BaseSubscribable = class {
	_subscribers = /* @__PURE__ */ new Set();
	subscribe(callback) {
		this._subscribers.add(callback);
		return () => this._subscribers.delete(callback);
	}
	waitForUpdate() {
		return new Promise((resolve) => {
			const unsubscribe = this.subscribe(() => {
				unsubscribe();
				resolve();
			});
		});
	}
	_notifySubscribers() {
		notifySubscribers(this._subscribers);
	}
};
var WritableSubscribable = class extends BaseSubscribable {
	_state;
	constructor(state) {
		super();
		this._state = state;
		this.subscribe = this.subscribe.bind(this);
		this.getState = this.getState.bind(this);
		this.getServerSnapshot = () => state;
	}
	getState() {
		return this._state;
	}
	getServerSnapshot;
	setState(state) {
		if (Object.is(state, this._state)) return;
		this._state = state;
		this._notifySubscribers();
	}
};
var BaseSubject = class {
	_subscriptions = /* @__PURE__ */ new Set();
	_connection;
	get isConnected() {
		return !!this._connection;
	}
	notifySubscribers(payload, errorContext) {
		if (errorContext) {
			notifyEventListeners(this._subscriptions, payload, errorContext);
			return;
		}
		notifySubscribers(this._subscriptions, payload);
	}
	_updateConnection() {
		if (this._subscriptions.size > 0) {
			if (this._connection) return;
			this._connection = this._connect();
		} else {
			const connection = this._connection;
			this._connection = void 0;
			connection?.();
		}
	}
	subscribe(callback) {
		this._subscriptions.add(callback);
		try {
			this._updateConnection();
		} catch (error) {
			this._subscriptions.delete(callback);
			throw error;
		}
		return () => {
			this._subscriptions.delete(callback);
			this._updateConnection();
		};
	}
};
var ShallowMemoizeSubject = class extends BaseSubject {
	get path() {
		return this.binding.path;
	}
	binding;
	constructor(binding) {
		super();
		this.binding = binding;
		const state = binding.getState();
		if (state === SKIP_UPDATE) throw new Error("Entry not available in the store");
		this._previousState = state;
	}
	_previousState;
	getState = () => {
		if (!this.isConnected) this._syncState();
		return this._previousState;
	};
	_syncState() {
		const state = this.binding.getState();
		if (state === SKIP_UPDATE) return false;
		if (shallowEqualOrUndefined(state, this._previousState)) return false;
		this._previousState = state;
		return true;
	}
	_connect() {
		const callback = () => {
			if (this._syncState()) this.notifySubscribers();
		};
		const unsubscribe = this.binding.subscribe(callback);
		try {
			this._syncState();
			return unsubscribe;
		} catch (error) {
			throw rollbackSubscription(unsubscribe, error);
		}
	}
};
var LazyMemoizeSubject = class extends BaseSubject {
	get path() {
		return this.binding.path;
	}
	binding;
	constructor(binding) {
		super();
		this.binding = binding;
	}
	_previousStateDirty = true;
	_previousState;
	getState = () => {
		if (!this.isConnected || this._previousStateDirty) {
			const newState = this.binding.getState();
			if (newState !== SKIP_UPDATE && (this._previousState === void 0 || !shallowEqualOrUndefined(newState, this._previousState))) this._previousState = newState;
			this._previousStateDirty = false;
		}
		if (this._previousState === void 0) throw new Error("Entry not available in the store");
		return this._previousState;
	};
	_connect() {
		const callback = () => {
			this._previousStateDirty = true;
			this.notifySubscribers();
		};
		const unsubscribe = this.binding.subscribe(callback);
		this._previousStateDirty = true;
		return unsubscribe;
	}
};
var NestedSubscriptionSubject = class extends BaseSubject {
	get path() {
		return this.binding.path;
	}
	binding;
	constructor(binding) {
		super();
		this.binding = binding;
	}
	getState() {
		return this.binding.getState();
	}
	outerSubscribe(callback) {
		return this.binding.subscribe(callback);
	}
	_connect() {
		const callback = () => {
			this.notifySubscribers();
		};
		let lastState = this.binding.getState();
		let innerUnsubscribe = lastState?.subscribe(callback);
		const onRuntimeUpdate = () => {
			const newState = this.binding.getState();
			if (newState === lastState) return;
			lastState = newState;
			const previousInner = innerUnsubscribe;
			innerUnsubscribe = void 0;
			try {
				previousInner?.();
			} finally {
				innerUnsubscribe = newState?.subscribe(callback);
				callback();
			}
		};
		let outerUnsubscribe;
		try {
			outerUnsubscribe = this.outerSubscribe(onRuntimeUpdate);
		} catch (error) {
			throw rollbackSubscription(() => innerUnsubscribe?.(), error);
		}
		return () => runCleanups([() => outerUnsubscribe(), () => innerUnsubscribe?.()]);
	}
};
var EventSubscriptionSubject = class extends BaseSubject {
	config;
	constructor(config) {
		super();
		this.config = config;
	}
	getState() {
		return this.config.binding.getState();
	}
	outerSubscribe(callback) {
		return this.config.binding.subscribe(callback);
	}
	_connect() {
		const errorContext = `Runtime event "${this.config.event}"`;
		const callback = (payload) => {
			this.notifySubscribers(payload, errorContext);
		};
		let lastState = this.config.binding.getState();
		let innerUnsubscribe = lastState?.unstable_on(this.config.event, callback);
		const onRuntimeUpdate = () => {
			const newState = this.config.binding.getState();
			if (newState === lastState) return;
			lastState = newState;
			const previousInner = innerUnsubscribe;
			innerUnsubscribe = void 0;
			try {
				previousInner?.();
			} finally {
				innerUnsubscribe = newState?.unstable_on(this.config.event, callback);
				if (this.config.notifyOnRebind) callback({});
			}
		};
		let outerUnsubscribe;
		try {
			outerUnsubscribe = this.outerSubscribe(onRuntimeUpdate);
		} catch (error) {
			throw rollbackSubscription(() => innerUnsubscribe?.(), error);
		}
		return () => runCleanups([() => outerUnsubscribe(), () => innerUnsubscribe?.()]);
	}
};
//#endregion
export { BaseSubject, BaseSubscribable, EventSubscriptionSubject, LazyMemoizeSubject, NestedSubscriptionSubject, SKIP_UPDATE, ShallowMemoizeSubject, WritableSubscribable, notifySubscribers, runCleanups };
