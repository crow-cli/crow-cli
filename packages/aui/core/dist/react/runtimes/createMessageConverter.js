"use client";
import { getExternalStoreMessages } from "../../runtime/utils/external-store-message.js";
import { convertExternalMessages, useExternalMessageConverter } from "./external-message-converter.js";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/runtimes/createMessageConverter.ts
const createMessageConverter = (callback) => {
	const result = {
		useThreadMessages: ({ messages, isRunning, joinStrategy, metadata }) => {
			return useExternalMessageConverter({
				callback,
				messages,
				isRunning,
				joinStrategy,
				metadata
			});
		},
		toThreadMessages: (messages, isRunning = false, metadata = {}) => {
			return convertExternalMessages(messages, callback, isRunning, metadata);
		},
		toOriginalMessages: (input) => {
			const messages = getExternalStoreMessages(input);
			if (messages.length === 0) throw new Error("No original messages found");
			return messages;
		},
		toOriginalMessage: (input) => {
			return result.toOriginalMessages(input)[0];
		},
		useOriginalMessage: () => {
			return result.useOriginalMessages()[0];
		},
		useOriginalMessages: () => {
			const aui = useAui();
			const partMessages = useAuiState((s) => {
				if (aui.part.source) return getExternalStoreMessages(s.part);
			});
			const messageMessages = useAuiState((s) => getExternalStoreMessages(s.message));
			const messages = partMessages ?? messageMessages;
			if (messages.length === 0) throw new Error("No original messages found");
			return messages;
		}
	};
	return result;
};
//#endregion
export { createMessageConverter };
