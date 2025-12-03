import { useState } from 'react';
import './Stage4.css';

export default function Stage4({ infographicResult }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  if (!infographicResult || !infographicResult.generated) {
    return null;
  }

  const { image_data, content, model } = infographicResult;
  const modelName = model ? (model.split('/').pop() || model) : 'Nano Banana Pro';

  // Check if we have image data
  const hasImage = image_data && (
    image_data.startsWith('data:image') ||
    image_data.length > 100  // Base64 data
  );

  // Build image src
  let imageSrc = null;
  if (hasImage) {
    if (image_data.startsWith('data:image')) {
      imageSrc = image_data;
    } else {
      // Assume base64 PNG
      imageSrc = `data:image/png;base64,${image_data}`;
    }
  }

  const handleDownload = (e) => {
    e.stopPropagation();
    if (!imageSrc) return;

    const link = document.createElement('a');
    link.href = imageSrc;
    link.download = `infographic-${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const openModal = () => setIsModalOpen(true);
  const closeModal = () => setIsModalOpen(false);

  return (
    <div className="stage stage4">
      <div className="stage-header">
        <h3>Stage 4: Infographic</h3>
        <span className="infographic-badge">{modelName}</span>
      </div>
      <div className="stage-content">
        {imageSrc ? (
          <>
            {/* Thumbnail Preview */}
            <div className="infographic-preview" onClick={openModal}>
              <img
                src={imageSrc}
                alt="Generated Infographic"
                className="infographic-thumbnail"
              />
              <div className="preview-overlay">
                <span className="preview-hint">Click to enlarge</span>
              </div>
            </div>
            <div className="infographic-actions">
              <button className="action-btn view-btn" onClick={openModal}>
                🔍 View Full Size
              </button>
              <button className="action-btn download-btn" onClick={handleDownload}>
                ⬇️ Download
              </button>
            </div>

            {/* Modal for Full Size View */}
            {isModalOpen && (
              <div className="modal-overlay" onClick={closeModal}>
                <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h4>Infographic</h4>
                    <button className="modal-close" onClick={closeModal}>✕</button>
                  </div>
                  <div className="modal-body">
                    <img
                      src={imageSrc}
                      alt="Generated Infographic Full Size"
                      className="infographic-full"
                    />
                  </div>
                  <div className="modal-footer">
                    <button className="action-btn download-btn" onClick={handleDownload}>
                      ⬇️ Download Image
                    </button>
                    <button className="action-btn close-btn" onClick={closeModal}>
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : content ? (
          <div className="infographic-text">
            <p className="info-note">Image generation result:</p>
            <div className="content-preview">{content}</div>
          </div>
        ) : (
          <div className="infographic-error">
            <p>Infographic could not be displayed</p>
          </div>
        )}
      </div>
    </div>
  );
}
