/**
 * Electron Main Process — Blueprint
 * ──────────────────────────────────
 * Thin shell that:
 *   1. Starts the Vite dev server (frontend) + FastAPI (backend) as child processes
 *   2. Opens a BrowserWindow pointing to localhost
 *   3. Manages lifecycle (quit, restart)
 *
 * Build with:  npm run electron:build
 * Dev with:    npm run electron:dev
 */

const { app, BrowserWindow, shell, Menu } = require("electron");
const { spawn } = require("child_process");
const { createServer } = require("net");
const path = require("path");
const http = require("http");

/* ── Globals ───────────────────────────────────────────────────────── */

let mainWindow = null;
let backendProcess = null;
let serverPort;

const isDev = process.env.NODE_ENV === "development";
const PROJECT_ROOT = path.resolve(__dirname, "..");

/* ── Port Discovery ────────────────────────────────────────────────── */

async function findFreePort(start = 5173, end = 5199) {
  for (let port = start; port <= end; port++) {
    const free = await new Promise((resolve) => {
      const server = createServer();
      server.once("error", () => resolve(false));
      server.once("listening", () => {
        server.close(() => resolve(true));
      });
      server.listen(port, "127.0.0.1");
    });
    if (free) return port;
  }
  throw new Error(`No free port found in range ${start}-${end}`);
}

/* ── Server Readiness ──────────────────────────────────────────────── */

function waitForServer(url, timeoutMs = 60000) {
  const startTime = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      if (Date.now() - startTime > timeoutMs) {
        return reject(new Error(`Server at ${url} did not start within ${timeoutMs}ms`));
      }
      http
        .get(url, (res) => {
          if (res.statusCode && res.statusCode < 500) {
            resolve();
          } else {
            setTimeout(check, 500);
          }
        })
        .on("error", () => {
          setTimeout(check, 500);
        });
    };
    check();
  });
}

/* ── Create Window ─────────────────────────────────────────────────── */

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    title: "Blueprint",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: "#000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(`http://localhost:${port}`);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

/* ── App Menu ──────────────────────────────────────────────────────── */

function buildMenu() {
  const template = [
    {
      label: "Blueprint",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" },
        { role: "zoom" },
        { type: "separator" },
        { role: "front" },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

/* ── App Lifecycle ─────────────────────────────────────────────────── */

app.whenReady().then(async () => {
  try {
    if (isDev) {
      // In dev mode, Vite is started separately via concurrently
      serverPort = 5173;
      await waitForServer(`http://localhost:${serverPort}`);
    } else {
      // In production, spawn the standalone PyInstaller Python backend binary which also serves the SPA
      serverPort = await findFreePort();
      const backendPath = path.join(process.resourcesPath, "blueprint_backend");
      console.log("[Blueprint] Spawning PyInstaller backend at:", backendPath, "on port", serverPort);
      backendProcess = spawn(backendPath, [serverPort.toString()], {
        stdio: "inherit"
      });
      console.log("[Blueprint] Waiting for backend to start...");
      await waitForServer(`http://localhost:${serverPort}`);
      console.log("[Blueprint] Backend ready!");
    }

    buildMenu();
    createWindow(serverPort);
  } catch (err) {
    console.error("[Blueprint] Startup failed:", err);
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow(serverPort);
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    cleanup();
    app.quit();
  }
});

app.on("before-quit", () => {
  cleanup();
});

function cleanup() {
  if (backendProcess) {
    console.log("[Blueprint] Stopping backend server...");
    backendProcess.kill("SIGTERM");
    backendProcess = null;
  }
}
