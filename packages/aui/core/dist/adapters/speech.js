import { notifyEventListeners } from "../utils/notify-event-listeners.js";
//#region src/adapters/speech.ts
const DICTATION_STOP_TIMEOUT_MS = 5e3;
var WebSpeechSynthesisAdapter = class {
	speak(text) {
		const utterance = new SpeechSynthesisUtterance(text);
		const subscribers = /* @__PURE__ */ new Set();
		const handleEnd = (reason, error) => {
			if (res.status.type === "ended") return;
			res.status = {
				type: "ended",
				reason,
				error
			};
			notifyEventListeners(subscribers, void 0, "Speech synthesis");
		};
		utterance.addEventListener("end", () => handleEnd("finished"));
		utterance.addEventListener("error", (e) => handleEnd("error", e.error));
		const res = {
			status: { type: "running" },
			cancel: () => {
				if (res.status.type === "ended") return;
				window.speechSynthesis.cancel();
				handleEnd("cancelled");
			},
			subscribe: (callback) => {
				if (res.status.type === "ended") {
					let cancelled = false;
					queueMicrotask(() => {
						if (!cancelled) notifyEventListeners([callback], void 0, "Speech synthesis");
					});
					return () => {
						cancelled = true;
					};
				} else {
					subscribers.add(callback);
					return () => {
						subscribers.delete(callback);
					};
				}
			}
		};
		window.speechSynthesis.speak(utterance);
		return res;
	}
};
const getSpeechRecognitionAPI = () => {
	if (typeof window === "undefined") return void 0;
	return window.SpeechRecognition ?? window.webkitSpeechRecognition;
};
var WebSpeechDictationAdapter = class {
	_language;
	_continuous;
	_interimResults;
	constructor(options = {}) {
		const defaultLanguage = typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
		this._language = options.language ?? defaultLanguage;
		this._continuous = options.continuous ?? true;
		this._interimResults = options.interimResults ?? true;
	}
	static isSupported() {
		return getSpeechRecognitionAPI() !== void 0;
	}
	listen() {
		const SpeechRecognitionAPI = getSpeechRecognitionAPI();
		if (!SpeechRecognitionAPI) throw new Error("SpeechRecognition is not supported in this browser. Try using Chrome, Edge, or Safari.");
		const recognition = new SpeechRecognitionAPI();
		recognition.lang = this._language;
		recognition.continuous = this._continuous;
		recognition.interimResults = this._interimResults;
		const speechStartCallbacks = /* @__PURE__ */ new Set();
		const speechEndCallbacks = /* @__PURE__ */ new Set();
		const speechCallbacks = /* @__PURE__ */ new Set();
		let finalTranscript = "";
		let hasInterimTranscript = false;
		let firstInterimIndex = 0;
		const session = {
			status: { type: "starting" },
			stop: async () => {
				recognition.stop();
				return new Promise((resolve) => {
					const timeoutAt = Date.now() + DICTATION_STOP_TIMEOUT_MS;
					const checkEnded = () => {
						if (session.status.type === "ended") resolve();
						else if (Date.now() >= timeoutAt) {
							updateStatus({
								type: "ended",
								reason: "cancelled"
							});
							try {
								recognition.abort();
							} catch (error) {
								console.error("Dictation cancellation after stop timeout failed:", error);
							}
							resolve();
						} else setTimeout(checkEnded, 50);
					};
					checkEnded();
				});
			},
			cancel: () => {
				recognition.abort();
			},
			onSpeechStart: (callback) => {
				speechStartCallbacks.add(callback);
				return () => {
					speechStartCallbacks.delete(callback);
				};
			},
			onSpeechEnd: (callback) => {
				speechEndCallbacks.add(callback);
				return () => {
					speechEndCallbacks.delete(callback);
				};
			},
			onSpeech: (callback) => {
				speechCallbacks.add(callback);
				return () => {
					speechCallbacks.delete(callback);
				};
			}
		};
		const updateStatus = (newStatus) => {
			session.status = newStatus;
		};
		recognition.addEventListener("speechstart", () => {
			notifyEventListeners(speechStartCallbacks, void 0, "Dictation");
		});
		recognition.addEventListener("start", () => {
			updateStatus({ type: "running" });
		});
		recognition.addEventListener("result", (event) => {
			const speechEvent = event;
			let interimTranscript = "";
			for (let i = firstInterimIndex; i < speechEvent.results.length; i++) {
				const result = speechEvent.results[i];
				if (!result) continue;
				const transcript = result[0]?.transcript ?? "";
				if (result.isFinal) {
					firstInterimIndex = i + 1;
					finalTranscript += transcript;
					hasInterimTranscript = false;
					notifyEventListeners(speechCallbacks, () => ({
						transcript,
						isFinal: true
					}), "Dictation");
				} else interimTranscript += transcript;
			}
			if (interimTranscript || hasInterimTranscript) {
				hasInterimTranscript = interimTranscript.length > 0;
				notifyEventListeners(speechCallbacks, () => ({
					transcript: interimTranscript,
					isFinal: false
				}), "Dictation");
			}
		});
		recognition.addEventListener("speechend", () => {});
		recognition.addEventListener("end", () => {
			if (session.status.type !== "ended") updateStatus({
				type: "ended",
				reason: "stopped"
			});
			if (finalTranscript) {
				notifyEventListeners(speechEndCallbacks, () => ({ transcript: finalTranscript }), "Dictation");
				finalTranscript = "";
			}
		});
		recognition.addEventListener("error", (event) => {
			if (session.status.type === "ended") return;
			const errorEvent = event;
			if (errorEvent.error === "aborted") updateStatus({
				type: "ended",
				reason: "cancelled"
			});
			else {
				updateStatus({
					type: "ended",
					reason: "error"
				});
				console.error("Dictation error:", errorEvent.error, errorEvent.message);
			}
		});
		try {
			recognition.start();
		} catch (error) {
			updateStatus({
				type: "ended",
				reason: "error"
			});
			throw error;
		}
		return session;
	}
};
//#endregion
export { WebSpeechDictationAdapter, WebSpeechSynthesisAdapter };
