const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

let mainWindow = null;
let backendProcess = null;
let backendPort = null;
let quitting = false;

function projectRoot() {
  return path.resolve(__dirname, "..");
}

function userDataPath(...parts) {
  return path.join(app.getPath("userData"), ...parts);
}

function envFilePath() {
  return app.isPackaged ? userDataPath(".env") : path.join(projectRoot(), ".env");
}

function findOpenPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function packagedBackendPath() {
  const executable = process.platform === "win32" ? "civagent-backend.exe" : "civagent-backend";
  return path.join(process.resourcesPath, "backend", executable);
}

function backendCommand() {
  const packaged = packagedBackendPath();
  if (app.isPackaged && fs.existsSync(packaged)) {
    return { command: packaged, args: [], cwd: path.dirname(packaged) };
  }
  const python = process.env.CIVAGENT_PYTHON || (process.platform === "win32" ? "python" : "python3");
  return { command: python, args: [path.join(projectRoot(), "server.py")], cwd: projectRoot() };
}

function startBackend(port) {
  const dataDir = userDataPath("data");
  fs.mkdirSync(dataDir, { recursive: true });

  const env = {
    ...process.env,
    HOST: "127.0.0.1",
    PORT: String(port),
    CIVAGENT_STATIC_ROOT: app.isPackaged ? path.join(process.resourcesPath, "web") : projectRoot(),
    CIVAGENT_ENV: envFilePath(),
    CIVAGENT_DB: path.join(dataDir, "civagent.sqlite")
  };
  const { command, args, cwd } = backendCommand();
  backendProcess = spawn(command, args, {
    cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true
  });

  backendProcess.stdout.on("data", data => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr.on("data", data => {
    console.error(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.on("exit", code => {
    backendProcess = null;
    if (!quitting && code !== 0) {
      console.error(`CivAgent backend exited with code ${code}`);
    }
  });
}

function healthCheck(port) {
  return new Promise((resolve, reject) => {
    const request = http.get(`http://127.0.0.1:${port}/api/health`, response => {
      response.resume();
      if (response.statusCode === 200) {
        resolve();
      } else {
        reject(new Error(`Health check returned ${response.statusCode}`));
      }
    });
    request.on("error", reject);
    request.setTimeout(900, () => {
      request.destroy(new Error("Health check timed out"));
    });
  });
}

async function waitForBackend(port) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt < 20000) {
    try {
      await healthCheck(port);
      return;
    } catch (error) {
      lastError = error;
      await new Promise(resolve => setTimeout(resolve, 350));
    }
  }
  throw lastError || new Error("CivAgent backend did not become ready.");
}

function stopBackend() {
  quitting = true;
  if (!backendProcess) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(backendProcess.pid), "/f", "/t"]);
  } else {
    backendProcess.kill("SIGTERM");
  }
  backendProcess = null;
}

async function createWindow() {
  backendPort = await findOpenPort();
  startBackend(backendPort);
  await waitForBackend(backendPort);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1120,
    minHeight: 760,
    title: "CivAgent Desktop",
    icon: app.isPackaged
      ? path.join(process.resourcesPath, "web", "assets", "brand", "civagent-icon-512.png")
      : path.join(projectRoot(), "assets", "brand", "civagent-icon-512.png"),
    backgroundColor: "#050706",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  await mainWindow.loadURL(`http://127.0.0.1:${backendPort}/app`);
}

app.whenReady().then(createWindow).catch(error => {
  console.error(error);
  app.quit();
});

app.on("before-quit", stopBackend);

app.on("window-all-closed", () => {
  app.quit();
});
