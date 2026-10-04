# Apex Health web application

This is the production React/Vite interface for Apex Health. Docker builds it
into the FastAPI image, where it is served with the authenticated API.

For local UI development:

```sh
npm ci
npm run dev
```

The Vite development server proxies API requests to the backend on port 8000.
Use the commands below before opening a frontend pull request:

```sh
npm run check:i18n
npm run build
npm run test:ui
```

See the root [installation guide](../docs/INSTALL.md) for the full local stack
and [UI system documentation](../docs/UI_REDESIGN.md) for the product design.
