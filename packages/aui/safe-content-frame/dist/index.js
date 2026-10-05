//#region src/index.ts
const SHIM_LOAD_ERROR_CODES = [
	"shim-unavailable",
	"shim-error",
	"render-timeout"
];
function shimLoadError(code, message) {
	return Object.assign(new Error(message), { code });
}
/**
* Narrows a rejection from `fullyLoadedPromiseWithTimeout`. The promise also
* rejects with plain errors that carry no code, so a bare property read is not
* enough to tell why a frame failed. Membership of the code set is the test
* rather than `instanceof`, which does not survive a duplicated copy of this
* package in a consumer's bundle.
*/
function isShimLoadError(error) {
	return error instanceof Error && SHIM_LOAD_ERROR_CODES.includes(error.code);
}
const SCF_HOST = "scf.auiusercontent.com";
const PRODUCT_HASH = "h184756";
async function sha256(data) {
	return crypto.subtle.digest("SHA-256", data);
}
async function computeOriginHash(product, salt, origin) {
	const enc = new TextEncoder();
	const sep = enc.encode("$@#|");
	const parts = [
		enc.encode(product),
		sep,
		new Uint8Array(salt),
		sep,
		enc.encode(origin)
	];
	const combined = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
	let offset = 0;
	for (const p of parts) {
		combined.set(p, offset);
		offset += p.length;
	}
	return new Uint8Array(await sha256(combined.buffer)).reduce((acc, b) => BigInt(256) * acc + BigInt(b), BigInt(0)).toString(36).padStart(50, "0").slice(0, 50);
}
function randomSalt() {
	const arr = /* @__PURE__ */ new Uint8Array(10);
	crypto.getRandomValues(arr);
	return arr.buffer;
}
async function contentSalt(content, pathname) {
	const enc = new TextEncoder();
	const sep = enc.encode("$@#|");
	const encodedPathname = enc.encode(pathname);
	const combined = new Uint8Array(content.length + sep.length + encodedPathname.length);
	combined.set(content, 0);
	combined.set(sep, content.length);
	combined.set(encodedPathname, content.length + sep.length);
	return sha256(combined.buffer);
}
var SafeContentFrame = class {
	product;
	options;
	constructor(product, options = {}) {
		this.product = product;
		this.options = options;
	}
	async renderHtml(html, container, opts) {
		return this.render(new TextEncoder().encode(html), "text/html; charset=utf-8", container, opts);
	}
	async renderRaw(content, mimeType, container) {
		const data = typeof content === "string" ? new TextEncoder().encode(content) : content;
		return this.render(data, mimeType, container);
	}
	async renderPdf(content, container) {
		return this.render(content, "application/pdf", container);
	}
	async render(content, mimeType, container, opts) {
		const origin = window.location.origin;
		const salt = this.options.salt ? new TextEncoder().encode(this.options.salt).buffer : this.options.enableBrowserCaching ? await contentSalt(content, location.pathname) : randomSalt();
		const shimUrl = `https://${await computeOriginHash(this.product, salt, origin)}-${PRODUCT_HASH}.${SCF_HOST}/${this.product}/shim.html?origin=${encodeURIComponent(origin)}${this.options.enableBrowserCaching ? "&cache=1" : ""}`;
		const iframeOrigin = new URL(shimUrl).origin;
		const iframe = document.createElement("iframe");
		iframe.setAttribute("sandbox", this.getSandbox());
		iframe.style.cssText = "border:none;width:100%;height:100%";
		let mountElement = iframe;
		if (this.options.useShadowDom) {
			const host = document.createElement("div");
			host.attachShadow({ mode: "closed" }).appendChild(iframe);
			container.appendChild(host);
			mountElement = host;
		} else container.appendChild(iframe);
		return new Promise((resolve, reject) => {
			const channel = new MessageChannel();
			let channelTransferred = false;
			let cleanedUp = false;
			let shimReady = false;
			let onLoaded;
			let onLoadError;
			const loaded = new Promise((resolveLoaded, rejectLoaded) => {
				onLoaded = resolveLoaded;
				onLoadError = rejectLoaded;
			});
			loaded.catch(() => {});
			const onWindowMessage = (event) => {
				if (event.origin !== iframeOrigin) return;
				if (event.source !== iframe.contentWindow) return;
				if (event.data?.type === "ready") shimReady = true;
				else if (event.data?.type === "error") onLoadError(shimLoadError("shim-error", event.data.message));
			};
			window.addEventListener("message", onWindowMessage);
			const cleanup = () => {
				if (cleanedUp) return;
				cleanedUp = true;
				iframe.onload = null;
				iframe.onerror = null;
				window.removeEventListener("message", onWindowMessage);
				channel.port1.onmessage = null;
				channel.port1.close();
				if (!channelTransferred) channel.port2.close();
				mountElement.remove();
			};
			channel.port1.onmessage = (e) => {
				if (e.data?.type === "msg") onLoaded();
				else if (e.data?.type === "error") {
					onLoadError(shimLoadError("shim-error", e.data.message));
					cleanup();
				}
			};
			let loadHandled = false;
			iframe.onload = () => {
				if (loadHandled) return;
				loadHandled = true;
				try {
					const contentWindow = iframe.contentWindow;
					if (!contentWindow) throw new Error("Failed to access iframe window");
					contentWindow.postMessage({
						body: content.buffer.slice(content.byteOffset, content.byteOffset + content.byteLength),
						mimeType,
						salt,
						unsafeDocumentWrite: opts?.unsafeDocumentWrite
					}, iframeOrigin, [channel.port2]);
					channelTransferred = true;
				} catch (error) {
					cleanup();
					reject(error);
					return;
				}
				iframe.onload = null;
				iframe.onerror = null;
				resolve({
					iframe,
					origin: iframeOrigin,
					sendMessage: (data, transfer) => iframe.contentWindow?.postMessage(data, iframeOrigin, transfer),
					fullyLoadedPromiseWithTimeout: async (ms) => {
						let timeout;
						try {
							await Promise.race([loaded, new Promise((_, reject) => {
								timeout = setTimeout(() => reject(shimReady ? shimLoadError("render-timeout", "Timeout") : shimLoadError("shim-unavailable", `Failed to load shim: ${shimUrl}`)), ms);
							})]);
						} finally {
							if (timeout !== void 0) clearTimeout(timeout);
						}
					},
					dispose: cleanup
				});
			};
			iframe.onerror = () => {
				cleanup();
				reject(/* @__PURE__ */ new Error("Failed to load iframe"));
			};
			iframe.src = shimUrl;
		});
	}
	getSandbox() {
		const s = new Set(this.options.sandbox || []);
		s.add("allow-same-origin");
		s.add("allow-scripts");
		return [...s].join(" ");
	}
};
//#endregion
export { SafeContentFrame, isShimLoadError };
