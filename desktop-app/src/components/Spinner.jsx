const Spinner = ({ text }) => (
  <div id="spinner-overlay" className="spinner-overlay active">
    <div className="spinner-container">
      <div className="spinner"></div>
      <div className="spinner-text">{text}</div>
    </div>
  </div>
);

export default Spinner;
