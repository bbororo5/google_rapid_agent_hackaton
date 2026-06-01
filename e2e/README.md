# Playwright E2E Tests

These tests are executable acceptance criteria for the frontend implementation.

The frontend app does not exist yet, so `npm run test:e2e` is expected to fail until a Next.js app is scaffolded and served at `FRONTEND_URL` or `http://127.0.0.1:3000`.

The first E2E spec uses contract fixtures as mocked API responses. This keeps the browser flow tied to the same contracts used by Java and Python.

Useful commands:

```sh
npm run test:e2e:list
npm run test:e2e
npm run test:e2e:ui
```

When frontend implementation starts, the first target is to make `main-analysis-approval.mock.spec.ts` pass.
