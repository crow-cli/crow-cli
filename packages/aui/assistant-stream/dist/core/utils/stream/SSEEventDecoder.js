//#region src/core/utils/stream/SSEEventDecoder.ts
var SSEEventDecoder = class {
	lineChunks = [];
	dataLines = [];
	eventName;
	lastEventId;
	retry;
	pendingLF = false;
	started = false;
	trailing;
	constructor(options) {
		this.trailing = options?.trailing ?? "drop";
	}
	push(text) {
		const events = [];
		if (text === "") return events;
		if (!this.started) {
			this.started = true;
			if (text.startsWith("﻿")) text = text.slice(1);
		}
		if (this.pendingLF && text.startsWith("\n")) text = text.slice(1);
		this.pendingLF = text.endsWith("\r");
		const lines = text.split(/\r\n|\r|\n/);
		const remainder = lines.pop();
		for (const line of lines) {
			let completeLine = line;
			if (this.lineChunks.length > 0) {
				this.lineChunks.push(line);
				completeLine = this.lineChunks.join("");
				this.lineChunks = [];
			}
			const event = this.processLine(completeLine);
			if (event) events.push(event);
		}
		if (remainder !== "") this.lineChunks.push(remainder);
		return events;
	}
	flush() {
		if (this.trailing === "drop") {
			this.resetFrame();
			this.lineChunks = [];
			this.pendingLF = false;
			return null;
		}
		if (this.lineChunks.length > 0) this.processLine(this.lineChunks.join(""));
		this.lineChunks = [];
		this.pendingLF = false;
		return this.dispatchEvent();
	}
	processLine(line) {
		if (line === "") return this.dispatchEvent();
		if (line.startsWith(":")) return null;
		const separator = line.indexOf(":");
		const field = separator === -1 ? line : line.slice(0, separator);
		let value = separator === -1 ? "" : line.slice(separator + 1);
		if (value.startsWith(" ")) value = value.slice(1);
		switch (field) {
			case "data":
				this.dataLines.push(value);
				break;
			case "event":
				this.eventName = value;
				break;
			case "id":
				if (!value.includes("\0")) this.lastEventId = value;
				break;
			case "retry": {
				const retry = Number(value);
				if (/^\d+$/.test(value) && Number.isSafeInteger(retry)) this.retry = retry;
				break;
			}
		}
		return null;
	}
	dispatchEvent() {
		if (this.dataLines.length === 0) {
			this.resetFrame();
			return null;
		}
		const event = { data: this.dataLines.join("\n") };
		if (this.eventName !== void 0) event.event = this.eventName;
		if (this.lastEventId !== void 0) event.id = this.lastEventId;
		if (this.retry !== void 0) event.retry = this.retry;
		this.resetFrame();
		return event;
	}
	resetFrame() {
		this.dataLines = [];
		this.eventName = void 0;
	}
};
//#endregion
export { SSEEventDecoder };
