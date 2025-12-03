import { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import './KnowledgeBase.css';

function KnowledgeBase({ onClose }) {
    const [files, setFiles] = useState([]);
    const [repositories, setRepositories] = useState([]);
    const [currentRepository, setCurrentRepository] = useState('default');
    const [newRepoName, setNewRepoName] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = useRef(null);

    useEffect(() => {
        loadRepositories();
    }, []);

    useEffect(() => {
        loadFiles();
    }, [currentRepository]);

    const loadRepositories = async () => {
        try {
            const data = await api.listRepositories();
            setRepositories(data.repositories);
            // If current repo is not in list (and list is not empty), set to first one
            // But 'default' should always be there if we create it on backend or handle it gracefully
            if (data.repositories.length > 0 && !data.repositories.includes(currentRepository)) {
                if (data.repositories.includes('default')) {
                    setCurrentRepository('default');
                } else {
                    setCurrentRepository(data.repositories[0]);
                }
            }
        } catch (error) {
            console.error('Failed to load repositories:', error);
        }
    };

    const loadFiles = async () => {
        setIsLoading(true);
        try {
            const data = await api.listKnowledgeFiles(currentRepository);
            setFiles(data.files);
        } catch (error) {
            console.error('Failed to load files:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleCreateRepository = async (e) => {
        e.preventDefault();
        if (!newRepoName.trim()) return;

        try {
            await api.createRepository(newRepoName);
            setNewRepoName('');
            await loadRepositories();
            setCurrentRepository(newRepoName);
        } catch (error) {
            console.error('Failed to create repository:', error);
            alert('Failed to create repository');
        }
    };

    const handleDeleteRepository = async () => {
        if (!window.confirm(`Are you sure you want to delete repository "${currentRepository}"? This will delete all files in it.`)) return;

        try {
            await api.deleteRepository(currentRepository);
            await loadRepositories();
            setCurrentRepository('default');
        } catch (error) {
            console.error('Failed to delete repository:', error);
            alert('Failed to delete repository');
        }
    };

    const handleFileSelect = async (e) => {
        const selectedFiles = Array.from(e.target.files);
        if (selectedFiles.length === 0) return;

        setIsUploading(true);
        try {
            for (const file of selectedFiles) {
                await api.uploadKnowledge(file, currentRepository);
            }
            await loadFiles();
        } catch (error) {
            console.error('Upload failed:', error);
            alert('Failed to upload file to knowledge base');
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleDeleteFile = async (filename) => {
        if (!window.confirm(`Delete ${filename}?`)) return;

        try {
            await api.deleteKnowledgeFile(filename, currentRepository);
            await loadFiles();
        } catch (error) {
            console.error('Delete failed:', error);
            alert('Failed to delete file');
        }
    };

    return (
        <div className="knowledge-base-overlay">
            <div className="knowledge-base-modal">
                <div className="kb-header">
                    <h2>Knowledge Base</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="kb-content">
                    <div className="kb-sidebar">
                        <h3>Repositories</h3>
                        <div className="repo-list">
                            {repositories.map(repo => (
                                <div
                                    key={repo}
                                    className={`repo-item ${currentRepository === repo ? 'active' : ''}`}
                                    onClick={() => setCurrentRepository(repo)}
                                >
                                    {repo}
                                </div>
                            ))}
                        </div>
                        <form onSubmit={handleCreateRepository} className="new-repo-form">
                            <input
                                type="text"
                                value={newRepoName}
                                onChange={(e) => setNewRepoName(e.target.value)}
                                placeholder="New Repo Name"
                            />
                            <button type="submit">+</button>
                        </form>
                        {currentRepository !== 'default' && (
                            <button className="delete-repo-btn" onClick={handleDeleteRepository}>
                                Delete Repository
                            </button>
                        )}
                    </div>

                    <div className="kb-main">
                        <div className="kb-actions">
                            <h3>Files in '{currentRepository}'</h3>
                            <div className="upload-section">
                                <button
                                    className="upload-btn"
                                    onClick={() => fileInputRef.current.click()}
                                    disabled={isUploading}
                                >
                                    {isUploading ? 'Uploading...' : 'Upload Files'}
                                </button>
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    onChange={handleFileSelect}
                                    style={{ display: 'none' }}
                                    multiple
                                    accept=".pdf,.txt,.md,.json,.csv,.py,.js,.html,.css,.docx,.jpg,.jpeg,.png,.webp"
                                />
                            </div>
                        </div>

                        <div className="files-list">
                            {isLoading ? (
                                <div className="loading">Loading files...</div>
                            ) : files.length === 0 ? (
                                <div className="empty-state">No files in this repository</div>
                            ) : (
                                files.map((file, idx) => {
                                    const fileName = typeof file === 'string' ? file : file.name;
                                    return (
                                        <div key={fileName + idx} className="file-item">
                                            <span className="file-icon">📄</span>
                                            <span className="file-name">{fileName}</span>
                                            <button
                                                className="delete-btn"
                                                onClick={() => handleDeleteFile(fileName)}
                                            >
                                                🗑️
                                            </button>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default KnowledgeBase;
