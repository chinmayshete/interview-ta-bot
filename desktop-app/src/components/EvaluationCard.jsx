export default function EvaluationCard({ data }) {
  if (!data) return null;

  const rating = data.rating || 'partial';
  const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };
  const score = data.confidence_score ?? 50;

  return (
    <div className="glass-card fade-in" style={{ marginTop: '20px' }}>
      <div className="card-header">
        <span className="icon">📊</span>
        <h2>AI Evaluation</h2>
        <div style={{ marginLeft: 'auto' }}>
          <span className={`eval-rating ${rating}`}>
            {ratingIcons[rating]} {rating.toUpperCase()}
          </span>
        </div>
      </div>
      <div className="card-body">
        <div className="confidence-meter">
          <div className="confidence-label">
            <span>Confidence Score</span>
            <span>{score}%</span>
          </div>
          <div className="confidence-track">
            <div className="confidence-bar" style={{ width: `${score}%` }}></div>
          </div>
        </div>

        <div style={{ marginTop: '15px' }}>
          <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '5px' }}>Candidate Answer Summary</h4>
          <p style={{ fontSize: '0.95rem' }}>{data.candidate_answer_summary || 'N/A'}</p>
        </div>

        <div style={{ marginTop: '15px' }}>
          <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '5px' }}>AI Reasoning</h4>
          <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)' }}>{data.reasoning || 'N/A'}</p>
        </div>
      </div>
    </div>
  );
}
