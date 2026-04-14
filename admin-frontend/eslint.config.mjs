import nextVitals from "eslint-config-next/core-web-vitals";

function addGetFilenameCompat(rule) {
  if (typeof rule.create !== "function") {
    return rule;
  }

  return {
    ...rule,
    create(context) {
      if (typeof context.getFilename === "function") {
        return rule.create(context);
      }

      const compatContext = new Proxy(context, {
        get(target, property, receiver) {
          if (property === "getFilename") {
            return () => target.filename ?? "<unknown>";
          }

          return Reflect.get(target, property, receiver);
        },
      });

      return rule.create(compatContext);
    },
  };
}

function addGlobalsCompat(scopeManager, names) {
  const globalScope = scopeManager.scopes?.[0];

  if (!globalScope?.set) {
    return;
  }

  for (const name of names) {
    if (globalScope.set.has(name)) {
      continue;
    }

    const variable = {
      name,
      defs: [],
      identifiers: [],
      references: [],
      eslintImplicitGlobalSetting: undefined,
      eslintExplicitGlobal: false,
      eslintExplicitGlobalComments: undefined,
      writeable: true,
    };

    globalScope.set.set(name, variable);

    if (Array.isArray(globalScope.variables)) {
      globalScope.variables.push(variable);
    }
  }
}

function patchParser(parser) {
  if (typeof parser.parseForESLint !== "function") {
    return parser;
  }

  return {
    ...parser,
    parseForESLint(code, options) {
      const result = parser.parseForESLint(code, options);

      if (
        result.scopeManager &&
        typeof result.scopeManager.addGlobals !== "function"
      ) {
        result.scopeManager.addGlobals = (names) => addGlobalsCompat(result.scopeManager, names);
      }

      return result;
    },
  };
}

function patchReactPlugin(plugin) {
  return {
    ...plugin,
    rules: Object.fromEntries(
      Object.entries(plugin.rules).map(([name, rule]) => [name, addGetFilenameCompat(rule)]),
    ),
  };
}

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**"],
  },
  ...nextVitals.map((config) =>
    config.plugins?.react || config.languageOptions?.parser
      ? {
          ...config,
          languageOptions: config.languageOptions?.parser
            ? {
                ...config.languageOptions,
                parser: patchParser(config.languageOptions.parser),
              }
            : config.languageOptions,
          plugins: config.plugins?.react
            ? {
                ...config.plugins,
                react: patchReactPlugin(config.plugins.react),
              }
            : config.plugins,
        }
      : config,
  ),
];

export default eslintConfig;
