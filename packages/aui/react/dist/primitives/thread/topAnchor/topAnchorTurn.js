"use client";
//#region src/primitives/thread/topAnchor/topAnchorTurn.ts
/**
* A stored turn stays valid only while it is still the trailing turn: the
* anchor immediately precedes the target, and anything after the target is a
* pending user message awaiting the next run. An assistant message after the
* target means the turn was superseded (e.g. an external store synced in a
* turn completed elsewhere), so the reserve must be torn down, not preserved.
*/
const isTopAnchorTurnValid = (turn, messages) => {
	if (!turn) return false;
	const targetIndex = messages.findIndex((message) => message.id === turn.targetId);
	if (targetIndex < 1) return false;
	return messages[targetIndex - 1]?.id === turn.anchorId && messages.slice(targetIndex + 1).every((message) => message.role === "user");
};
const getActiveTopAnchorTurn = ({ isRunning, messages }) => {
	if (!isRunning) return null;
	const target = messages.at(-1);
	const anchor = messages.at(-2);
	if (anchor?.role !== "user" || target?.role !== "assistant") return null;
	return {
		anchorId: anchor.id,
		targetId: target.id
	};
};
const getActiveTopAnchorAnchorId = (options) => getActiveTopAnchorTurn(options)?.anchorId;
const getActiveTopAnchorTargetId = (options) => getActiveTopAnchorTurn(options)?.targetId;
//#endregion
export { getActiveTopAnchorAnchorId, getActiveTopAnchorTargetId, getActiveTopAnchorTurn, isTopAnchorTurnValid };
