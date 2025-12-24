// Admin Dashboard JavaScript
let currentUserPage = 1;
let currentChatPage = 1;
const itemsPerPage = 10;

document.addEventListener('DOMContentLoaded', function() {
    console.log('Admin dashboard loaded');
    loadDashboardData();
    setInterval(loadDashboardData, 30000); // Refresh every 30 seconds
});

async function loadDashboardData() {
    try {
        await loadStatistics();
        await loadUsers();
        await loadChats();
        await loadDocuments();
        await loadSystemStatus();
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showError('Failed to load dashboard data');
    }
}

async function loadStatistics() {
    try {
        const response = await fetch('/api/admin/statistics');
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('total-users').textContent = data.total_users || 0;
            document.getElementById('total-chats').textContent = data.total_chats || 0;
            document.getElementById('total-documents').textContent = data.total_documents || 0;
            document.getElementById('active-today').textContent = data.active_today || 0;
        } else {
            throw new Error(data.error || 'Failed to load statistics');
        }
    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

async function loadUsers(page = 1) {
    try {
        const response = await fetch(`/api/admin/users?page=${page}&limit=${itemsPerPage}`);
        const data = await response.json();
        
        if (response.ok) {
            displayUsers(data.users);
            setupPagination('users-pagination', data.total_pages, page, loadUsers);
        } else {
            throw new Error(data.error || 'Failed to load users');
        }
    } catch (error) {
        console.error('Error loading users:', error);
        showError('Failed to load users');
    }
}

async function loadChats(page = 1) {
    try {
        const response = await fetch(`/api/admin/chats?page=${page}&limit=${itemsPerPage}`);
        const data = await response.json();
        
        if (response.ok) {
            displayChats(data.chats);
            setupPagination('chats-pagination', data.total_pages, page, loadChats);
        } else {
            throw new Error(data.error || 'Failed to load chats');
        }
    } catch (error) {
        console.error('Error loading chats:', error);
        showError('Failed to load chats');
    }
}

async function loadDocuments() {
    try {
        const response = await fetch('/api/admin/documents');
        const data = await response.json();
        
        if (response.ok) {
            displayDocuments(data.documents);
        } else {
            throw new Error(data.error || 'Failed to load documents');
        }
    } catch (error) {
        console.error('Error loading documents:', error);
        showError('Failed to load documents');
    }
}

async function loadSystemStatus() {
    try {
        const response = await fetch('/api/admin/system-status');
        const data = await response.json();
        
        if (response.ok) {
            displaySystemStatus(data);
        } else {
            throw new Error(data.error || 'Failed to load system status');
        }
    } catch (error) {
        console.error('Error loading system status:', error);
    }
}

function displayUsers(users) {
    const tbody = document.getElementById('users-tbody');
    tbody.innerHTML = '';

    users.forEach(user => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${user.id}</td>
            <td>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div class="user-avatar">${user.username.charAt(0).toUpperCase()}</div>
                    ${user.username}
                </div>
            </td>
            <td>${user.email || 'N/A'}</td>
            <td>${user.chat_count || 0}</td>
            <td>${user.last_active || 'Never'}</td>
            <td class="status-${user.is_active ? 'active' : 'inactive'}">
                ${user.is_active ? 'Active' : 'Inactive'}
            </td>
            <td>
                <button class="btn btn-danger" onclick="deleteUser(${user.id})" title="Delete User">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function displayChats(chats) {
    const tbody = document.getElementById('chats-tbody');
    tbody.innerHTML = '';

    chats.forEach(chat => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td title="${chat.chat_id}">${chat.chat_id.substring(0, 15)}...</td>
            <td>${chat.username || 'Unknown'}</td>
            <td>${chat.message_count || 0}</td>
            <td>${formatDate(chat.created_at)}</td>
            <td>${formatDate(chat.last_activity)}</td>
            <td>
                <button class="btn btn-primary" onclick="viewChat('${chat.chat_id}')" title="View Chat">
                    <i class="fas fa-eye"></i>
                </button>
                <button class="btn btn-danger" onclick="deleteChat('${chat.chat_id}')" title="Delete Chat">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function displayDocuments(documents) {
    const tbody = document.getElementById('documents-tbody');
    tbody.innerHTML = '';

    documents.forEach(doc => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${doc.filename}</td>
            <td>${doc.uploaded_by || 'System'}</td>
            <td>${formatDate(doc.uploaded_at)}</td>
            <td>${formatFileSize(doc.file_size || 0)}</td>
            <td class="status-${doc.is_indexed ? 'active' : 'inactive'}">
                ${doc.is_indexed ? 'Indexed' : 'Not Indexed'}
            </td>
            <td>
                <button class="btn btn-warning" onclick="reindexDocument(${doc.id})" title="Reindex">
                    <i class="fas fa-sync"></i>
                </button>
                <button class="btn btn-danger" onclick="deleteDocument(${doc.id})" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function displaySystemStatus(status) {
    const container = document.getElementById('system-status');
    container.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
            <div class="stat-card">
                <div class="stat-label">LLM Status</div>
                <div class="stat-number ${status.llm_available ? 'status-active' : 'status-inactive'}">
                    ${status.llm_available ? 'Online' : 'Offline'}
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Embeddings</div>
                <div class="stat-number ${status.embeddings_available ? 'status-active' : 'status-inactive'}">
                    ${status.embeddings_available ? 'Online' : 'Offline'}
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">OCR</div>
                <div class="stat-number ${status.ocr_available ? 'status-active' : 'status-inactive'}">
                    ${status.ocr_available ? 'Online' : 'Offline'}
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Vectorstore</div>
                <div class="stat-number ${status.vectorstore_exists ? 'status-active' : 'status-inactive'}">
                    ${status.vectorstore_exists ? 'Loaded' : 'Missing'}
                </div>
            </div>
        </div>
        ${status.error ? `<div class="error">Error: ${status.error}</div>` : ''}
    `;
}

function setupPagination(containerId, totalPages, currentPage, loadFunction) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';

    for (let i = 1; i <= totalPages; i++) {
        const button = document.createElement('button');
        button.className = `page-btn ${i === currentPage ? 'active' : ''}`;
        button.textContent = i;
        button.onclick = () => loadFunction(i);
        container.appendChild(button);
    }
}

// Action Functions
async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This will also delete all their chats.')) {
        return;
    }

    try {
        const response = await fetch(`/api/admin/users/${userId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showSuccess('User deleted successfully');
            loadUsers(currentUserPage);
            loadStatistics();
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Failed to delete user');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showError('Failed to delete user: ' + error.message);
    }
}

async function deleteChat(chatId) {
    if (!confirm('Are you sure you want to delete this chat?')) {
        return;
    }

    try {
        const response = await fetch(`/api/admin/chats/${chatId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showSuccess('Chat deleted successfully');
            loadChats(currentChatPage);
            loadStatistics();
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Failed to delete chat');
        }
    } catch (error) {
        console.error('Error deleting chat:', error);
        showError('Failed to delete chat: ' + error.message);
    }
}

async function reindexDocuments() {
    if (!confirm('Reindex all documents? This may take a while.')) {
        return;
    }

    try {
        const response = await fetch('/api/admin/reindex-documents', {
            method: 'POST'
        });

        if (response.ok) {
            showSuccess('Document reindexing started');
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Failed to start reindexing');
        }
    } catch (error) {
        console.error('Error reindexing documents:', error);
        showError('Failed to reindex documents: ' + error.message);
    }
}

async function reindexDocument(documentId) {
    try {
        const response = await fetch(`/api/admin/reindex-document/${documentId}`, {
            method: 'POST'
        });

        if (response.ok) {
            showSuccess('Document reindexed successfully');
            loadDocuments();
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Failed to reindex document');
        }
    } catch (error) {
        console.error('Error reindexing document:', error);
        showError('Failed to reindex document: ' + error.message);
    }
}

async function deleteDocument(documentId) {
    if (!confirm('Are you sure you want to delete this document?')) {
        return;
    }

    try {
        const response = await fetch(`/api/admin/documents/${documentId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showSuccess('Document deleted successfully');
            loadDocuments();
            loadStatistics();
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Failed to delete document');
        }
    } catch (error) {
        console.error('Error deleting document:', error);
        showError('Failed to delete document: ' + error.message);
    }
}

function viewChat(chatId) {
    window.open(`/api/admin/chat/${chatId}`, '_blank');
}

function checkSystemStatus() {
    loadSystemStatus();
    showSuccess('System status refreshed');
}

function refreshData() {
    loadDashboardData();
    showSuccess('Dashboard data refreshed');
}

function searchUsers() {
    const searchTerm = document.getElementById('user-search').value.toLowerCase();
    const rows = document.getElementById('users-tbody').getElementsByTagName('tr');
    
    for (let row of rows) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(searchTerm) ? '' : 'none';
    }
}

function searchChats() {
    const searchTerm = document.getElementById('chat-search').value.toLowerCase();
    const rows = document.getElementById('chats-tbody').getElementsByTagName('tr');
    
    for (let row of rows) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(searchTerm) ? '' : 'none';
    }
}

function logout() {
    window.location.href = '/logout';
}

// Utility Functions
function formatDate(dateString) {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showError(message) {
    showMessage(message, 'error');
}

function showSuccess(message) {
    showMessage(message, 'success');
}

function showMessage(message, type) {
    // Remove existing messages
    const existingMessages = document.querySelectorAll('.message-temp');
    existingMessages.forEach(msg => msg.remove());

    // Create new message
    const messageDiv = document.createElement('div');
    messageDiv.className = `message-temp ${type}`;
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    if (type === 'error') {
        messageDiv.style.background = '#e53935';
    } else {
        messageDiv.style.background = '#43a047';
    }
    
    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);

    // Remove after 5 seconds
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 5000);
}

// Add CSS for animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
`;
document.head.appendChild(style);