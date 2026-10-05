import { generateId } from "../../utils/id.js";
import { notifyEventListeners } from "../../utils/notify-event-listeners.js";
import { getThreadMessageText } from "../../utils/text.js";
import { EMPTY_QUEUE_ITEMS } from "./queue-item.js";
//#region src/runtime/queue/message-queue.ts
const getQueueItemParts = (message) => {
	const source = [...message.content, ...(message.attachments ?? []).flatMap((attachment) => (attachment.content ?? []).filter((part) => part.type !== "text"))];
	const parts = [];
	for (const part of source) if (part.type === "file" || part.type === "text") parts.push(part);
	else if (part.type === "image") parts.push({
		type: "file",
		data: part.image,
		mimeType: "image/*",
		...part.filename !== void 0 && { filename: part.filename }
	});
	return parts;
};
const createMessageQueue = (driver) => {
	let lanes = {
		queue: EMPTY_QUEUE_ITEMS,
		steer: EMPTY_QUEUE_ITEMS
	};
	const messages = /* @__PURE__ */ new Map();
	const subscribers = /* @__PURE__ */ new Set();
	let running = false;
	let dispatchPending = false;
	let paused = false;
	let held = false;
	let dispatchTransform = (m) => m;
	let suppressIdle = 0;
	let cancelSettles = 0;
	let interrupting = false;
	let busyEdges = 0;
	const notify = () => {
		notifyEventListeners(subscribers, void 0, "Message queue");
	};
	const setLanes = (next) => {
		lanes = next;
		adapter.items = next.queue;
		adapter.steerItems = next.steer;
		notify();
	};
	const toItem = (id, message) => ({
		id,
		prompt: getThreadMessageText(message),
		parts: getQueueItemParts(message)
	});
	const restore = (lane, dispatch, index = 0) => {
		paused = true;
		messages.set(dispatch.id, dispatch.message);
		setLanes({
			...lanes,
			[lane]: [
				...lanes[lane].slice(0, index),
				dispatch.item,
				...lanes[lane].slice(index)
			]
		});
	};
	const laneOf = (queueItemId) => {
		if (lanes.steer.some((item) => item.id === queueItemId)) return "steer";
		if (lanes.queue.some((item) => item.id === queueItemId)) return "queue";
	};
	const advance = () => {
		if (running || paused || held) return;
		const lane = lanes.steer.length > 0 ? "steer" : "queue";
		const head = lanes[lane][0];
		if (!head) return;
		const message = messages.get(head.id);
		if (!message) return;
		running = true;
		messages.delete(head.id);
		dispatchPending = true;
		setLanes({
			...lanes,
			[lane]: lanes[lane].slice(1)
		});
		dispatchPending = false;
		const dispatch = {
			id: head.id,
			item: head,
			message
		};
		const busyEdgesBeforeRun = busyEdges;
		try {
			driver.run(dispatchTransform(message), { steer: false });
		} catch (error) {
			if (busyEdges === busyEdgesBeforeRun) {
				running = false;
				restore(lane, dispatch);
			}
			throw error;
		}
	};
	const interrupt = (dispatch, restoreLane = "steer", restoreIndex = 0) => {
		paused = false;
		suppressIdle += Math.max(cancelSettles, 1);
		cancelSettles = 0;
		const restoreInterrupted = (replacementStarted = false) => {
			if (replacementStarted) return;
			const pendingSettles = suppressIdle;
			suppressIdle = Math.max(pendingSettles - 1, 0);
			cancelSettles = pendingSettles > 0 ? 1 : 0;
			running = pendingSettles > 0;
			restore(restoreLane, dispatch, restoreIndex);
		};
		interrupting = true;
		try {
			driver.cancel();
		} catch (error) {
			restoreInterrupted();
			throw error;
		} finally {
			interrupting = false;
		}
		running = true;
		const busyEdgesBeforeRun = busyEdges;
		try {
			driver.run(dispatchTransform(dispatch.message), { steer: true });
		} catch (error) {
			restoreInterrupted(busyEdges !== busyEdgesBeforeRun);
			throw error;
		}
	};
	const push = (lane, message) => {
		paused = false;
		const id = generateId();
		messages.set(id, message);
		setLanes({
			...lanes,
			[lane]: [...lanes[lane], toItem(id, message)]
		});
		advance();
	};
	const enqueue = (message) => {
		push("queue", message);
	};
	const steer = (message) => {
		if (running && !dispatchPending && driver.cancel) {
			const id = generateId();
			interrupt({
				id,
				item: toItem(id, message),
				message
			});
			return;
		}
		push("steer", message);
	};
	const move = (queueItemId, placement) => {
		const fromLane = laneOf(queueItemId);
		if (!fromLane) throw new Error(`Unknown queue item "${queueItemId}".`);
		const toLane = placement.lane ?? fromLane;
		const fromIndex = lanes[fromLane].findIndex((i) => i.id === queueItemId);
		const item = lanes[fromLane][fromIndex];
		const dest = (toLane === fromLane ? lanes[fromLane] : lanes[toLane]).filter((i) => i.id !== queueItemId);
		const anchorIndex = (anchor) => {
			if (anchor === queueItemId) throw new Error(`Queue item "${queueItemId}" cannot anchor itself.`);
			const index = dest.findIndex((i) => i.id === anchor);
			if (index === -1) throw new Error(`Unknown anchor "${anchor}" in lane "${toLane}".`);
			return index;
		};
		const { insertAfter, insertBefore } = placement;
		let index;
		if (insertAfter === void 0 && insertBefore === void 0) index = toLane === fromLane ? lanes[fromLane].findIndex((i) => i.id === queueItemId) : dest.length;
		else if (insertAfter !== void 0 && insertBefore !== void 0) {
			const after = insertAfter === null ? -1 : anchorIndex(insertAfter);
			if ((insertBefore === null ? dest.length : anchorIndex(insertBefore)) !== after + 1) throw new Error(`insertAfter "${insertAfter}" and insertBefore "${insertBefore}" are not adjacent in lane "${toLane}".`);
			index = after + 1;
		} else if (insertAfter !== void 0) index = insertAfter === null ? 0 : anchorIndex(insertAfter) + 1;
		else index = insertBefore === null ? dest.length : anchorIndex(insertBefore);
		if (insertAfter === void 0 && insertBefore === void 0 && toLane === "steer" && fromLane !== "steer" && running && !dispatchPending && driver.cancel) {
			const message = messages.get(queueItemId);
			messages.delete(queueItemId);
			setLanes({
				queue: lanes.queue.filter((i) => i.id !== queueItemId),
				steer: lanes.steer
			});
			interrupt({
				id: queueItemId,
				item,
				message
			}, fromLane, fromIndex);
			return;
		}
		const nextDest = [
			...dest.slice(0, index),
			item,
			...dest.slice(index)
		];
		const next = {
			...lanes,
			[toLane]: nextDest
		};
		if (toLane !== fromLane) next[fromLane] = lanes[fromLane].filter((i) => i.id !== queueItemId);
		setLanes(next);
		advance();
	};
	const edit = (queueItemId, message) => {
		const lane = laneOf(queueItemId);
		if (!lane) throw new Error(`Unknown queue item "${queueItemId}".`);
		messages.set(queueItemId, message);
		setLanes({
			...lanes,
			[lane]: lanes[lane].map((item) => item.id === queueItemId ? toItem(queueItemId, message) : item)
		});
	};
	const remove = (queueItemId) => {
		if (!messages.delete(queueItemId)) return;
		setLanes({
			queue: lanes.queue.filter((item) => item.id !== queueItemId),
			steer: lanes.steer.filter((item) => item.id !== queueItemId)
		});
	};
	const notifyCancelled = () => {
		if (interrupting || dispatchPending) return;
		if (running && cancelSettles === 0) {
			paused = true;
			cancelSettles = 1;
		}
	};
	const adapter = {
		items: lanes.queue,
		steerItems: lanes.steer,
		enqueue,
		steer,
		move,
		edit,
		remove,
		__internal_setDispatchTransform: (transform) => {
			dispatchTransform = transform;
		},
		__internal_notifyCancelled: notifyCancelled
	};
	return {
		adapter,
		hold: () => {
			held = true;
		},
		release: () => {
			held = false;
			advance();
		},
		notifyBusy: () => {
			paused = false;
			suppressIdle += cancelSettles;
			cancelSettles = 0;
			running = true;
			busyEdges++;
		},
		notifyIdle: () => {
			if (suppressIdle > 0) {
				suppressIdle--;
				return;
			}
			if (cancelSettles > 0) cancelSettles--;
			running = false;
			advance();
		},
		notifyCancelled,
		clear: () => {
			messages.clear();
			setLanes({
				queue: EMPTY_QUEUE_ITEMS,
				steer: EMPTY_QUEUE_ITEMS
			});
		},
		subscribe: (callback) => {
			subscribers.add(callback);
			return () => {
				subscribers.delete(callback);
			};
		}
	};
};
//#endregion
export { createMessageQueue };
