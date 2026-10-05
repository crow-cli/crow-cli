import { commitResourceFiber, renderResourceFiber } from "../core/ResourceFiber.js";
import { useHostLifecycle, useResourceFiberHost } from "./utils/useResourceFiberHostUtils.js";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
//#region src/hooks/useTapHost.ts
const useHostRender = (render) => render();
const useTapHost = (callback) => {
	const { createFiber } = useResourceFiberHost();
	const [fiber] = useState(() => createFiber(useHostRender, void 0));
	const render = renderResourceFiber(fiber, [callback]);
	useHostLifecycle(fiber);
	let renderCommitted = false;
	const effects = () => {
		if (renderCommitted && fiber.isMounted) return;
		renderCommitted = true;
		commitResourceFiber(fiber);
	};
	useEffect(effects);
	return {
		value: render,
		effects
	};
};
//#endregion
export { useTapHost };
