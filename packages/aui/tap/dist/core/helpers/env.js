//#region src/core/helpers/env.ts
const isDevelopment = typeof process !== "undefined" && (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test");
//#endregion
export { isDevelopment };
