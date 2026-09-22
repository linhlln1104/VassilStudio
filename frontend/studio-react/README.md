# VassilStudio UI

Production React interface for VassilStudio. The build output is served by the FastAPI backend from `/studio`.
Use Node.js 24, matching `.node-version`, CI, and the Docker build stage.

## Commands

```powershell
npm.cmd install
npm.cmd run lint
npm.cmd run build
```

The Vite dev server is useful while iterating on UI:

```powershell
npm.cmd run dev
```

The development proxy forwards API requests, realtime WebSockets, health/readiness, diagnostics,
and model controls to `http://127.0.0.1:8000`. Set `VASSIL_API_TARGET` in the shell or Vite's local
environment file when using another backend address, for example:

```powershell
$env:VASSIL_API_TARGET = "http://127.0.0.1:8018"
npm.cmd run dev
```

The repository quality gate builds Studio and runs browser QA against an isolated temporary backend
workspace. Models are disabled, and no existing owner account, voices, jobs, or runtime config are used.
From the repository root, run the browser suite on an existing build with:

```powershell
python -m pip install -e ".[test,qa]"
python scripts/browser_qa.py --install-browser
```

`--install-browser` installs Playwright Chromium. Omit it to use installed Chrome, or set
`PLAYWRIGHT_CHANNEL` / `PLAYWRIGHT_EXECUTABLE_PATH`. Reports and screenshots go to
`artifacts/ui-qa/gate/`. The suite covers landing, audio workflows, jobs, voice intake, transcript
review, settings, and browser regressions. API fixtures make UI state checks deterministic; real
model E2E and language quality remain separate release checks.

On Windows, `scripts/check.ps1` resolves Node and npm from the same installation and adds that
directory to child-process `PATH`. Set `VASSIL_NODE_PATH` to `node.exe` for a custom installation.
`-SkipBrowser` is available for a focused local gate; CI runs the browser suite.
