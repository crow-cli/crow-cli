import type { Unsubscribe } from "@assistant-ui/core";
import { type RefObject } from "react";
import { AssistantFrameHost } from "@assistant-ui/core";
type UseAssistantFrameHostOptions = {
    iframeRef: Readonly<RefObject<HTMLIFrameElement | null | undefined>>;
    targetOrigin?: string;
    register: (frameHost: AssistantFrameHost) => Unsubscribe;
};
/**
 * React hook that manages the lifecycle of an AssistantFrameHost and its binding to the current AssistantRuntime.
 *
 * Usage example:
 * ```typescript
 * function MyComponent() {
 *   const iframeRef = useRef<HTMLIFrameElement>(null);
 *
 *   useAssistantFrameHost({
 *     iframeRef,
 *     targetOrigin: "https://trusted-domain.com",
 *   });
 *
 *   return <iframe ref={iframeRef} src="..." />;
 * }
 * ```
 */
export declare const useAssistantFrameHost: ({ iframeRef, targetOrigin, register, }: UseAssistantFrameHostOptions) => void;
export {};