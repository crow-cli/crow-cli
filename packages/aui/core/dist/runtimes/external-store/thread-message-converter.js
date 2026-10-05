//#region src/runtimes/external-store/thread-message-converter.ts
var ThreadMessageConverter = class {
	cache = /* @__PURE__ */ new WeakMap();
	convertMessages(messages, converter) {
		return messages.map((m, idx) => {
			const newMessage = converter(this.cache.get(m), m, idx);
			this.cache.set(m, newMessage);
			return newMessage;
		});
	}
};
//#endregion
export { ThreadMessageConverter };
