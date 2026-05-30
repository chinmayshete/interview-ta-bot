export default function QuestionCard({ data, number }) {
  const q = data?.next_question || {};
  const difficulty = q.difficulty || 'easy';
  const category = (q.category || 'technical').replace('_', ' ');

  return (
    <div className="glass-card" id="question-card">
      <div className="card-header">
        <span className="icon">🎯</span>
        <h2>Current Question</h2>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
          <span className={`badge badge-${difficulty}`}>{difficulty.toUpperCase()}</span>
          <span className="badge badge-medium">{category.toUpperCase()}</span>
        </div>
      </div>
      <div className="card-body">
        <div className="question-text">
          <span style={{ color: 'var(--accent-primary)', marginRight: '8px' }}>Q{number}.</span>
          {q.question || 'Loading question...'}
        </div>

        {data?.expected_answer && (
          <div className="expected-answer" style={{marginTop:'15px'}}>
            <details>
              <summary style={{fontWeight:500, cursor:'pointer', color:'var(--text-secondary)'}}>
                Expected Points
              </summary>
              <div style={{marginTop:'10px', fontSize:'0.9rem'}}>
                {data.expected_answer}
              </div>
            </details>
          </div>
        )}

        {data?.reference_answer && (
          <div className="reference-answer" style={{marginTop:'15px'}}>
            <details open>
              <summary style={{fontWeight:500, cursor:'pointer', color:'var(--text-secondary)'}}>
                Ideal Reference Answer
              </summary>
              <div style={{marginTop:'10px', fontSize:'0.9rem', color:'var(--text-muted)'}}>
                {data.reference_answer}
              </div>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}
