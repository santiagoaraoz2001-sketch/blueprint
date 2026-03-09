/**
 * Electron Forge Configuration — Blueprint
 * ──────────────────────────────────────────
 * Produces a macOS .app bundle and .dmg installer.
 *
 * Build:  npm run electron:build
 * Package (no installer): npm run electron:package
 */

module.exports = {
  packagerConfig: {
    name: "Blueprint",
    icon: "./electron/icon",
    appBundleId: "com.specificlabs.blueprint",
    appCategoryType: "public.app-category.developer-tools",
    ignore: [
      /^\/\.git/,
      /^\/node_modules\/\.cache/,
      /^\/\.claude/,
    ],
    extraResource: [
      "../dist/blueprint_backend"
    ],
  },
  makers: [
    {
      name: "@electron-forge/maker-dmg",
      platforms: ["darwin"],
      config: {
        name: "Blueprint",
        icon: "./electron/icon.icns",
        format: "ULFO",
      },
    },
    {
      name: "@electron-forge/maker-zip",
      platforms: ["darwin"],
    },
  ],
};
