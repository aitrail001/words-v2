import { TextDecoder, TextEncoder } from "node:util";
import "@testing-library/jest-dom";

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

const locationImpl = (window.location as unknown as Record<symbol, any>)[implSymbol];

const updateLocation = (url: string): void => {
  const parsedUrl = locationImpl._relevantDocument.encodingParseAURL(url);

  if (parsedUrl === null) {
    throw new TypeError(`Could not resolve "${url}" against the current document URL`);
  }

  locationImpl._relevantDocument._URL = parsedUrl;
};

locationImpl.assign = function assign(url: string): void {
  updateLocation(url);
};

locationImpl.replace = function replace(url: string): void {
  updateLocation(url);
};
