import { isDevelopment } from "./helpers/env.js";
import { throwAggregated } from "./helpers/throwAggregated.js";
//#region src/core/scheduler.ts
const MAX_UPDATE_DEPTH = 50;
let flushState = {
	schedulers: /* @__PURE__ */ new Set(),
	isScheduled: false
};
let activeDrainRuns = null;
const pendingNotifies = [];
var UpdateScheduler = class {
	_isDirty = false;
	_task;
	constructor(_task) {
		this._task = _task;
	}
	get isDirty() {
		return this._isDirty;
	}
	markDirty() {
		if (activeDrainRuns && (activeDrainRuns.get(this) ?? 0) >= MAX_UPDATE_DEPTH) throw new Error("Maximum update depth exceeded. This can happen when a resource repeatedly calls setState inside useEffect.");
		this._isDirty = true;
		flushState.schedulers.add(this);
		scheduleFlush();
	}
	runTask() {
		activeDrainRuns?.set(this, (activeDrainRuns.get(this) ?? 0) + 1);
		this._isDirty = false;
		this._task();
	}
	settle() {
		this._isDirty = false;
	}
};
const scheduledTasks = [];
const taskScheduler = new UpdateScheduler(() => {
	const tasks = scheduledTasks.splice(0);
	const errors = [];
	for (const task of tasks) try {
		task();
	} catch (error) {
		errors.push(error);
	}
	throwAggregated(errors, "Errors occurred while running scheduled tasks");
});
const scheduleTask = (task) => {
	taskScheduler.markDirty();
	scheduledTasks.push(task);
};
const scheduleNotify = (notify) => {
	if (activeDrainRuns !== null) {
		pendingNotifies.push(notify);
		return;
	}
	notify();
};
const scheduleFlush = () => {
	if (flushState.isScheduled) return;
	flushState.isScheduled = true;
	scheduleMacrotask();
};
const flushScheduled = () => {
	const prevDrainRuns = activeDrainRuns;
	activeDrainRuns = /* @__PURE__ */ new Map();
	const errors = [];
	try {
		for (const scheduler of flushState.schedulers) {
			flushState.schedulers.delete(scheduler);
			if (!scheduler.isDirty) continue;
			try {
				scheduler.runTask();
			} catch (error) {
				errors.push(error);
			}
		}
	} finally {
		activeDrainRuns = prevDrainRuns;
		flushState.schedulers.clear();
		flushState.isScheduled = false;
		if (activeDrainRuns === null) while (pendingNotifies.length > 0) try {
			pendingNotifies.shift()();
		} catch (error) {
			errors.push(error);
		}
	}
	throwAggregated(errors, "Errors occurred during flushSync");
};
const scheduleMacrotask = (() => {
	if (typeof MessageChannel !== "undefined") {
		let port1 = null;
		let port2;
		return () => {
			if (!port1) {
				const channel = new MessageChannel();
				channel.port1.onmessage = () => {
					port1?.unref?.();
					flushScheduled();
				};
				port1 = channel.port1;
				port2 = channel.port2;
			}
			port1.ref?.();
			port2.postMessage(null);
		};
	}
	return () => setTimeout(flushScheduled, 0);
})();
const flushTapSync = (callback) => {
	if (activeDrainRuns !== null) {
		if (isDevelopment) console.warn("flushTapSync was called from inside a render or commit. The flush is deferred until the current pass completes.");
		return callback();
	}
	const prev = flushState;
	flushState = {
		schedulers: /* @__PURE__ */ new Set(),
		isScheduled: true
	};
	try {
		const value = callback();
		flushScheduled();
		return value;
	} finally {
		const stranded = flushState.schedulers;
		flushState = prev;
		if (stranded.size > 0) {
			for (const scheduler of stranded) flushState.schedulers.add(scheduler);
			scheduleFlush();
		}
	}
};
//#endregion
export { UpdateScheduler, flushTapSync, scheduleNotify, scheduleTask };
