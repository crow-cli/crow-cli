//#region src/core/helpers/thenable.ts
const isThenable = (value) => value !== null && typeof value === "object" && typeof value.then === "function";
const noop = () => {};
const trackThenable = (thenable) => {
	const tracked = thenable;
	if (typeof tracked.status !== "string") {
		tracked.status = "pending";
		thenable.then((value) => {
			if (tracked.status === "pending") {
				tracked.status = "fulfilled";
				tracked.value = value;
			}
		}, (reason) => {
			if (tracked.status === "pending") {
				tracked.status = "rejected";
				tracked.reason = reason;
			}
		});
	} else if (tracked.status !== "fulfilled" && tracked.status !== "rejected") thenable.then(noop, noop);
	switch (tracked.status) {
		case "fulfilled": return tracked.value;
		case "rejected": throw tracked.reason;
		default: throw thenable;
	}
};
//#endregion
export { isThenable, trackThenable };
