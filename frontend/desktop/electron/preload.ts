import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("harness", {
  platform: process.platform,
});
