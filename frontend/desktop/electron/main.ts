import { spawn, type ChildProcess } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow } from "electron";

const WEB_URL = process.env.HARNESS_WEB_URL ?? "http://127.0.0.1:5173";
const WS_HOST = process.env.HARNESS_WS_HOST ?? "127.0.0.1";
const WS_PORT = Number(process.env.HARNESS_WS_PORT ?? 8765);
const BACKEND = process.env.HARNESS_BACKEND ?? path.resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../backend");

let spawned: ChildProcess | null = null;
let owned = false;

function probe(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port }, () => {
      socket.end();
      resolve(true);
    });
    socket.setTimeout(400, () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("error", () => resolve(false));
  });
}

async function waitForServer(ms = 8000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (await probe(WS_HOST, WS_PORT)) return;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`App Server not up ws://${WS_HOST}:${WS_PORT}`);
}

async function ensureServer(): Promise<void> {
  if (await probe(WS_HOST, WS_PORT)) return;
  const python = process.env.HARNESS_PYTHON ?? "python";
  spawned = spawn(python, ["-m", "server", "--host", WS_HOST, "--port", String(WS_PORT)], {
    cwd: BACKEND,
    stdio: "ignore",
    windowsHide: true,
  });
  owned = true;
  await waitForServer();
}

function createWindow() {
  const preload = fileURLToPath(new URL("./preload.js", import.meta.url));
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  void win.loadURL(WEB_URL);
}

app.whenReady().then(async () => {
  try {
    await ensureServer();
  } catch (err) {
    console.error(err);
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", () => {
  if (owned && spawned && !spawned.killed) spawned.kill();
});
