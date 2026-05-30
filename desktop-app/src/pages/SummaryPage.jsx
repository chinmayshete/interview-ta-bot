import { useState, useEffect } from 'react';
import { apiGet, getExportUrl } from '../api/client';
import Spinner from '../components/Spinner';

export default function SummaryPage({ sessionId, showToast, onRestart }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadSummary() {
      try {
        const res = await apiGet(`/api/interview/summary/${sessionId}`);
        setSummary(res);
      } catch (err) {
        showToast('Failed to load summary: ' + err.message, 'error');
      } finally {
        setLoading(false);
      }
    }
    if (sessionId) {
      loadSummary();
    }
  }, [sessionId]);

  if (loading) {
    return <Spinner text="Loading Summary..." />;
  }

  if (!summary) {
    return <div style={{textAlign:'center', marginTop:'50px'}}>No summary data available.</div>;
  }

  const score = summary.overall_score || 0;

  const handleDownload = async (format) => {
    try {
      showToast(`Generating ${format.toUpperCase()}...`, 'info');
      const url = getExportUrl(sessionId, format);
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Download failed: ${res.statusText}`);
      }
      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = downloadUrl;
      a.download = `Interview_Report_${sessionId}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  return (
    <section id="summary-panel" className="fade-in">
      <div className="summary-header-container">
        <div>
          <h2>Interview Complete</h2>
          <p className="summary-metadata">
            Session ID: <strong>#{sessionId}</strong> • 
            Rating: <span className={`badge badge-${summary.overall_rating?.toLowerCase() || 'medium'}`}>{(summary.overall_rating||'N/A').toUpperCase()}</span>
          </p>
        </div>
        <div className="download-actions">
          <button className="btn-secondary" onClick={() => handleDownload('pdf')}>📄 PDF Report</button>
          <button className="btn-secondary" onClick={() => handleDownload('docx')}>📝 DOCX Report</button>
          <button className="btn-primary" onClick={onRestart} style={{ marginLeft: '10px' }}>🔄 New Interview</button>
        </div>
      </div>

      <div className="summary-main-grid">
        <div className="glass-card summary-overview-card">
          <div className="score-chart-container">
            <svg viewBox="0 0 36 36" className="circular-chart">
              <path className="circle-bg"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path className="circle"
                strokeDasharray={`${score}, 100`}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <text x="18" y="20.35" className="percentage">{score}%</text>
            </svg>
            <div className="score-label">Overall Match</div>
          </div>
          <div className="summary-statement">
            <h3>Executive Summary</h3>
            <p>{summary.summary_statement}</p>
          </div>
        </div>

        <div className="glass-card">
          <div className="card-header"><span className="icon">💪</span><h2>Strengths</h2></div>
          <div className="card-body">
            <ul className="summary-list">
              {(summary.strengths || []).map((s,i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        </div>

        <div className="glass-card">
          <div className="card-header"><span className="icon">⚠️</span><h2>Areas for Improvement</h2></div>
          <div className="card-body">
            <ul className="summary-list">
              {(summary.weaknesses || []).map((w,i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        </div>
      </div>

      <div className="summary-details-grid">
        <div className="glass-card">
          <div className="card-header"><span className="icon">💻</span><h2>Technical Proficiency</h2></div>
          <div className="card-body"><p>{summary.technical_proficiency}</p></div>
        </div>
        <div className="glass-card">
           <div className="card-header"><span className="icon">🤝</span><h2>Behavioral Fit</h2></div>
           <div className="card-body"><p>{summary.behavioral_fit}</p></div>
        </div>
        <div className="glass-card" style={{gridColumn: '1 / -1'}}>
           <div className="card-header"><span className="icon">🎯</span><h2>Final Recommendation</h2></div>
           <div className="card-body"><p><strong>{summary.recommendation}</strong></p></div>
        </div>
      </div>
    </section>
  );
}
