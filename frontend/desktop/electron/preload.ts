import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("harness", {
  platform: process.platform,
  wsUrl: process.env.HARNESS_WS_URL ?? "ws://127.0.0.1:8765",
  cwd: process.env.HARNESS_WORKSPACE ?? "",
});
