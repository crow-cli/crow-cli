import { useAssistantDataUI } from "./useAssistantDataUI.js";
//#region src/react/model-context/makeAssistantDataUI.ts
/**
* Creates a React component that registers a named data-part renderer when
* rendered.
*
* @param dataUI - Data renderer registration.
*/
const makeAssistantDataUI = (dataUI) => {
	const DataUI = () => {
		useAssistantDataUI(dataUI);
		return null;
	};
	DataUI.unstable_data = dataUI;
	return DataUI;
};
//#endregion
export { makeAssistantDataUI };
