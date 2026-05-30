import { useState } from 'react';

export default function HistoryPanel({ items }) {
  const [selected, setSelected] = useState(null);

  const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };

  return (
    <div className="glass-card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="card-header">
        <span className="icon">📜</span>
        <h2>Interview History</h2>
      </div>
      <div className="card-body" style={{ flexGrow: 1, overflowY: 'auto', padding: '10px' }}>
        {items.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '20px' }}>
            No history yet
          </div>
        ) : (
          items.map((item) => (
            <div 
              key={item.index} 
              className="history-item fade-in" 
              style={{ cursor: 'pointer', marginBottom: '10px' }}
              onClick={() => setSelected(item)}
            >
              <div className="history-item-header" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <div>
                  <span style={{ fontWeight: 'bold', marginRight: '8px' }}>Q{item.index}</span>
                  <span className={`badge badge-${item.difficulty}`}>{item.difficulty?.toUpperCase()}</span>
                </div>
                <span>{ratingIcons[item.rating] || '🟡'}</span>
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {item.question}
              </div>
            </div>
          ))
        )}
      </div>

      {selected && (
        <div id="history-modal-overlay" className="history-modal-overlay active" onClick={() => setSelected(null)}>
          <div className="history-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Question {selected.index} Details</h3>
              <button className="btn-icon" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="modal-section">
                <h4>Question <span className={`badge badge-${selected.difficulty}`}>{selected.difficulty?.toUpperCase()}</span></h4>
                <p>{selected.question}</p>
              </div>
              <div className="modal-section">
                <h4>Candidate Answer</h4>
                <p>{selected.answer || '(No answer recorded)'}</p>
              </div>
              <div className="modal-section">
                <h4>Evaluation <span className={`eval-rating ${selected.rating}`}>{ratingIcons[selected.rating]} {selected.rating?.toUpperCase()}</span></h4>
                <p>{selected.summary}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
