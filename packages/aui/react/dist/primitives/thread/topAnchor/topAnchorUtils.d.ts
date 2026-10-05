/**
 * Convert a supported CSS length string (`px`, `em`, `rem`) into pixels,
 * resolving font-relative units against the supplied element's computed style.
 * Unsupported or malformed values disable the tall-message clamp.
 *
 * Part of the top-anchor package's public input contract: consumers may pass
 * clamp configuration as supported CSS-length strings, and this function is the
 * single place that converts them into the pixel values the package operates on.
 */
export declare const parseCssLength: (value: string, element: HTMLElement) => number;
export declare const getAnchorId: (anchor: HTMLElement) => string | undefined;
export declare const createReserveElement: () => HTMLDivElement;
export declare const setReserveHeight: (reserve: HTMLElement, height: number) => boolean;
export declare const snapScrollTop: (top: number) => number;