import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
type PdfToImagesRequestBody = {
    file_blob?: string | undefined;
    file_url?: string | undefined;
};
type PdfToImagesResponse = {
    success: boolean;
    urls: string[];
    message: string;
};
type GeneratePresignedUploadUrlRequestBody = {
    filename: string;
};
type GeneratePresignedUploadUrlResponse = {
    success: boolean;
    signedUrl: string;
    expiresAt: string;
    publicUrl: string;
    key?: string;
};
export type GeneratePresignedDownloadUrlResponse = {
    signedUrl: string;
    expiresAt: string;
    key: string;
};
export declare class AssistantCloudFiles {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    /**
     * @deprecated Assistant Cloud has no PDF conversion endpoint, so this request always rejects with a `CloudAPIError` whose `status` is 404.
     */
    pdfToImages(body: PdfToImagesRequestBody): Promise<PdfToImagesResponse>;
    generatePresignedUploadUrl(body: GeneratePresignedUploadUrlRequestBody): Promise<GeneratePresignedUploadUrlResponse>;
    generatePresignedDownloadUrl(body: {
        key: string;
    } | {
        url: string;
    }): Promise<GeneratePresignedDownloadUrlResponse>;
}
export {};