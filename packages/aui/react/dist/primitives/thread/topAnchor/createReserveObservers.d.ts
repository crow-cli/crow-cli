export declare const createReserveObservers: (onChange: () => void) => {
    target: (viewport: HTMLElement, anchor: HTMLElement, target: HTMLElement) => void;
    disconnect: () => void;
};