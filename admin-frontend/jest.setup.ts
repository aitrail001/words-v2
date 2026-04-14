import { TextDecoder, TextEncoder } from "node:util";
import "@testing-library/jest-dom";
import {
  recordLocationAssign,
  recordLocationReplace,
  resetLocationSpies,
} from "./src/test/location-spies";

if (typeof globalThis.TextEncoder === "undefined") {
  globalThis.TextEncoder = TextEncoder;
}

if (typeof globalThis.TextDecoder === "undefined") {
  globalThis.TextDecoder = TextDecoder;
}

const implSymbol = Object.getOwnPropertySymbols(window.location).find(
  (symbol) => symbol.description === "impl",
);

if (!implSymbol) {
  throw new Error("Unable to locate the jsdom Location implementation symbol");
}

const locationImpl = (window.location as unknown as Record<symbol, { assign?: (url: string) => void; replace?: (url: string) => void }>)[implSymbol];
const locationImplProto = Object.getPrototypeOf(locationImpl);

locationImplProto.assign = function assign(url: string): void {
  recordLocationAssign(url);
};

locationImplProto.replace = function replace(url: string): void {
  recordLocationReplace(url);
};

const registerBeforeEach = (globalThis as { beforeEach?: (callback: () => void) => void }).beforeEach;

if (typeof registerBeforeEach === "function") {
  registerBeforeEach(() => {
    resetLocationSpies();
  });
}
