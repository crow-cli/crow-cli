"use client";
import { stepStreamingTiming } from "../../runtime/utils/streaming-timing.js";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/useStreamingTiming.ts
/**
* Tracks per-message streaming timing client-side and returns finalized
* `MessageTiming` keyed by message id.
*
* Observes `isRunning` transitions and content growth through the provided
* `accessors`, which adapt the hook to a runtime's message shape. Timing is
* finalized when streaming ends; adapters thread the result into
* `useExternalMessageConverter` metadata as `messageTiming`.
*
* @example
* ```ts
* const messageTiming = useStreamingTiming(messages, isRunning, {
*   getAssistantMessageId: (msgs) => msgs.findLast((m) => m.role === "assistant")?.id,
*   getTextLength: (msgs, id) => msgs.find((m) => m.id === id)?.content?.length ?? 0,
*   getToolCallCount: (msgs, id) => msgs.find((m) => m.id === id)?.tool_calls?.length ?? 0,
* });
* ```
*/
const useStreamingTiming = (messages, isRunning, accessors, options) => {
	const [timings, setTimings] = useState({});
	const stateRef = useRef(null);
	const accessorsRef = useRef(accessors);
	accessorsRef.current = accessors;
	const optionsRef = useRef(options);
	optionsRef.current = options;
	useEffect(() => {
		const result = stepStreamingTiming(stateRef.current, messages, isRunning, accessorsRef.current, optionsRef.current);
		stateRef.current = result.state;
		if (Object.keys(result.timings).length > 0) setTimings((prev) => ({
			...prev,
			...result.timings
		}));
	}, [messages, isRunning]);
	return timings;
};
//#endregion
export { useStreamingTiming };
