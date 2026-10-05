import { type CSSProperties } from "react";
import { type RenderedFrame, type SandboxOption } from "safe-content-frame";
export type SandboxHostConfig = {
    sandbox?: SandboxOption[];
    useShadowDom?: boolean;
    enableBrowserCaching?: boolean;
    salt?: string;
    product?: string;
    className?: string;
    style?: CSSProperties;
    unsafeDocumentWrite?: boolean;
};
export type SandboxHostFrame = Pick<RenderedFrame, "iframe" | "origin" | "sendMessage">;
export type SandboxHostApi = {
    setHeight: (height: number) => void;
};
export type SandboxBridge = {
    onMessage: (event: MessageEvent) => void;
    dispose: () => void;
};
export type SandboxContent = {
    html: string;
};
export type SandboxHostProps = {
    content: SandboxContent;
    contentKey: string;
    sandbox?: SandboxHostConfig | undefined;
    maxHeight?: number | undefined;
    createBridge: (frame: SandboxHostFrame, host: SandboxHostApi) => SandboxBridge;
    onError?: ((error: Error) => void) | undefined;
    containerProps?: Record<string, string | undefined> | undefined;
};
export declare function isSandboxFrameMessage(event: MessageEvent, frame: {
    iframe: HTMLIFrameElement;
    origin: string;
}): boolean;
export declare function SandboxHost({ content, contentKey, sandbox, maxHeight, createBridge, onError, containerProps, }: SandboxHostProps): import("react").JSX.Element;