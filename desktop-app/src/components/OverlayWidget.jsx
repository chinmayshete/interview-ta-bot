import { useState, useEffect } from 'react';

export default function OverlayWidget() {
  const [data, setData] = useState({ question: 'Waiting for interview to start...', rating: null });

  useEffect(() => {
    // Add special body class for the transparent window
    document.body.style.background = 'rgba(15, 23, 42, 0.85)';
    document.body.style.margin = '0';
    document.body.style.overflow = 'hidden';
    document.body.style.borderRadius = '12px';
    document.body.style.border = '1px solid rgba(255, 255, 255, 0.1)';
    document.body.style.backdropFilter = 'blur(10px)';
    document.body.style.color = '#fff';
    document.body.style.fontFamily = 'Inter, sans-serif';

    if (window.electronAPI) {
      window.electronAPI.onOverlayUpdate('interview-update', (payload) => {
        setData(payload);
      });
    }

    return () => {
      document.body.style = '';
    };
  }, []);

  const hideOverlay = () => {
    if (window.electronAPI) {
      window.electronAPI.toggleOverlay(false);
    }
  };

  return (
    <div style={{ padding: '15px', height: '100%', display: 'flex', flexDirection: 'column', WebkitAppRegion: 'drag' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', WebkitAppRegion: 'no-drag' }}>
        <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '1px' }}>
          Current Question
        </div>
        <button 
          onClick={hideOverlay} 
          style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '1.2rem', padding: '0 5px' }}
        >
          ×
        </button>
      </div>
      
      <div style={{ marginTop: '10px', fontSize: '1.1rem', fontWeight: 500, lineHeight: 1.4, flexGrow: 1 }}>
        {data.question}
      </div>

      {data.rating && (
        <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
          <span style={{ color: '#94a3b8' }}>Last Evaluation:</span>
          <span style={{ 
            padding: '2px 8px', 
            borderRadius: '12px', 
            background: data.rating === 'strong' ? 'rgba(34,197,94,0.2)' : data.rating === 'weak' ? 'rgba(239,68,68,0.2)' : 'rgba(234,179,8,0.2)',
            color: data.rating === 'strong' ? '#4ade80' : data.rating === 'weak' ? '#f87171' : '#facc15'
          }}>
            {data.rating.toUpperCase()}
          </span>
        </div>
      )}
    </div>
  );
}
