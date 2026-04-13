# Next.js 16 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the learner and admin Next.js apps from 15.x to `^16.2.0`, remove deprecated file conventions, and adopt low-risk Next 16 performance improvements that fit the current codebase.

**Architecture:** Keep the existing App Router structure and repo-owned CI flow intact. Apply the upgrade in two focused slices: first dependency/runtime migration, then performance-oriented config adoption with verification on both apps.

**Tech Stack:** Next.js 16.2.x, React 19, TypeScript, Jest, Playwright, repo `make` gates.

---

## File Map

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/next.config.ts`
- Create: `frontend/proxy.ts`
- Delete: `frontend/src/middleware.ts`
- Modify: `frontend/src/app/__tests__/page.test.tsx`
- Create: `frontend/src/__tests__/proxy.test.ts`
- Modify: `admin-frontend/package.json`
- Modify: `admin-frontend/package-lock.json`
- Modify: `admin-frontend/next.config.ts`
- Create: `admin-frontend/proxy.ts`
- Delete: `admin-frontend/middleware.ts`
- Modify: `admin-frontend/src/app/__tests__/page.test.tsx`
- Create: `admin-frontend/src/__tests__/proxy.test.ts`

### Task 1: Upgrade Next.js Dependencies And Capture RED/GREEN

**Files:**
- Modify: `frontend/package.json`
- Modify: `admin-frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `admin-frontend/package-lock.json`
- Test: `frontend/src/__tests__/proxy.test.ts`
- Test: `admin-frontend/src/__tests__/proxy.test.ts`

- [ ] **Step 1: Write the failing proxy migration tests**

```ts
import { NextRequest } from "next/server";
import { proxy } from "../proxy";

describe("proxy", () => {
  it("redirects unauthenticated protected requests", () => {
    const request = new NextRequest("http://localhost/imports");
    const response = proxy(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost/login?next=%2Fimports");
  });

  it("allows authenticated protected requests", () => {
    const request = new NextRequest("http://localhost/imports", {
      headers: {
        cookie: "words_access_token=test-token",
      },
    });
    const response = proxy(request);

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
```

- [ ] **Step 2: Run the new tests to confirm RED**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/proxy.test.ts
cd admin-frontend && npm test -- --runInBand src/__tests__/proxy.test.ts
```

Expected:
```text
FAIL ... Cannot find module '../proxy'
```

- [ ] **Step 3: Update package manifests to Next 16.2**

```json
{
  "dependencies": {
    "next": "^16.2.0"
  },
  "devDependencies": {
    "eslint-config-next": "^16.2.0"
  }
}
```

- [ ] **Step 4: Refresh lockfiles**

Run:
```bash
cd frontend && npm install
cd admin-frontend && npm install
```

Expected:
```text
added/changed packages...
next 16.2.x
eslint-config-next 16.2.x
```

- [ ] **Step 5: Commit the RED checkpoint**

```bash
git add frontend/src/__tests__/proxy.test.ts admin-frontend/src/__tests__/proxy.test.ts frontend/package.json admin-frontend/package.json
git commit -m "test: add next16 proxy migration reproducers"
```

### Task 2: Replace Deprecated Middleware With Proxy

**Files:**
- Create: `frontend/proxy.ts`
- Delete: `frontend/src/middleware.ts`
- Create: `admin-frontend/proxy.ts`
- Delete: `admin-frontend/middleware.ts`
- Modify: `frontend/src/app/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/__tests__/page.test.tsx`
- Test: `frontend/src/__tests__/proxy.test.ts`
- Test: `admin-frontend/src/__tests__/proxy.test.ts`

- [ ] **Step 1: Implement the renamed file convention**

```ts
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE_KEY } from "./src/lib/auth-session";
import { getAuthRedirectPath } from "./src/lib/auth-route-guard";

export function proxy(request: NextRequest) {
  const isAuthenticated = Boolean(
    request.cookies.get(ACCESS_TOKEN_COOKIE_KEY)?.value,
  );
  const redirectPath = getAuthRedirectPath(
    request.nextUrl.pathname,
    isAuthenticated,
  );

  if (!redirectPath) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL(redirectPath, request.url));
}

export const config = {
  matcher: ["/", "/lexicon/:path*"],
};
```

- [ ] **Step 2: Update wording in existing auth tests from middleware to proxy**

```ts
describe("Auth proxy", () => {
  it("redirects unauthenticated requests to /login", () => {
    expect(getAuthRedirectPath("/", false)).toBe("/login?next=%2F");
  });
});
```

- [ ] **Step 3: Run the targeted tests to confirm GREEN**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/proxy.test.ts src/app/__tests__/page.test.tsx
cd admin-frontend && npm test -- --runInBand src/__tests__/proxy.test.ts src/app/__tests__/page.test.tsx
```

Expected:
```text
PASS
```

- [ ] **Step 4: Commit the GREEN checkpoint**

```bash
git add frontend/proxy.ts frontend/src/middleware.ts frontend/src/__tests__/proxy.test.ts frontend/src/app/__tests__/page.test.tsx admin-frontend/proxy.ts admin-frontend/middleware.ts admin-frontend/src/__tests__/proxy.test.ts admin-frontend/src/app/__tests__/page.test.tsx
git commit -m "fix: migrate next middleware to proxy"
```

### Task 3: Adopt Low-Risk Next 16 Performance Features

**Files:**
- Modify: `frontend/next.config.ts`
- Modify: `admin-frontend/next.config.ts`
- Modify: `frontend/package.json`
- Modify: `admin-frontend/package.json`
- Test: `frontend/package.json`
- Test: `admin-frontend/package.json`

- [ ] **Step 1: Add the React Compiler dependency and enable it in config**

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  async rewrites() {
    const backendUrl =
      process.env.BACKEND_URL ?? "http://localhost:8000/api";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
```

```json
{
  "devDependencies": {
    "babel-plugin-react-compiler": "^1.0.0"
  }
}
```

- [ ] **Step 2: Install updated dependencies**

Run:
```bash
cd frontend && npm install
cd admin-frontend && npm install
```

Expected:
```text
added 1 package...
```

- [ ] **Step 3: Run lint and build checks for both apps**

Run:
```bash
make lint-frontend
make lint-admin
cd frontend && npm run build
cd admin-frontend && npm run build
```

Expected:
```text
eslint passes
Next.js 16.2.x build succeeds
```

- [ ] **Step 4: Commit the performance/config checkpoint**

```bash
git add frontend/next.config.ts admin-frontend/next.config.ts frontend/package.json admin-frontend/package.json frontend/package-lock.json admin-frontend/package-lock.json
git commit -m "refactor: enable next16 performance defaults"
```

### Task 4: Final Verification And Repo Wrap-Up

**Files:**
- Modify: `graphify-out/` (generated output)

- [ ] **Step 1: Run repo-local frontend verification**

Run:
```bash
make test-frontend
make test-admin
```

Expected:
```text
PASS
```

- [ ] **Step 2: Run the canonical readiness gate**

Run:
```bash
make gate-fast
```

Expected:
```text
gate-fast passed
```

- [ ] **Step 3: Rebuild the graphify knowledge graph**

Run:
```bash
uv run --with graphifyy python3.13 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

Expected:
```text
graph rebuild completed
```

- [ ] **Step 4: Summarize what ran and what did not run**

```text
Ran: make test-frontend, make test-admin, make gate-fast
Not run: make gate-full (unless explicitly needed before PR)
```
