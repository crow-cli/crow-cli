export type UseActionBarCopyOptions = {
    copiedDuration?: number | undefined;
    copyToClipboard?: ((text: string) => void | Promise<void>) | undefined;
};
export declare const useActionBarCopy: ({ copiedDuration, copyToClipboard, }?: UseActionBarCopyOptions) => {
    copy: () => void;
    disabled: boolean;
    isCopied: boolean;
};