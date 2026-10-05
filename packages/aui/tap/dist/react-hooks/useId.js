import { useRef } from "./useRef.js";
//#region src/react-hooks/useId.ts
let nextId = 0;
const useId = () => {
	const ref = useRef(null);
	ref.current ??= `:tap${nextId++}:`;
	return ref.current;
};
//#endregion
export { useId };
