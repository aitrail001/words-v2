import { fixupConfigRules } from "@eslint/compat";
import nextVitals from "eslint-config-next/core-web-vitals";

const wrapParser = (parser) => ({
  ...parser,
  parseForESLint(code, options) {
    const result = parser.parseForESLint(code, options);

    if (
      result.scopeManager &&
      typeof result.scopeManager.addGlobals !== "function"
    ) {
      Object.defineProperty(result.scopeManager, "addGlobals", {
        configurable: true,
        value(names) {
          const globalScope = result.scopeManager.scopes?.[0];

          if (!globalScope?.set) {
            return;
          }

          for (const name of names) {
            if (globalScope.set.has(name)) {
              continue;
            }

            const variable = {
              defs: [],
              eslintExplicitGlobal: false,
              eslintExplicitGlobalComments: undefined,
              eslintImplicitGlobalSetting: undefined,
              identifiers: [],
              name,
              references: [],
              writeable: false,
            };

            globalScope.set.set(name, variable);

            if (Array.isArray(globalScope.variables)) {
              globalScope.variables.push(variable);
            }
          }
        },
        writable: true,
      });
    }

    return result;
  },
});

const fixedNextVitals = fixupConfigRules(
  nextVitals.map((config) => {
    const parser = config.languageOptions?.parser;

    if (!parser) {
      return config;
    }

    return {
      ...config,
      languageOptions: {
        ...config.languageOptions,
        parser: wrapParser(parser),
      },
    };
  }),
);

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**"],
  },
  ...fixedNextVitals,
];

export default eslintConfig;
