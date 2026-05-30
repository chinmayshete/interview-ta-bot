export default function Toast({ message, type }) {
  return (
    <div id="toast-container" className="toast-container">
      <div className={`toast ${type}`} style={{ animation: 'slide-in 0.3s ease-out forwards' }}>
        <span style={{ fontSize: '1.1rem' }}>
          {type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}
        </span>
        <span className="toast-message">{message}</span>
      </div>
    </div>
  );
}
