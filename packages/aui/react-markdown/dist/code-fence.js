//#region src/code-fence.ts
const parseLanguageClass = (className) => /language-([^\s]+)/.exec(className ?? "")?.[1] ?? "";
//#endregion
export { parseLanguageClass };
