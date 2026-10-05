//#region src/AssistantCloudEvents.ts
const FLUSH_SIZE = 20;
const MAX_BATCH_SIZE = 50;
const FLUSH_DELAY_MS = 2e3;
const RETRY_DELAYS_MS = [250, 1e3];
const pendingClearers = /* @__PURE__ */ new WeakMap();
const clearPendingAssistantCloudEvents = (events) => {
	pendingClearers.get(events)?.();
};
var AssistantCloudEvents = class {
	buffer = [];
	timer;
	flushing;
	retryTimer;
	resolveRetryDelay;
	bestEffortRequested = false;
	generation = 0;
	cloud;
	isEnabled;
	listening = false;
	constructor(cloud, isEnabled) {
		this.cloud = cloud;
		this.isEnabled = isEnabled;
		pendingClearers.set(this, () => this.clearPending());
	}
	track(event) {
		if (!this.isEnabled()) return;
		this.listen();
		this.buffer.push(normalizeEvent(event));
		if (this.buffer.length >= FLUSH_SIZE) {
			this.flush(true);
			return;
		}
		this.scheduleFlush();
	}
	listen() {
		if (this.listening || typeof window === "undefined" || typeof document === "undefined") return;
		this.listening = true;
		window.addEventListener("pagehide", this.flushBestEffort);
		document.addEventListener("visibilitychange", this.onVisibilityChange);
	}
	unlisten() {
		if (!this.listening) return;
		this.listening = false;
		window.removeEventListener("pagehide", this.flushBestEffort);
		document.removeEventListener("visibilitychange", this.onVisibilityChange);
	}
	dispose() {
		this.unlisten();
		this.clearFlushTimer();
		this.flushBestEffort();
	}
	clearPending() {
		this.generation++;
		this.buffer = [];
		this.clearFlushTimer();
		this.interruptRetryDelay();
		this.unlisten();
	}
	onVisibilityChange = () => {
		if (document.visibilityState === "hidden") this.flushBestEffort();
	};
	flushBestEffort = () => {
		if (this.flushing) {
			this.bestEffortRequested = true;
			this.interruptRetryDelay();
		}
		return this.flush(false);
	};
	flush = async (retryFailures) => {
		if (!this.isEnabled()) {
			this.clearPending();
			return;
		}
		if (this.flushing) return this.flushing;
		this.clearFlushTimer();
		const task = this.flushPending(retryFailures);
		this.flushing = task;
		task.then(() => {
			if (this.flushing !== task) return;
			this.flushing = void 0;
			this.bestEffortRequested = false;
			if (this.buffer.length === 0) {
				this.clearFlushTimer();
				this.unlisten();
			} else this.flush(true);
		});
		return task;
	};
	async flushPending(retryFailures) {
		while (this.buffer.length > 0) {
			if (!this.isEnabled()) {
				this.buffer = [];
				return;
			}
			const events = this.buffer.splice(0, MAX_BATCH_SIZE);
			const generation = this.generation;
			for (let attempt = 0;; attempt++) try {
				await this.cloud.makeRequest("/events", {
					method: "POST",
					body: { events },
					keepalive: true
				});
				if (generation !== this.generation) return;
				break;
			} catch {
				if (generation !== this.generation) return;
				const delay = retryFailures && !this.bestEffortRequested ? RETRY_DELAYS_MS[attempt] : void 0;
				if (delay === void 0) break;
				await this.waitForRetry(delay);
				if (generation !== this.generation) return;
				if (!this.isEnabled()) return this.clearPending();
				if (this.bestEffortRequested) break;
			}
		}
	}
	waitForRetry(delay) {
		return new Promise((resolve) => {
			const finish = () => {
				this.retryTimer = void 0;
				this.resolveRetryDelay = void 0;
				resolve();
			};
			this.resolveRetryDelay = finish;
			this.retryTimer = setTimeout(finish, delay);
		});
	}
	interruptRetryDelay() {
		if (this.retryTimer !== void 0) clearTimeout(this.retryTimer);
		this.resolveRetryDelay?.();
	}
	scheduleFlush() {
		if (this.timer !== void 0) return;
		this.timer = setTimeout(() => {
			this.timer = void 0;
			this.flush(true);
		}, FLUSH_DELAY_MS);
	}
	clearFlushTimer() {
		if (this.timer === void 0) return;
		clearTimeout(this.timer);
		this.timer = void 0;
	}
};
const normalizeEvent = (event) => {
	const props = normalizeProps(event.props);
	return {
		kind: event.kind,
		...normalizeId(event.thread_id) ? { thread_id: event.thread_id } : {},
		...normalizeId(event.message_id) ? { message_id: event.message_id } : {},
		...normalizeId(event.run_id) ? { run_id: event.run_id } : {},
		...isNonNegativeInteger(event.value) ? { value: event.value } : {},
		...props ? { props } : {}
	};
};
const normalizeId = (value) => value && value.length <= 48 ? value : void 0;
const isNonNegativeInteger = (value) => value !== void 0 && Number.isInteger(value) && value >= 0;
const normalizeProps = (props) => {
	if (!props) return void 0;
	const entries = Object.entries(props);
	if (entries.some(([, value]) => typeof value === "string" && value.length > 256 || typeof value === "number" && !Number.isFinite(value) || typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean")) return;
	const value = Object.fromEntries(entries);
	return new TextEncoder().encode(JSON.stringify(value)).byteLength <= 1024 ? value : void 0;
};
//#endregion
export { AssistantCloudEvents, clearPendingAssistantCloudEvents };
