export type AssistantCloudAuthStrategy = {
    readonly strategy: "anon" | "jwt" | "api-key";
    getAuthHeaders(): Promise<Record<string, string> | false>;
    readAuthHeaders(headers: Headers): void;
};
export declare class AssistantCloudJWTAuthStrategy implements AssistantCloudAuthStrategy {
    #private;
    readonly strategy = "jwt";
    private cachedToken;
    private tokenExpiry;
    private tokenRequest;
    constructor(authTokenCallback: () => Promise<string | null>);
    getAuthHeaders(): Promise<Record<string, string> | false>;
    private fetchAuthHeaders;
    readAuthHeaders(headers: Headers): void;
}
export declare class AssistantCloudAPIKeyAuthStrategy implements AssistantCloudAuthStrategy {
    #private;
    readonly strategy = "api-key";
    constructor(apiKey: string, userId: string, workspaceId: string);
    getAuthHeaders(): Promise<Record<string, string>>;
    readAuthHeaders(): void;
}
export declare const normalizeBaseUrl: (baseUrl: string) => string;
/** The refresh token of the anonymous identity this browser holds for `baseUrl`, or null when it has none. */
export declare const readAnonymousRefreshToken: (baseUrl: string) => string | null;
export declare class AssistantCloudAnonymousAuthStrategy implements AssistantCloudAuthStrategy {
    readonly strategy = "anon";
    private baseUrl;
    private jwtStrategy;
    constructor(baseUrl: string);
    getAuthHeaders(): Promise<Record<string, string> | false>;
    readAuthHeaders(headers: Headers): void;
}