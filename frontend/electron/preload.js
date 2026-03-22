/**
 * Electron Preload Script — Blueprint
 * ────────────────────────────────────
 * Context bridge exposing platform info and native file dialogs
 * to the sandboxed renderer process.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("blueprint", {
  platform: process.platform,
  isElectron: true,

  /** Open a native file picker. Returns the selected path or null if cancelled. */
  selectFile: (options) => ipcRenderer.invoke("dialog:open-file", options),

  /** Open a native directory picker. Returns the selected path or null if cancelled. */
  selectDirectory: (options) => ipcRenderer.invoke("dialog:open-directory", options),
});
