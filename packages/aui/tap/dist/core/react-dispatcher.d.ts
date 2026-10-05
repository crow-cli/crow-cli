/**
 * Runs a resource body with tap's React dispatcher installed, so real React
 * hooks called inside it (`import { useState } from "react"`) route to tap, then
 * restores the previous dispatcher. If React's internal dispatcher slot can't be
 * found (an unsupported React version), the body runs unchanged and `react`
 * hooks inside it keep throwing React's "invalid hook call".
 */
export declare function withReactDispatcher<T>(render: () => T): T;