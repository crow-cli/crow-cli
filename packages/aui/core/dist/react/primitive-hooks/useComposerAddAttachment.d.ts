import type { CreateAttachment } from "../../types/attachment.js";
export declare const useComposerAddAttachment: () => {
    addAttachment: (file: File | CreateAttachment) => Promise<void>;
    disabled: boolean;
};