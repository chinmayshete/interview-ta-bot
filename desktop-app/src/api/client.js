const API = 'http://localhost:8000';

export async function apiPost(path, body, isFormData = false) {
  const opts = { method: 'POST' };
  if (isFormData) {
    opts.body = body;
  } else {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || msg);
    } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

export async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || msg);
    } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

export const ENDPOINTS = {
  uploadResume: '/api/upload/resume',
  startInterview: '/api/interview/start',
  nextTurn: '/api/interview/next',
  transcribe: '/api/interview/transcribe',
  endInterview: '/api/interview/end',
  getSummary: '/api/interview/summary',
  startLoopback: '/api/audio/start-loopback',
  stopLoopback: '/api/audio/stop-loopback'
};

export const getExportUrl = (sessionId, format) => `${API}/api/interview/export/${sessionId}/${format}`;
