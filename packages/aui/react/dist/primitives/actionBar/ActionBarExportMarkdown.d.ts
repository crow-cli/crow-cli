import type { ActionButtonProps } from "../../utils/createActionButton.js";
declare const useActionBarExportMarkdown: ({ filename, onExport, }?: {
    filename?: string | undefined;
    onExport?: ((content: string) => void | Promise<void>) | undefined;
}) => (() => Promise<void>) | null;
export declare namespace ActionBarPrimitiveExportMarkdown {
    type Element = HTMLButtonElement;
    type Props = ActionButtonProps<typeof useActionBarExportMarkdown>;
}
export declare const ActionBarPrimitiveExportMarkdown: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    filename?: string | undefined;
    onExport?: ((content: string) => void | Promise<void>) | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
export {};