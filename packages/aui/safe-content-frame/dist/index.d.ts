export type SandboxOption = "allow-same-origin" | "allow-scripts" | "allow-forms" | "allow-popups" | "allow-modals" | "allow-downloads" | "allow-popups-to-escape-sandbox";
export interface SafeContentFrameOptions {
    useShadowDom?: boolean;
    enableBrowserCaching?: boolean;
    sandbox?: SandboxOption[];
    salt?: string;
}
/**
 * Why a frame never signalled a completed render. `shim-unavailable` means the
 * shim never acknowledged that it started, so the document at the shim URL is
 * missing or is not a shim. `shim-error` is the shim reporting its own failure.
 * `render-timeout` is the shim running normally with the content still not
 * rendered, which is the one case that may still resolve on its own.
 */
export type ShimLoadErrorCode = "shim-unavailable" | "shim-error" | "render-timeout";
export interface ShimLoadError extends Error {
    code: ShimLoadErrorCode;
}
export interface RenderedFrame {
    iframe: HTMLIFrameElement;
    origin: string;
    sendMessage(data: unknown, transfer?: Transferable[]): void;
    fullyLoadedPromiseWithTimeout(timeoutMs: number): Promise<void>;
    dispose(): void;
}
/**
 * Narrows a rejection from `fullyLoadedPromiseWithTimeout`. The promise also
 * rejects with plain errors that carry no code, so a bare property read is not
 * enough to tell why a frame failed. Membership of the code set is the test
 * rather than `instanceof`, which does not survive a duplicated copy of this
 * package in a consumer's bundle.
 */
export declare function isShimLoadError(error: unknown): error is ShimLoadError;
export declare class SafeContentFrame {
    private product;
    private options;
    constructor(product: string, options?: SafeContentFrameOptions);
    renderHtml(html: string, container: HTMLElement, opts?: {
        unsafeDocumentWrite?: boolean;
    }): Promise<RenderedFrame>;
    renderRaw(content: Uint8Array | string, mimeType: string, container: HTMLElement): Promise<RenderedFrame>;
    renderPdf(content: Uint8Array, container: HTMLElement): Promise<RenderedFrame>;
    private render;
    private getSandbox;
}