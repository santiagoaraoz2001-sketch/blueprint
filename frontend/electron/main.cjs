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

const { app, BrowserWindow, shell, Menu, ipcMain, dialog } = require("electron");
const { spawn, execSync } = require("child_process");
const { createServer } = require("net");
const path = require("path");
const http = require("http");
const { pid: electronPid } = process;

/* ── GPU Acceleration ─────────────────────────────────────────────── */

// Ensure Chromium uses the GPU for rendering (especially on macOS Apple Silicon)
app.commandLine.appendSwitch("enable-gpu-rasterization");
app.commandLine.appendSwitch("enable-zero-copy");
app.commandLine.appendSwitch("ignore-gpu-blocklist");
app.commandLine.appendSwitch("enable-native-gpu-memory-buffers");

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

  // If the renderer crashes or is killed, clean up backend processes
  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    console.error(`[Blueprint] Renderer process gone: ${details.reason}`);
    if (details.reason === "crashed" || details.reason === "killed") {
      cleanup();
      app.quit();
    }
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

/* ── File / Directory Picker IPC ───────────────────────────────────── */

ipcMain.handle("dialog:open-file", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    title: options.title || "Select File",
    filters: options.filters || [],
    defaultPath: options.defaultPath || undefined,
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

ipcMain.handle("dialog:open-directory", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory", "createDirectory"],
    title: options.title || "Select Folder",
    defaultPath: options.defaultPath || undefined,
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

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
        stdio: "inherit",
        env: {
          ...process.env,
          BLUEPRINT_FRONTEND_DIST: path.join(process.resourcesPath, "app", "dist"),
        },
      });

      // If the backend process dies unexpectedly, quit the app cleanly
      backendProcess.on("exit", (code, signal) => {
        console.log(`[Blueprint] Backend exited (code=${code}, signal=${signal})`);
        // Avoid triggering cleanup for a process that already exited
        backendProcess = null;
        if (code !== 0 && code !== null) {
          console.error("[Blueprint] Backend crashed — quitting app.");
          app.quit();
        }
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

/* ── Zombie Process Annihilation ──────────────────────────────────── */

/**
 * Kill the entire process tree rooted at `pid`.
 * Uses `pkill -P` to find children first, then kills the parent.
 * Falls back to plain SIGKILL if pkill is unavailable.
 */
function killTree(pid, signal = "SIGTERM") {
  try {
    // Kill children first (descendants of our backend)
    execSync(`pkill -${signal === "SIGTERM" ? "TERM" : "KILL"} -P ${pid} 2>/dev/null || true`);
  } catch (_) {
    // pkill may not exist or no children found — fine
  }
  try {
    process.kill(pid, signal);
  } catch (_) {
    // Already dead — fine
  }
}

/**
 * Aggressive cleanup with SIGTERM → SIGKILL escalation.
 *
 * 1. Send SIGTERM to the backend process tree.
 * 2. Wait up to 3 seconds for graceful exit.
 * 3. If still alive, send SIGKILL (cannot be caught or ignored).
 * 4. Kill any orphaned child processes listening on our server port.
 */
function cleanup() {
  if (!backendProcess) return;

  const backendPid = backendProcess.pid;
  console.log(`[Blueprint] Stopping backend (PID ${backendPid})...`);

  // Phase 1: Graceful SIGTERM to the process tree
  killTree(backendPid, "SIGTERM");

  // Phase 2: Wait up to 3s, then escalate to SIGKILL
  const deadline = Date.now() + 3000;
  const escalate = () => {
    try {
      // process.kill(pid, 0) throws if PID is gone — use as alive check
      process.kill(backendPid, 0);
      if (Date.now() < deadline) {
        setTimeout(escalate, 200);
      } else {
        console.log(`[Blueprint] Backend PID ${backendPid} did not exit in time, sending SIGKILL...`);
        killTree(backendPid, "SIGKILL");
      }
    } catch (_) {
      // Process is gone — success
      console.log("[Blueprint] Backend stopped.");
    }
  };
  escalate();

  // Phase 3: Port-based sweep — kill anything still bound to our server port.
  // Catches orphaned children (e.g. Ollama, mlx_lm.server) that the tree-kill
  // may have missed because they double-forked / detached.
  if (serverPort) {
    try {
      const lsofOutput = execSync(
        `lsof -ti tcp:${serverPort} 2>/dev/null || true`,
        { encoding: "utf-8", timeout: 3000 }
      ).trim();
      if (lsofOutput) {
        const pids = lsofOutput.split("\n").filter(Boolean);
        for (const orphanPid of pids) {
          const p = parseInt(orphanPid, 10);
          if (p && p !== electronPid) {
            try {
              process.kill(p, "SIGKILL");
              console.log(`[Blueprint] Killed orphaned process on port ${serverPort}: PID ${p}`);
            } catch (_) {}
          }
        }
      }
    } catch (_) {}
  }

  backendProcess = null;
}
