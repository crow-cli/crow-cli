import { CloudResponseError, readCloudRecord, readCloudString } from "./cloudResponse.js";
//#region src/AssistantCloudAuthStrategy.ts
const AUTH_TOKEN_REQUEST_TIMEOUT_MS = 3e4;
const withAuthTokenDeadline = async (operation, run) => {
	const controller = new AbortController();
	let timedOut = false;
	const timeout = setTimeout(() => {
		timedOut = true;
		controller.abort();
	}, AUTH_TOKEN_REQUEST_TIMEOUT_MS);
	try {
		return await run(controller.signal);
	} catch (error) {
		if (timedOut) throw new Error(`Assistant Cloud ${operation} timed out after ${AUTH_TOKEN_REQUEST_TIMEOUT_MS}ms`, { cause: error });
		throw error;
	} finally {
		clearTimeout(timeout);
	}
};
const getJwtExpiry = (jwt) => {
	try {
		const bodyPart = jwt.split(".")[1];
		if (!bodyPart) throw new Error("Invalid JWT format");
		let base64 = bodyPart.replace(/-/g, "+").replace(/_/g, "/");
		while (base64.length % 4 !== 0) base64 += "=";
		const payload = atob(base64);
		const exp = JSON.parse(payload).exp;
		if (!exp || typeof exp !== "number") throw new Error("JWT does not contain a valid \"exp\" field");
		return exp * 1e3;
	} catch (error) {
		throw new Error(`Unable to determine the token expiry: ${error}`);
	}
};
const readNonEmptyCloudString = (value, field) => {
	const result = readCloudString(value, field);
	if (result.length === 0) throw new CloudResponseError(`Invalid Assistant Cloud response for "${field}": expected a non-empty string`);
	return result;
};
const readRefreshTokenResponse = (value, field) => {
	const refreshToken = readCloudRecord(value, field);
	return {
		token: readNonEmptyCloudString(refreshToken.token, `${field}.token`),
		expires_at: readNonEmptyCloudString(refreshToken.expires_at, `${field}.expires_at`)
	};
};
const readAuthTokenResponse = async (response, field) => {
	let value;
	try {
		value = await response.json();
	} catch {
		throw new CloudResponseError(`Invalid Assistant Cloud response for "${field}": expected valid JSON`);
	}
	const data = readCloudRecord(value, field);
	return {
		data,
		accessToken: readNonEmptyCloudString(data.access_token, `${field}.access_token`)
	};
};
var AssistantCloudJWTAuthStrategy = class {
	strategy = "jwt";
	cachedToken = null;
	tokenExpiry = null;
	tokenRequest = null;
	#authTokenCallback;
	constructor(authTokenCallback) {
		this.#authTokenCallback = authTokenCallback;
	}
	async getAuthHeaders() {
		const currentTime = Date.now();
		if (this.cachedToken && this.tokenExpiry && this.tokenExpiry - currentTime > 3e4) return { Authorization: `Bearer ${this.cachedToken}` };
		if (!this.tokenRequest) this.tokenRequest = this.fetchAuthHeaders();
		const tokenRequest = this.tokenRequest;
		try {
			return await tokenRequest;
		} finally {
			if (this.tokenRequest === tokenRequest) this.tokenRequest = null;
		}
	}
	async fetchAuthHeaders() {
		const token = await this.#authTokenCallback();
		if (!token) return false;
		const tokenExpiry = getJwtExpiry(token);
		this.cachedToken = token;
		this.tokenExpiry = tokenExpiry;
		return { Authorization: `Bearer ${token}` };
	}
	readAuthHeaders(headers) {
		const authHeader = headers.get("Authorization");
		if (!authHeader) return;
		const [scheme, token] = authHeader.split(" ");
		if (scheme !== "Bearer" || !token) throw new Error("Invalid auth header received");
		const tokenExpiry = getJwtExpiry(token);
		this.cachedToken = token;
		this.tokenExpiry = tokenExpiry;
	}
};
var AssistantCloudAPIKeyAuthStrategy = class {
	strategy = "api-key";
	#apiKey;
	#userId;
	#workspaceId;
	constructor(apiKey, userId, workspaceId) {
		this.#apiKey = apiKey;
		this.#userId = userId;
		this.#workspaceId = workspaceId;
	}
	async getAuthHeaders() {
		return {
			Authorization: `Bearer ${this.#apiKey}`,
			"Aui-User-Id": this.#userId,
			"Aui-Workspace-Id": this.#workspaceId
		};
	}
	readAuthHeaders() {}
};
const LEGACY_AUI_REFRESH_TOKEN_NAME = "aui:refresh_token";
const getRefreshTokenName = (baseUrl) => `${LEGACY_AUI_REFRESH_TOKEN_NAME}:${baseUrl}`;
const removeLegacyRefreshToken = (storage) => {
	try {
		storage.removeItem(LEGACY_AUI_REFRESH_TOKEN_NAME);
	} catch {}
};
const getLocalStorage = () => {
	if (!("localStorage" in globalThis)) return null;
	try {
		return globalThis.localStorage;
	} catch {
		return null;
	}
};
const readRefreshToken = (baseUrl) => {
	const storage = getLocalStorage();
	if (!storage) return void 0;
	try {
		const name = getRefreshTokenName(baseUrl);
		const value = storage.getItem(name);
		if (value) {
			removeLegacyRefreshToken(storage);
			return JSON.parse(value);
		}
		const legacyValue = storage.getItem(LEGACY_AUI_REFRESH_TOKEN_NAME);
		if (!legacyValue) return void 0;
		let refreshToken;
		try {
			refreshToken = JSON.parse(legacyValue);
		} catch {
			removeLegacyRefreshToken(storage);
			return;
		}
		storage.setItem(name, legacyValue);
		removeLegacyRefreshToken(storage);
		return refreshToken;
	} catch {
		return;
	}
};
const normalizeBaseUrl = (baseUrl) => {
	if (!baseUrl || !baseUrl.endsWith("/")) return baseUrl;
	return baseUrl.slice(0, -1);
};
/** The refresh token of the anonymous identity this browser holds for `baseUrl`, or null when it has none. */
const readAnonymousRefreshToken = (baseUrl) => {
	const refreshToken = readRefreshToken(normalizeBaseUrl(baseUrl));
	if (!refreshToken) return null;
	return new Date(refreshToken.expires_at).getTime() - Date.now() > 3e4 ? refreshToken.token : null;
};
const writeRefreshToken = (baseUrl, refreshToken) => {
	const storage = getLocalStorage();
	if (!storage) return;
	try {
		storage.setItem(getRefreshTokenName(baseUrl), JSON.stringify(refreshToken));
	} catch {}
};
const removeRefreshToken = (baseUrl) => {
	const storage = getLocalStorage();
	if (!storage) return;
	try {
		storage.removeItem(getRefreshTokenName(baseUrl));
	} catch {}
};
const anonymousAuthTokenRequests = /* @__PURE__ */ new WeakMap();
const getWebLockManager = () => {
	if (!("navigator" in globalThis)) return null;
	return globalThis.navigator?.locks ?? null;
};
const getAnonymousAuthLockName = (baseUrl) => `assistant-cloud:anonymous-auth:${baseUrl}`;
const getSharedAnonymousAuthToken = (baseUrl, requestToken) => {
	const storage = getLocalStorage();
	if (!storage) return requestToken();
	let storageRequests = anonymousAuthTokenRequests.get(storage);
	if (!storageRequests) {
		storageRequests = /* @__PURE__ */ new Map();
		anonymousAuthTokenRequests.set(storage, storageRequests);
	}
	const activeRequest = storageRequests.get(baseUrl);
	if (activeRequest) return activeRequest;
	const locks = getWebLockManager();
	const sharedRequest = (locks ? locks.request(getAnonymousAuthLockName(baseUrl), requestToken) : requestToken()).finally(() => {
		if (storageRequests.get(baseUrl) === sharedRequest) storageRequests.delete(baseUrl);
	});
	storageRequests.set(baseUrl, sharedRequest);
	return sharedRequest;
};
var AssistantCloudAnonymousAuthStrategy = class {
	strategy = "anon";
	baseUrl;
	jwtStrategy;
	constructor(baseUrl) {
		this.baseUrl = baseUrl;
		const requestAuthToken = async () => {
			const currentTime = Date.now();
			const storedRefreshToken = readRefreshToken(this.baseUrl);
			if (storedRefreshToken) {
				if (new Date(storedRefreshToken.expires_at).getTime() - currentTime > 3e4) {
					const refreshedAccessToken = await withAuthTokenDeadline("refresh token request", async (signal) => {
						const response = await fetch(`${this.baseUrl}/v1/auth/tokens/refresh`, {
							method: "POST",
							headers: { "Content-Type": "application/json" },
							body: JSON.stringify({ refresh_token: storedRefreshToken.token }),
							signal
						});
						if (response.ok) {
							const { data, accessToken } = await readAuthTokenResponse(response, "refresh auth token response");
							if (data.refresh_token != null) writeRefreshToken(this.baseUrl, readRefreshTokenResponse(data.refresh_token, "refresh auth token response.refresh_token"));
							return accessToken;
						}
						if (response.status === 429 || response.status >= 500) throw new Error(`Assistant Cloud token refresh failed with status ${response.status}`);
						return null;
					});
					if (refreshedAccessToken !== null) return refreshedAccessToken;
				} else removeRefreshToken(this.baseUrl);
			}
			return withAuthTokenDeadline("anonymous token request", async (signal) => {
				const response = await fetch(`${this.baseUrl}/v1/auth/tokens/anonymous`, {
					method: "POST",
					signal
				});
				if (!response.ok) return null;
				const { data, accessToken } = await readAuthTokenResponse(response, "anonymous auth token response");
				writeRefreshToken(this.baseUrl, readRefreshTokenResponse(data.refresh_token, "anonymous auth token response.refresh_token"));
				return accessToken;
			});
		};
		this.jwtStrategy = new AssistantCloudJWTAuthStrategy(() => getSharedAnonymousAuthToken(this.baseUrl, requestAuthToken));
	}
	async getAuthHeaders() {
		return this.jwtStrategy.getAuthHeaders();
	}
	readAuthHeaders(headers) {
		this.jwtStrategy.readAuthHeaders(headers);
	}
};
//#endregion
export { AssistantCloudAPIKeyAuthStrategy, AssistantCloudAnonymousAuthStrategy, AssistantCloudJWTAuthStrategy, normalizeBaseUrl, readAnonymousRefreshToken };
