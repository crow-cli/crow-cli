//#region src/core/AssistantStream.ts
const AssistantStream = {
	/**
	* Converts an {@link AssistantStream} into a `Response` using the supplied
	* encoder.
	*
	* The encoder's `headers` are copied onto the response. Pair this with the
	* decoder for the same wire format when consuming the response.
	*/
	toResponse(stream, transformer) {
		return new Response(AssistantStream.toByteStream(stream, transformer), { headers: transformer.headers ?? {} });
	},
	/**
	* Reads an assistant stream from a `Response` body using the supplied
	* decoder.
	*
	* The response body must be present and encoded with the matching assistant
	* stream wire format.
	*/
	fromResponse(response, transformer) {
		return AssistantStream.fromByteStream(response.body, transformer);
	},
	/**
	* Pipes an {@link AssistantStream} through an encoder and returns the
	* resulting byte stream.
	*/
	toByteStream(stream, transformer) {
		return stream.pipeThrough(transformer);
	},
	/**
	* Pipes a byte stream through a decoder and returns normalized
	* {@link AssistantStreamChunk} values.
	*/
	fromByteStream(readable, transformer) {
		return readable.pipeThrough(transformer);
	}
};
//#endregion
export { AssistantStream };
