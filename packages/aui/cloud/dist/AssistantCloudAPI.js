import { AssistantCloudAPIKeyAuthStrategy, AssistantCloudAnonymousAuthStrategy, AssistantCloudJWTAuthStrategy, normalizeBaseUrl } from "./AssistantCloudAuthStrategy.js";
import { ASSISTANT_CLOUD_VERSION } from "./version.js";
//#region src/AssistantCloudAPI.ts
var CloudAPIError = class extends Error {
	status;
	code;
	details;
	constructor(message, status, code, details) {
		super(message);
		this.status = status;
		if (code !== void 0) this.code = code;
		if (details !== void 0) this.details = details;
		this.name = "CloudAPIError";
	}
};
const HEADER_TOKEN = /^[\x21-\x7e]+$/;
var AssistantCloudAPI = class {
	_auth;
	_baseUrl;
	registerSdk;
	sdkHeader;
	constructor(config) {
		const sdks = /* @__PURE__ */ new Map();
		this.registerSdk = (sdk) => {
			const name = sdk.name.trim();
			const version = sdk.version.trim();
			if (!HEADER_TOKEN.test(name) || !HEADER_TOKEN.test(version)) return;
			sdks.set(`${name}/${version}`, {
				name,
				version
			});
		};
		this.sdkHeader = () => [`assistant-cloud/${ASSISTANT_CLOUD_VERSION}`, ...Array.from(sdks.values(), ({ name, version }) => `${name}/${version}`)].join(" ");
		if ("authToken" in config) {
			this._baseUrl = normalizeBaseUrl(config.baseUrl);
			this._auth = new AssistantCloudJWTAuthStrategy(config.authToken);
		} else if ("apiKey" in config) {
			this._baseUrl = normalizeBaseUrl(config.baseUrl ?? "https://backend.assistant-api.com");
			this._auth = new AssistantCloudAPIKeyAuthStrategy(config.apiKey, config.userId, config.workspaceId);
		} else if ("anonymous" in config) {
			this._baseUrl = normalizeBaseUrl(config.baseUrl);
			this._auth = new AssistantCloudAnonymousAuthStrategy(this._baseUrl);
		} else throw new Error("Invalid configuration: Must provide authToken, apiKey, or anonymous configuration");
	}
	async initializeAuth() {
		return !!await this._auth.getAuthHeaders();
	}
	async makeRawRequest(endpoint, options = {}) {
		const authHeaders = await this._auth.getAuthHeaders();
		if (!authHeaders) throw new Error("Authorization failed");
		const headers = {
			...authHeaders,
			...options.headers,
			"Content-Type": "application/json",
			"Aui-Sdk": this.sdkHeader()
		};
		const queryParams = new URLSearchParams();
		if (options.query) for (const [key, value] of Object.entries(options.query)) {
			if (value === false) continue;
			if (value === true) queryParams.set(key, "true");
			else queryParams.set(key, value.toString());
		}
		const url = new URL(`${this._baseUrl}/v1${endpoint}`);
		url.search = queryParams.toString();
		const response = await fetch(url, {
			method: options.method ?? "GET",
			headers,
			body: options.body ? JSON.stringify(options.body) : null,
			...options.keepalive ? { keepalive: true } : {}
		});
		this._auth.readAuthHeaders(response.headers);
		if (!response.ok) {
			const text = await response.text();
			let message;
			let code;
			let details;
			try {
				const body = JSON.parse(text);
				if (typeof body === "object" && body !== null && !Array.isArray(body)) {
					const record = body;
					if (typeof record.message === "string" && record.message.length > 0) message = record.message;
					if (typeof record.error === "string") {
						code = record.error;
						details = { ...record };
						delete details.error;
					}
				}
			} catch {}
			throw new CloudAPIError(message ?? `Request failed with status ${response.status}, ${text}`, response.status, code, details);
		}
		return response;
	}
	async makeRequest(endpoint, options = {}) {
		const response = await this.makeRawRequest(endpoint, options);
		if (response.status === 204 || response.headers.get("content-length") === "0") return void 0;
		const text = await response.text();
		if (text.trim() === "") return void 0;
		return JSON.parse(text);
	}
};
//#endregion
export { AssistantCloudAPI, CloudAPIError };
