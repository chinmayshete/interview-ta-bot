import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import http from 'http';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow;
let pythonProcess;

// ---------------------------------------------------------------------------
// Python Backend Sidecar
// ---------------------------------------------------------------------------

function getPythonPath() {
  const venvPython = path.join(__dirname, '../../InvTaBotvenv/Scripts/python.exe');
  // In packaged app, resources are in a different location
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'InvTaBotvenv/Scripts/python.exe');
  }
  return venvPython;
}

function getBackendCwd() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'python_backend');
  }
  return path.join(__dirname, '../python_backend');
}

function startPythonBackend() {
  const pythonPath = getPythonPath();
  const cwd = getBackendCwd();
  const scriptPath = path.join(cwd, 'main.py');

  console.log(`[Electron] Starting Python backend...`);
  console.log(`[Electron]   Python: ${pythonPath}`);
  console.log(`[Electron]   Script: ${scriptPath}`);
  console.log(`[Electron]   CWD:    ${cwd}`);

  pythonProcess = spawn(pythonPath, [scriptPath], {
    cwd: cwd,
    env: { ...process.env },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[FastAPI] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[FastAPI] ${data.toString().trim()}`);
  });

  pythonProcess.on('error', (err) => {
    console.error(`[Electron] Failed to start Python backend: ${err.message}`);
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`[Electron] Python backend exited with code ${code}, signal ${signal}`);
  });
}

// ---------------------------------------------------------------------------
// Wait for backend to be ready (health check)
// ---------------------------------------------------------------------------

function waitForBackend(url = 'http://localhost:8000/docs', maxRetries = 30, intervalMs = 1000) {
  return new Promise((resolve, reject) => {
    let retries = 0;

    const check = () => {
      http.get(url, (res) => {
        if (res.statusCode === 200) {
          console.log('[Electron] Backend is ready!');
          resolve();
        } else {
          retry();
        }
      }).on('error', () => {
        retry();
      });
    };

    const retry = () => {
      retries++;
      if (retries >= maxRetries) {
        reject(new Error(`Backend did not start after ${maxRetries} retries.`));
      } else {
        setTimeout(check, intervalMs);
      }
    };

    check();
  });
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    titleBarStyle: 'hidden',
    transparent: true,
    frame: false,
    alwaysOnTop: true, // Keep fixed on screen
    show: false,
  });

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Show window when ready to prevent white flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
    app.quit(); // Ensure app exits when main window is closed
  });
}



// ---------------------------------------------------------------------------
// App Lifecycle
// ---------------------------------------------------------------------------

function isPortInUse(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}/`, (res) => {
      resolve(true); // something is already listening
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

app.whenReady().then(async () => {
  const alreadyRunning = await isPortInUse(8000);

  if (alreadyRunning) {
    console.log('[Electron] Port 8000 already in use — skipping Python spawn, using existing backend.');
  } else {
    startPythonBackend();
  }

  try {
    await waitForBackend();
  } catch (err) {
    console.error(`[Electron] ${err.message}`);
    console.log('[Electron] Launching UI anyway — backend may still be starting...');
  }

  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (pythonProcess && !pythonProcess.killed) {
    console.log('[Electron] Killing Python backend...');
    pythonProcess.kill();
  }
  process.exit(0);
});

// ---------------------------------------------------------------------------
// Window Control Handlers
// ---------------------------------------------------------------------------

ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.close();
});

// Click-through logic: Ignore mouse events if not over a UI element
// Note: This requires the frontend to send mouse-over/mouse-out signals
ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) {
    win.setIgnoreMouseEvents(ignore, options);
  }
});


