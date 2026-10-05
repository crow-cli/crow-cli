import { ExportedMessageRepository } from "../../runtime/utils/message-repository.js";
import { BaseAssistantRuntimeCore } from "../../runtime/base/base-assistant-runtime-core.js";
import { LocalThreadRuntimeCore } from "./local-thread-runtime-core.js";
import { LocalThreadListRuntimeCore } from "./local-thread-list-runtime-core.js";
//#region src/runtimes/local/local-runtime-core.ts
var LocalRuntimeCore = class extends BaseAssistantRuntimeCore {
	threads;
	Provider = void 0;
	_options;
	constructor(options, initialMessages) {
		super();
		this._options = options;
		this.threads = new LocalThreadListRuntimeCore(() => {
			return new LocalThreadRuntimeCore(this._contextProvider, this._options);
		});
		if (initialMessages) this.threads.getMainThreadRuntimeCore().import(ExportedMessageRepository.fromArray(initialMessages));
	}
};
//#endregion
export { LocalRuntimeCore };
