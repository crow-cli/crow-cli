import { notifyEventListeners } from "../utils/notify-event-listeners.js";
//#region src/adapters/voice.ts
function createVoiceSession(options, setup) {
	const statusCbs = /* @__PURE__ */ new Set();
	const transcriptCbs = /* @__PURE__ */ new Set();
	const modeCbs = /* @__PURE__ */ new Set();
	const volumeCbs = /* @__PURE__ */ new Set();
	let currentStatus = { type: "starting" };
	let isMuted = false;
	let disposed = false;
	let disconnected = false;
	let controls = null;
	let controlsDisconnected = false;
	const abortSignal = options.abortSignal;
	let abortHandler;
	const detachAbortHandler = () => {
		if (abortHandler) {
			abortSignal?.removeEventListener("abort", abortHandler);
			abortHandler = void 0;
		}
	};
	const cleanup = () => {
		disposed = true;
		statusCbs.clear();
		transcriptCbs.clear();
		modeCbs.clear();
		volumeCbs.clear();
	};
	const disconnectControls = () => {
		if (!controls || controlsDisconnected) return;
		controlsDisconnected = true;
		controls.disconnect();
	};
	const helpers = {
		setStatus: (status) => {
			if (disposed) return;
			currentStatus = status;
			notifyEventListeners(statusCbs, status, "Voice session");
		},
		end: (reason, error) => {
			if (disposed) return;
			currentStatus = {
				type: "ended",
				reason,
				error
			};
			notifyEventListeners(statusCbs, currentStatus, "Voice session");
			cleanup();
		},
		emitTranscript: (item) => {
			if (disposed) return;
			notifyEventListeners(transcriptCbs, item, "Voice session");
		},
		emitMode: (mode) => {
			if (disposed) return;
			notifyEventListeners(modeCbs, mode, "Voice session");
		},
		emitVolume: (volume) => {
			if (disposed) return;
			notifyEventListeners(volumeCbs, volume, "Voice session");
		},
		isDisposed: () => disposed
	};
	const session = {
		get status() {
			return currentStatus;
		},
		get isMuted() {
			return isMuted;
		},
		get sendText() {
			if (disposed || !controls?.sendText) return void 0;
			return controls.sendText.bind(controls);
		},
		disconnect: () => {
			if (disconnected) return;
			disconnected = true;
			detachAbortHandler();
			if (currentStatus.type !== "ended") {
				currentStatus = {
					type: "ended",
					reason: "cancelled"
				};
				notifyEventListeners(statusCbs, currentStatus, "Voice session");
			}
			try {
				disconnectControls();
			} finally {
				cleanup();
			}
		},
		mute: () => {
			controls?.mute();
			isMuted = true;
		},
		unmute: () => {
			controls?.unmute();
			isMuted = false;
		},
		onStatusChange: (cb) => {
			statusCbs.add(cb);
			return () => statusCbs.delete(cb);
		},
		onTranscript: (cb) => {
			transcriptCbs.add(cb);
			return () => transcriptCbs.delete(cb);
		},
		onModeChange: (cb) => {
			modeCbs.add(cb);
			return () => modeCbs.delete(cb);
		},
		onVolumeChange: (cb) => {
			volumeCbs.add(cb);
			return () => volumeCbs.delete(cb);
		}
	};
	if (abortSignal) {
		abortHandler = () => session.disconnect();
		abortSignal.addEventListener("abort", abortHandler, { once: true });
		if (abortSignal.aborted) {
			session.disconnect();
			return session;
		}
	}
	const doSetup = async () => {
		try {
			if (disposed) return;
			controls = await setup(helpers);
			if (disposed) {
				disconnectControls();
				return;
			}
			if (isMuted) controls.mute();
			if (controls.sendText && currentStatus.type === "running") notifyEventListeners(statusCbs, currentStatus, "Voice session");
		} catch (error) {
			helpers.end("error", error);
		}
	};
	doSetup();
	return session;
}
//#endregion
export { createVoiceSession };
