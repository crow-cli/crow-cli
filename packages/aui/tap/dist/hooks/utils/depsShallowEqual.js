import { isDevelopment } from "../../core/helpers/env.js";
//#region src/hooks/utils/depsShallowEqual.ts
const depsShallowEqual = (a, b) => {
	if (isDevelopment && a.length !== b.length) console.error(`The final argument passed to a hook changed size between renders. The order and size of this array must remain constant.

Previous: [${a.join(", ")}]\nIncoming: [${b.join(", ")}]`);
	for (let i = 0; i < a.length && i < b.length; i++) if (!Object.is(a[i], b[i])) return false;
	return true;
};
//#endregion
export { depsShallowEqual };
