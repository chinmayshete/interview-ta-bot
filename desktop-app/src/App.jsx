import { useState } from 'react';
import SetupPage from './pages/SetupPage';
import InterviewPage from './pages/InterviewPage';
import LiveInterviewPage from './pages/LiveInterviewPage';
import SummaryPage from './pages/SummaryPage';
import OverlayWidget from './components/OverlayWidget';
import Toast from './components/Toast';
import Spinner from './components/Spinner';

function App() {
  const [page, setPage] = useState(window.location.hash === '#overlay' ? 'overlay' : 'setup');
  const [sessionId, setSessionId] = useState(null);
  const [resumeText, setResumeText] = useState('');
  const [jdText, setJdText] = useState('');
  const [toast, setToast] = useState({ message: '', type: '', visible: false });
  const [spinner, setSpinner] = useState({ text: '', visible: false });

  const showToast = (message, type = 'info') => {
    setToast({ message, type, visible: true });
    setTimeout(() => setToast(t => ({ ...t, visible: false })), 4000);
  };

  const showSpinner = (text = 'Processing...') => setSpinner({ text, visible: true });
  const hideSpinner = () => setSpinner(s => ({ ...s, visible: false }));

  const resetApp = () => {
    setSessionId(null);
    setResumeText('');
    setJdText('');
    setPage('setup');
  };

  if (page === 'overlay') {
    return <OverlayWidget />;
  }

  return (
    <div className="app-container">
      <div className="title-bar-custom">
        <div className="window-controls">
          <button className="control-btn minimize" onClick={() => window.electronAPI.minimize()} title="Minimize">
            <span>−</span>
          </button>
          <button className="control-btn maximize" onClick={() => window.electronAPI.maximize()} title="Maximize">
            <span>▢</span>
          </button>
          <button className="control-btn close" onClick={() => window.electronAPI.close()} title="Close">
            <span>✕</span>
          </button>
        </div>
      </div>

      <header className="app-header">
        <div className="app-logo">
          <div className="logo-icon">🧠</div>
          <div className="logo-text">
            <h1>Interview Support Agent</h1>
            <p>Powered by Azure OpenAI GPT-4.1 (Desktop)</p>
          </div>
        </div>
        <div className={`header-status ${page === 'interview' ? 'active' : ''}`}>
          <span className={`status-dot ${page === 'interview' ? 'active' : ''}`}></span>
          <span className="status-text">
            {page === 'setup' ? 'Ready to Start' : page === 'interview' ? 'Interview Active' : 'Interview Ended'}
          </span>
        </div>
      </header>

      {page === 'setup' && (
        <SetupPage 
          setPage={setPage} 
          setSessionId={setSessionId}
          resumeText={resumeText}
          setResumeText={setResumeText}
          jdText={jdText}
          setJdText={setJdText}
          showToast={showToast}
          showSpinner={showSpinner}
          hideSpinner={hideSpinner}
        />
      )}

      {page === 'interview' && (
        <InterviewPage 
          sessionId={sessionId}
          setPage={setPage}
          showToast={showToast}
          showSpinner={showSpinner}
          hideSpinner={hideSpinner}
        />
      )}

      {page === 'live-interview' && (
        <LiveInterviewPage 
          sessionId={sessionId}
          setPage={setPage}
          showToast={showToast}
          showSpinner={showSpinner}
          hideSpinner={hideSpinner}
        />
      )}

      {page === 'summary' && (
        <SummaryPage 
          sessionId={sessionId}
          showToast={showToast}
          onRestart={resetApp}
        />
      )}

      {toast.visible && <Toast message={toast.message} type={toast.type} />}
      {spinner.visible && <Spinner text={spinner.text} />}
    </div>
  );
}

export default App;
