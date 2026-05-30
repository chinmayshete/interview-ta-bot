import { useState } from 'react';
import { apiPost } from '../api/client';

export default function SetupPage({ 
  setPage, 
  setSessionId, 
  resumeText, 
  setResumeText, 
  jdText, 
  setJdText,
  showToast,
  showSpinner,
  hideSpinner
}) {

  const [jdFilename, setJdFilename] = useState('');

  const handleResumeUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const fd = new FormData();
    fd.append('file', file);

    try {
      showSpinner('Parsing resume...');
      const res = await apiPost('/api/upload/resume', fd, true);
      setResumeText(res.text);
      showToast(`Resume parsed — ${res.char_count} characters`, 'success');
    } catch (err) {
      showToast(`Resume upload failed: ${err.message}`, 'error');
    } finally {
      hideSpinner();
    }
  };

  const handleJdUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const fd = new FormData();
    fd.append('file', file);

    try {
      showSpinner('Parsing job description...');
      const res = await apiPost('/api/upload/jd', fd, true);
      setJdText(res.text);
      setJdFilename(res.filename || file.name);
      showToast(`JD parsed — ${res.char_count} characters`, 'success');
    } catch (err) {
      showToast(`JD upload failed: ${err.message}`, 'error');
    } finally {
      hideSpinner();
    }
  };

  const startInterview = async (isLive = false) => {
    if (!resumeText || !jdText) return;

    showSpinner(isLive ? 'Starting Live session...' : 'Starting interview & generating first question...');
    try {
      const res = await apiPost('/api/interview/start', {
        resume_text: resumeText,
        jd_text: jdText,
      });

      setSessionId(res.session_id);
      
      if (isLive) {
        // Create a linked live session
        const liveRes = await apiPost('/api/live/start', {
           parent_session_id: res.session_id
        });
        window.liveSessionData = liveRes;
        setPage('live-interview');
      } else {
        window.initialQuestion = res;
        setPage('interview');
      }
      
      showToast('Interview started successfully!', 'success');
    } catch (err) {
      showToast(`Failed to start: ${err.message}`, 'error');
    } finally {
      hideSpinner();
    }
  };

  const isReady = resumeText.length > 0 && jdText.length > 20;

  return (
    <section id="setup-panel">
      <div className="glass-card">
        <div className="card-header">
          <span className="icon">📋</span>
          <h2>Interview Setup</h2>
        </div>
        <div className="card-body">
          <div className="setup-grid">
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                Candidate Resume
              </label>
              <div className={`upload-zone ${resumeText ? 'uploaded' : ''}`}>
                <span className="upload-icon">{resumeText ? '✅' : '📄'}</span>
                <div className="upload-label">{resumeText ? 'Resume Loaded' : 'Click to upload resume'}</div>
                <div className="upload-hint">{resumeText ? '✓ Uploaded successfully' : 'Supports PDF and DOCX'}</div>
                <input type="file" accept=".pdf,.docx" onChange={handleResumeUpload} style={{ opacity: 0, position: 'absolute', inset: 0, width: '100%', cursor: 'pointer' }}/>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                Job Description
              </label>
              <div className={`upload-zone ${jdText ? 'uploaded' : ''}`}>
                <span className="upload-icon">{jdText ? '✅' : '📋'}</span>
                <div className="upload-label">{jdText ? `JD Loaded — ${jdFilename}` : 'Click to upload Job Description'}</div>
                <div className="upload-hint">{jdText ? `✓ ${jdText.length} characters extracted` : 'Supports PDF and DOCX'}</div>
                <input type="file" accept=".pdf,.docx" onChange={handleJdUpload} style={{ opacity: 0, position: 'absolute', inset: 0, width: '100%', cursor: 'pointer' }}/>
              </div>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: '20px', display: 'flex', gap: '15px', justifyContent: 'center' }}>
            <button className="btn-primary" disabled={!isReady} onClick={() => startInterview(false)}>
              <span>🚀</span> Start Regular
            </button>
            <button className="btn-secondary" disabled={!isReady} onClick={() => startInterview(true)} style={{ borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' }}>
              <span>📡</span> Start Live Mode
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
