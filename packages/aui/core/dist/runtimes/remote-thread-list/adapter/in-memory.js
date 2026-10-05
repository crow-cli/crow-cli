//#region src/runtimes/remote-thread-list/adapter/in-memory.ts
var InMemoryThreadListAdapter = class {
	list() {
		return Promise.resolve({ threads: [] });
	}
	rename() {
		return Promise.resolve();
	}
	updateCustom() {
		return Promise.resolve();
	}
	archive() {
		return Promise.resolve();
	}
	unarchive() {
		return Promise.resolve();
	}
	delete() {
		return Promise.resolve();
	}
	initialize(threadId) {
		return Promise.resolve({
			remoteId: threadId,
			externalId: void 0
		});
	}
	generateTitle() {
		return Promise.resolve(new ReadableStream({ start(controller) {
			controller.close();
		} }));
	}
	fetch(threadId) {
		return Promise.reject(/* @__PURE__ */ new Error(`Thread "${threadId}" not found in in-memory thread list.`));
	}
};
//#endregion
export { InMemoryThreadListAdapter };
