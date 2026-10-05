//#region src/types/message.ts
const MCP_APP_URI_SCHEME = "ui://";
const isMcpAppUri = (uri) => !!uri?.startsWith(MCP_APP_URI_SCHEME);
/**
* Whether the request asks for a free-form answer, on its own or alongside its
* options. Renderers read this to decide whether to offer a text affordance,
* and the runtime reads it to reject a `text` response the host cannot record.
*/
const toolApprovalAcceptsText = (approval) => approval.display === "text" || approval.allowFreeform === true;
//#endregion
export { MCP_APP_URI_SCHEME, isMcpAppUri, toolApprovalAcceptsText };
