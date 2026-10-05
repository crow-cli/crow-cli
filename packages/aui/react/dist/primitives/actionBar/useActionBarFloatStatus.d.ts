export declare const HideAndFloatStatus: {
    readonly Hidden: "hidden";
    readonly Floating: "floating";
    readonly Normal: "normal";
};
export type HideAndFloatStatus = (typeof HideAndFloatStatus)[keyof typeof HideAndFloatStatus];
export type UseActionBarFloatStatusProps = {
    hideWhenRunning?: boolean | undefined;
    autohide?: "always" | "not-last" | "never" | undefined;
    autohideFloat?: "always" | "single-branch" | "never" | undefined;
    forceVisible?: boolean | undefined;
};
export declare const useActionBarFloatStatus: ({ hideWhenRunning, autohide, autohideFloat, forceVisible, }: UseActionBarFloatStatusProps) => "hidden" | "floating" | "normal";