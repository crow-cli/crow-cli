import { WritableSubscribable } from "../../subscribable/subscribable.js";
import { useSubscribable } from "../../store/runtime-clients/useSubscribable.js";
import { useCallback, useEffect, useState } from "@assistant-ui/tap/react-shim";
//#region src/react/model-context/useInlineRender.ts
const useInlineRender = (toolUI) => {
	const [toolUIStore] = useState(() => new WritableSubscribable(toolUI));
	useEffect(() => {
		toolUIStore.setState(toolUI);
	}, [toolUI, toolUIStore]);
	return useCallback(function ToolUI(args) {
		return useSubscribable(toolUIStore)(args);
	}, [toolUIStore]);
};
//#endregion
export { useInlineRender };
