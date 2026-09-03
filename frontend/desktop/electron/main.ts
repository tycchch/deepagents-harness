import { app, BrowserWindow } from "electron";

const WEB_URL = process.env.HARNESS_WEB_URL ?? "http://127.0.0.1:5173";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: new URL("./preload.js", import.meta.url).pathname,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  void win.loadURL(WEB_URL);
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
