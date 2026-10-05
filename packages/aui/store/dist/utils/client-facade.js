//#region src/utils/client-facade.ts
/**
* Creates a stable `AssistantClient` facade over a source.
*
* The client object changes identity on structural updates; the facade keeps
* one stable object that always forwards to the source's current client, so a
* binding can hand consumers a single reference for the provider's lifetime.
*/
const createClientFacade = (source) => new Proxy({}, {
	get: (_target, prop) => Reflect.get(source.getClient(), prop),
	has: (_target, prop) => prop in source.getClient(),
	ownKeys: () => {
		const client = source.getClient();
		const keys = new Set(Reflect.ownKeys(client));
		for (const key in client) keys.add(key);
		return [...keys];
	},
	getOwnPropertyDescriptor: (_target, prop) => {
		const client = source.getClient();
		if (!(prop in client)) return void 0;
		return {
			configurable: true,
			enumerable: true,
			value: Reflect.get(client, prop)
		};
	}
});
//#endregion
export { createClientFacade };
