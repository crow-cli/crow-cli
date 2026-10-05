import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitives/composer/ComposerIf.tsx
const useComposerIf = (props) => {
	const $ = c(3);
	let t0;
	if ($[0] !== props.dictation || $[1] !== props.editing) {
		t0 = (s) => {
			if (props.editing === true && !s.composer.isEditing) return false;
			if (props.editing === false && s.composer.isEditing) return false;
			const isDictating = s.composer.dictation != null;
			if (props.dictation === true && !isDictating) return false;
			if (props.dictation === false && isDictating) return false;
			return true;
		};
		$[0] = props.dictation;
		$[1] = props.editing;
		$[2] = t0;
	} else t0 = $[2];
	return useAuiState(t0);
};
/**
* @deprecated Use `<AuiIf condition={(s) => s.composer...} />` instead.
*/
const ComposerPrimitiveIf = (t0) => {
	const $ = c(3);
	let children;
	let query;
	if ($[0] !== t0) {
		({children, ...query} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = query;
	} else {
		children = $[1];
		query = $[2];
	}
	return useComposerIf(query) ? children : null;
};
ComposerPrimitiveIf.displayName = "ComposerPrimitive.If";
//#endregion
export { ComposerPrimitiveIf };
