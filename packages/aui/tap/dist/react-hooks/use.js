import { useContext } from "../core/context.js";
import { isThenable, trackThenable } from "../core/helpers/thenable.js";
//#region src/react-hooks/use.ts
/**
* The tap equivalent of React's `use`. Accepts React contexts and thenables:
* a context read returns its current value; a pending promise suspends the
* render by throwing the thenable, a settled one returns its value or throws
* its rejection reason.
*/
const use = (usable) => {
	if (isThenable(usable)) return trackThenable(usable);
	return useContext(usable);
};
//#endregion
export { use };
