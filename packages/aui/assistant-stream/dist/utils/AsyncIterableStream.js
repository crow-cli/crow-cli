//#region src/utils/AsyncIterableStream.ts
async function* streamGeneratorPolyfill() {
	const reader = this.getReader();
	let shouldCancel = true;
	try {
		while (true) {
			let result;
			try {
				result = await reader.read();
			} catch (error) {
				shouldCancel = false;
				throw error;
			}
			if (result.done) {
				shouldCancel = false;
				break;
			}
			const { value } = result;
			yield value;
		}
	} finally {
		try {
			if (shouldCancel) await reader.cancel();
		} finally {
			reader.releaseLock();
		}
	}
}
function asAsyncIterableStream(source) {
	source[Symbol.asyncIterator] ??= streamGeneratorPolyfill;
	return source;
}
//#endregion
export { asAsyncIterableStream };
