/**
 * Electron Preload Script — Blueprint
 * ────────────────────────────────────
 * Minimal context bridge. The app runs as a standard web page
 * talking to FastAPI backend, so very little IPC is needed.
 */

const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("blueprint", {
  platform: process.platform,
  isElectron: true,
});
