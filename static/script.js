document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const chatContainer = document.getElementById('chat-container');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const typingIndicator = document.getElementById('typing-indicator');
    const suggestions = document.querySelectorAll('.suggestion');
    const sidebar = document.getElementById('sidebar');
    const toggleSidebar = document.getElementById('toggle-sidebar');
    const closeSidebar = document.getElementById('close-sidebar');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatList = document.getElementById('chat-list');
    
    // Upload modal elements
    const uploadBtn = document.getElementById('upload-btn');
    const uploadModal = document.getElementById('upload-modal');
    const closeModal = document.getElementById('close-modal');
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const cancelUpload = document.getElementById('cancel-upload');
    const processDocument = document.getElementById('process-document');
    
    // Chat management
    let currentDocument = null;
    let currentChatId = null;
    
    // Upload progress tracking
    function createProgressMessage(filename, type = 'document') {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message');
        messageElement.classList.add('user-message');
        messageElement.id = `upload-${Date.now()}`;
        
        const icon = type === 'image' ? '📷' : '📄';
        messageElement.innerHTML = `
            <div>
                <div>${icon} Uploading: ${filename}</div>
                <div class="upload-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                    <span class="progress-text">0%</span>
                </div>
            </div>
            <div class="message-time">${getCurrentTime()}</div>
        `;
        
        chatContainer.insertBefore(messageElement, typingIndicator);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return messageElement;
    }

    function updateProgress(messageElement, percentage) {
        const progressFill = messageElement.querySelector('.progress-fill');
        const progressText = messageElement.querySelector('.progress-text');
        if (progressFill) progressFill.style.width = percentage + '%';
        if (progressText) progressText.textContent = percentage + '%';
    }

    function completeProgress(messageElement, finalMessage) {
        const progressContainer = messageElement.querySelector('.upload-progress');
        if (progressContainer) {
            progressContainer.innerHTML = finalMessage;
        }
    }
    
    // Set initial message time
    document.getElementById('initial-time').textContent = getCurrentTime();
    
    // Initialize chats
    initChats();
    
    // Focus on input field
    userInput.focus();
    
    // Sidebar functionality
    toggleSidebar.addEventListener('click', function() {
        const mainContent = document.querySelector('.main-content');
        if (window.innerWidth >= 1025) {
            const isHidden = sidebar.classList.toggle('hidden');
            if (isHidden) {
                sidebar.classList.remove('collapsed');
                mainContent.classList.remove('expanded');
            }
            localStorage.setItem('sidebarHidden', isHidden);
        } else {
            sidebar.classList.toggle('open');
        }
    });
    
    closeSidebar.addEventListener('click', function() {
        const mainContent = document.querySelector('.main-content');
        if (window.innerWidth >= 1025) {
            sidebar.classList.add('hidden');
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('expanded');
            localStorage.setItem('sidebarHidden', 'true');
        } else {
            sidebar.classList.remove('open');
        }
    });
    
    // New chat button
    newChatBtn.addEventListener('click', function() {
        createNewChat();
    });

    // Profile menu functionality
    const profileBtn = document.getElementById('profile-btn');
    const profileMenu = document.getElementById('profile-menu');
    const profileName = document.getElementById('profile-name');

    if (profileBtn && profileMenu) {
        profileBtn.addEventListener('click', function(e){
            e.stopPropagation();
            const isDesktop = window.innerWidth >= 1025;
            if (isDesktop) {
                const isNowOpen = sidebar.classList.toggle('show-profile');
                if (isNowOpen) {
                    profileMenu.setAttribute('aria-hidden', 'false');
                    profileMenu.style.display = 'flex';
                } else {
                    profileMenu.setAttribute('aria-hidden', 'true');
                    profileMenu.style.display = 'none';
                }
            } else {
                const visible = profileMenu.getAttribute('aria-hidden') === 'false';
                profileMenu.setAttribute('aria-hidden', String(!visible));
                profileMenu.style.display = visible ? 'none' : 'flex';
            }
        });

        // Close profile menu when clicking outside
        document.addEventListener('click', function(e){
            if (window.innerWidth < 1025) {
                if (!profileMenu.contains(e.target) && e.target !== profileBtn) {
                    profileMenu.setAttribute('aria-hidden', 'true');
                    profileMenu.style.display = 'none';
                }
                return;
            }

            if (sidebar.classList.contains('show-profile')) {
                if (!sidebar.contains(e.target) || e.target === profileBtn) {
                    return;
                }
                sidebar.classList.remove('show-profile');
                profileMenu.setAttribute('aria-hidden', 'true');
                profileMenu.style.display = 'none';
            }
        });

        // Menu actions
        document.getElementById('menu-logout').addEventListener('click', async function(){
            try { 
                await fetch('/logout', { method: 'POST' }); 
            } catch(e){
                console.warn('Logout request failed', e);
            }
            window.location.href = '/login';
        });

        const menuProfileBtn = document.getElementById('menu-profile');
        if (menuProfileBtn) {
            menuProfileBtn.addEventListener('click', function(){
                const uploadModalEl = document.getElementById('upload-modal');
                if (uploadModalEl) uploadModalEl.style.display = 'none';
                const modal = document.getElementById('profile-modal');
                if (!modal) return;
                modal.style.display = 'flex';
                fetchUserProfile();
            });
        }

        const menuChangePw = document.getElementById('menu-change-password');
        if (menuChangePw) {
            menuChangePw.addEventListener('click', function(){
                const uploadModalEl = document.getElementById('upload-modal');
                if (uploadModalEl) uploadModalEl.style.display = 'none';
                const modal = document.getElementById('profile-modal');
                if (!modal) return;
                modal.style.display = 'flex';
                setTimeout(() => {
                    const cur = document.getElementById('pm-current');
                    if (cur) cur.focus();
                }, 250);
            });
        }

        document.getElementById('menu-change-avatar').addEventListener('click', function(){
            const inp = document.createElement('input');
            inp.type = 'file';
            inp.accept = 'image/*';
            inp.addEventListener('change', async function(){
                if (!this.files || !this.files[0]) return;
                await uploadAvatar(this.files[0]);
            });
            inp.click();
        });

        // Fetch and show current user info
        updateProfileInfo();
    }

    // Profile modal handlers
    const profileModal = document.getElementById('profile-modal');
    if (profileModal) {
        const closeProfileModal = document.getElementById('close-profile-modal');
        const pmCancel = document.getElementById('pm-cancel');
        const pmPwCancel = document.getElementById('pm-pw-cancel');
        const pmAvatar = document.getElementById('pm-avatar');
        const pmPwForm = document.getElementById('pm-change-password');

        function closeProfileModalFunc() { 
            profileModal.style.display = 'none'; 
        }
        
        if (closeProfileModal) closeProfileModal.addEventListener('click', closeProfileModalFunc);
        if (pmCancel) pmCancel.addEventListener('click', closeProfileModalFunc);
        if (pmPwCancel) pmPwCancel.addEventListener('click', closeProfileModalFunc);

        // Avatar upload in profile modal
        if (pmAvatar) {
            pmAvatar.addEventListener('click', function(){
                const inp = document.createElement('input'); 
                inp.type = 'file'; 
                inp.accept = 'image/*';
                inp.addEventListener('change', async function(){
                    if (!this.files || !this.files[0]) return;
                    await uploadAvatar(this.files[0]);
                });
                inp.click();
            });
        }

        // Change password form
        if (pmPwForm) {
            pmPwForm.addEventListener('submit', async function(e){
                e.preventDefault();
                const cur = document.getElementById('pm-current').value;
                const nw = document.getElementById('pm-new').value;
                const msgEl = document.getElementById('pm-pw-msg'); 
                if (msgEl) msgEl.textContent = '';
                
                if (!cur || !nw) { 
                    if (msgEl) msgEl.textContent = 'Both fields required'; 
                    return; 
                }
                
                try {
                    const res = await fetch('/api/user/change_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ current_password: cur, new_password: nw })
                    });
                    const d = await res.json();
                    if (res.ok) { 
                        alert(d.message || 'Password changed'); 
                        closeProfileModalFunc(); 
                    } else { 
                        if (msgEl) msgEl.textContent = d.error || 'Failed to change password'; 
                    }
                } catch(e) { 
                    if (msgEl) msgEl.textContent = 'Network error'; 
                }
            });
        }

        // Edit/Save profile
        document.getElementById('pm-edit').addEventListener('click', function(){ 
            setProfileEditable(true); 
        });
        
        document.getElementById('pm-save').addEventListener('click', async function(){
            const newName = document.getElementById('pm-username').value.trim();
            const newEmail = document.getElementById('pm-email').value.trim();
            if (!newName || !newEmail) {
                alert('Name and email are required');
                return;
            }
            
            try {
                const res = await fetch('/api/user/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: newName, email: newEmail })
                });
                const d = await res.json();
                if (res.ok) { 
                    alert(d.message || 'Saved'); 
                    updateProfileInfo(); 
                    setProfileEditable(false); 
                    closeProfileModalFunc();
                } else { 
                    alert(d.error || 'Failed to save'); 
                }
            } catch(e) { 
                alert('Save failed'); 
            }
        });
    }

    // Apply saved sidebar state
    const savedHidden = localStorage.getItem('sidebarHidden');
    if (savedHidden === 'true' && window.innerWidth >= 1025) {
        sidebar.classList.add('hidden');
        document.querySelector('.main-content').classList.remove('expanded');
    }
    
    // Initialize mini sidebar
    initMiniSidebar();
    
    // Re-initialize on window resize
    window.addEventListener('resize', function() {
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.querySelector('.main-content');
        if (window.innerWidth < 1025) {
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('expanded');
        } else {
            initMiniSidebar();
        }
    });
    
    // Send message functionality
    sendBtn.addEventListener('click', sendMessage);
    
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    // Suggestion buttons
    suggestions.forEach(suggestion => {
        suggestion.addEventListener('click', function() {
            userInput.value = this.getAttribute('data-question');
            sendMessage();
        });
    });
    
    // Upload modal functionality
    if (uploadBtn) {
        uploadBtn.addEventListener('click', function() {
            const profileModalEl = document.getElementById('profile-modal');
            if (profileModalEl) profileModalEl.style.display = 'none';
            uploadModal.style.display = 'flex';
        });
    }

    // Add button functionality
    const addBtn = document.getElementById('add-btn');
    const addMenu = document.getElementById('add-menu');
    const addUploadDoc = document.getElementById('add-upload-doc');
    const addUploadImg = document.getElementById('add-upload-img');

    if (addBtn && addMenu) {
        addBtn.addEventListener('click', function(e){
            e.stopPropagation();
            addMenu.classList.toggle('open');
        });
    }

    document.addEventListener('click', function(){ 
        if (addMenu) addMenu.classList.remove('open'); 
    });

    if (addUploadDoc) {
        addUploadDoc.addEventListener('click', function(e){
            e.stopPropagation();
            const profileModalEl = document.getElementById('profile-modal');
            if (profileModalEl) profileModalEl.style.display = 'none';
            if (uploadModal) uploadModal.style.display = 'flex';
            if (addMenu) addMenu.classList.remove('open');
        });
    }

    if (addUploadImg) {
        addUploadImg.addEventListener('click', function(e){
            e.stopPropagation();
            const inp = document.createElement('input'); 
            inp.type = 'file'; 
            inp.accept = 'image/*';
            inp.addEventListener('change', async function(){
                if (!this.files || !this.files[0]) return;
                
                const file = this.files[0];
                const fd = new FormData(); 
                fd.append('file', file); 
                fd.append('chat_id', currentChatId || getNewChatId());
                
                // Create progress message
                const progressMessage = createProgressMessage(file.name, 'image');
                
                const question = prompt('Optional: enter a question about the image', 'Describe the image and extract any readable text.');
                if (question) fd.append('question', question);
                
                try {
                    // Simulate progress
                    let progress = 0;
                    const progressInterval = setInterval(() => {
                        progress += 10;
                        if (progress <= 90) {
                            updateProgress(progressMessage, progress);
                        }
                    }, 100);
                    
                    const res = await fetch('/api/image', { method: 'POST', body: fd });
                    clearInterval(progressInterval);
                    updateProgress(progressMessage, 100);
                    
                    const d = await res.json();
                    if (res.ok) {
                        completeProgress(progressMessage, `✅ Uploaded: ${file.name}`);
                        addMessageToChat(d.response || 'Image processed successfully', 'bot');
                    } else {
                        completeProgress(progressMessage, `❌ Failed: ${file.name}`);
                        addMessageToChat('Error: ' + (d.error || 'Image upload failed'), 'bot');
                    }
                } catch(err) { 
                    completeProgress(progressMessage, `❌ Failed: ${file.name}`);
                    addMessageToChat('Error: Image upload failed - ' + err.message, 'bot'); 
                }
            });
            inp.click();
            if (addMenu) addMenu.classList.remove('open');
        });
    }
    
    // Upload modal controls
    closeModal.addEventListener('click', function() {
        uploadModal.style.display = 'none';
        resetUploadForm();
    });
    
    cancelUpload.addEventListener('click', function() {
        uploadModal.style.display = 'none';
        resetUploadForm();
    });
    
    uploadArea.addEventListener('click', function() {
        fileInput.click();
    });
    
    // Drag and drop
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.style.background = '#e0f2f1';
    });
    
    uploadArea.addEventListener('dragleave', function() {
        uploadArea.style.background = '';
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.style.background = '';
        if (e.dataTransfer.files.length) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', function() {
        if (this.files.length) {
            handleFileSelection(this.files[0]);
        }
    });
    
    processDocument.addEventListener('click', function() {
        if (currentDocument) {
            processUploadedDocument(currentDocument);
        }
    });

    // Helper Functions
    
    function getNewChatId() {
        const username = document.getElementById('profile-name')?.textContent || 'user';
        return `${username}-${Date.now()}`;
    }
    
    async function fetchUserProfile() {
        try {
            const res = await fetch('/api/user');
            const d = await res.json();
            if (d.user) {
                const uel = document.getElementById('pm-username');
                const eel = document.getElementById('pm-email');
                const ael = document.getElementById('pm-avatar');
                if (uel) uel.value = d.user.username || '';
                if (eel) eel.value = d.user.email || '';
                if (d.user.avatar && ael) {
                    ael.style.backgroundImage = `url(${d.user.avatar})`;
                    ael.textContent = '';
                    ael.style.backgroundSize = 'cover';
                }
                setProfileEditable(false);
            }
        } catch(e) {
            console.error('Failed to fetch user profile', e);
        }
    }
    
    function setProfileEditable(editable) {
        const username = document.getElementById('pm-username');
        const email = document.getElementById('pm-email');
        const currentPw = document.getElementById('pm-current');
        const newPw = document.getElementById('pm-new');
        const saveBtn = document.getElementById('pm-save');
        const editBtn = document.getElementById('pm-edit');
        
        if (username) username.disabled = !editable;
        if (email) email.disabled = !editable;
        if (currentPw) currentPw.disabled = !editable;
        if (newPw) newPw.disabled = !editable;
        if (saveBtn) saveBtn.style.display = editable ? 'inline-block' : 'none';
        if (editBtn) editBtn.style.display = editable ? 'none' : 'inline-block';
    }
    
    async function uploadAvatar(file) {
        const fd = new FormData();
        fd.append('file', file);
        try {
            const res = await fetch('/api/user/avatar', { method: 'POST', body: fd });
            const data = await res.json();
            if (res.ok) {
                alert('Avatar updated');
                updateProfileInfo();
            } else {
                alert(data.error || 'Failed to upload avatar');
            }
        } catch (err) {
            alert('Upload failed');
        }
    }
    
    async function updateProfileInfo() {
        try {
            const res = await fetch('/api/user');
            const data = await res.json();
            if (data.user && data.user.username) {
                if (profileName) profileName.textContent = data.user.username;
                const avatarEl = document.getElementById('profile-btn');
                if (data.user.avatar && avatarEl) {
                    avatarEl.style.backgroundImage = `url(${data.user.avatar})`;
                    avatarEl.textContent = '';
                    avatarEl.style.backgroundSize = 'cover';
                    avatarEl.style.backgroundPosition = 'center';
                }
            }
        } catch (err) {
            console.error('Failed to update profile info', err);
        }
    }

    // Chat management functions
async function initChats() {
    try {
        console.log('Initializing chats...');
        const response = await fetch('/api/chats');
        const chats = await response.json();
        console.log('Chats received:', chats);
        
        if (chats.length === 0) {
            console.log('No chats found, creating new chat...');
            await createNewChat();
        } else {
            console.log('Loading existing chat:', chats[0].id);
            currentChatId = chats[0].id;
            await loadChat(currentChatId);
        }
        await renderChatList(chats);
    } catch (error) {
        console.error('Error fetching chats:', error);
        await createNewChat();
    }
}

    async function createNewChat() {
        currentChatId = getNewChatId();
        console.log('Creating new chat with ID:', currentChatId);
        
        // Clear chat container completely - start with empty chat
        chatContainer.innerHTML = '';
        chatContainer.appendChild(typingIndicator);
        
        // Use a proper chat name instead of the greeting message
        const chatName = "New AquaAI Chat";
        
        try {
            // Save the chat with proper name first
            const chatResponse = await fetch('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    chat_id: currentChatId,
                    name: chatName
                })
            });
            
            console.log('Chat created:', chatResponse.ok);
            
            // ⚠️ REMOVED: Don't save bot welcome message via API
            // This prevents the duplicate when loading chat history
            
        } catch (error) {
            console.error('Error creating new chat:', error);
        }
        
        await renderChatList();
        if (window.innerWidth <= 768) {
            sidebar.classList.remove('open');
        }
        
        // ✅ ONLY show welcome message in UI, don't save to database
        const welcomeText = "Hello! I'm AquaAI, your specialized assistant for water management, climate change, and sustainability. How can I help you today?";
        
        const initialMessage = document.createElement('div');
        initialMessage.classList.add('message', 'bot-message');
        initialMessage.innerHTML = `
            <div>${welcomeText}</div>
            <div class="message-time">${getCurrentTime()}</div>
        `;
        chatContainer.insertBefore(initialMessage, typingIndicator);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

async function loadChat(chatId) {
    currentChatId = chatId;
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        const messages = await response.json();
        
        // Clear chat container completely
        chatContainer.innerHTML = '';
        
        if (messages.length === 0) {
            // If no messages in database, show welcome message (UI only)
            const welcomeText = "Hello! I'm AquaAI, your specialized assistant for water management, climate change, and sustainability. How can I help you today?";
            
            const initialMessage = document.createElement('div');
            initialMessage.classList.add('message', 'bot-message');
            initialMessage.innerHTML = `
                <div>${welcomeText}</div>
                <div class="message-time">${getCurrentTime()}</div>
            `;
            chatContainer.appendChild(initialMessage);
        } else {
            // Only add messages that are actually in the database
            messages.forEach(msg => {
                const messageElement = document.createElement('div');
                messageElement.classList.add('message');
                messageElement.classList.add(msg.sender === 'user' ? 'user-message' : 'bot-message');
                messageElement.innerHTML = `
                    <div>${msg.content}</div>
                    <div class="message-time">${msg.time}</div>
                `;
                chatContainer.appendChild(messageElement);
            });
        }
        
        chatContainer.appendChild(typingIndicator);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        await renderChatList();
        if (window.innerWidth <= 768) {
            sidebar.classList.remove('open');
        }
    } catch (error) {
        console.error('Error loading chat:', error);
    }
}
    async function renderChatList(chats = null) {
        if (!chats) {
            try {
                const response = await fetch('/api/chats');
                chats = await response.json();
            } catch (error) {
                console.error('Error fetching chats:', error);
                return;
            }
        }
        
        chatList.innerHTML = '';
        chats.forEach(chat => {
            const chatItem = document.createElement('div');
            chatItem.classList.add('chat-item');
            if (chat.id === currentChatId) {
                chatItem.classList.add('active');
            }
            
            chatItem.innerHTML = `
                <div class="chat-item-content">
                    <i class="fas fa-comment"></i>
                    <div class="chat-item-name">${chat.name}</div>
                </div>
                <div class="chat-menu">
                    <button class="menu-dots">•••</button>
                    <div class="menu-options">
                        <div class="menu-option" data-action="rename" data-chat-id="${chat.id}">
                            <i class="fas fa-edit"></i> Rename
                        </div>
                        <div class="menu-option" data-action="delete" data-chat-id="${chat.id}">
                            <i class="fas fa-trash"></i> Delete
                        </div>
                    </div>
                </div>
            `;
            
            chatItem.querySelector('.chat-item-content').addEventListener('click', function() {
                loadChat(chat.id);
            });
            
            const menuDots = chatItem.querySelector('.menu-dots');
            const menuOptions = chatItem.querySelector('.menu-options');
            
            menuDots.addEventListener('click', function(e) {
                e.stopPropagation();
                document.querySelectorAll('.menu-options').forEach(menu => {
                    if (menu !== menuOptions) menu.classList.remove('show');
                });
                menuOptions.classList.toggle('show');
            });
            
            menuOptions.querySelectorAll('.menu-option').forEach(option => {
                option.addEventListener('click', async function(e) {
                    e.stopPropagation();
                    const action = this.getAttribute('data-action');
                    const chatId = this.getAttribute('data-chat-id');
                    
                    if (action === 'rename') {
                        await renameChat(chatId);
                    } else if (action === 'delete') {
                        await deleteChat(chatId);
                    }
                    
                    menuOptions.classList.remove('show');
                });
            });
            
            chatList.appendChild(chatItem);
        });
        
        document.addEventListener('click', function() {
            document.querySelectorAll('.menu-options').forEach(menu => {
                menu.classList.remove('show');
            });
        });
    }
    
    async function renameChat(chatId) {
        const newName = prompt('Enter a new name for this chat:');
        if (newName && newName.trim() !== '') {
            try {
                await fetch(`/api/chats/${chatId}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName.trim() })
                });
                await renderChatList();
            } catch (error) {
                console.error('Error renaming chat:', error);
            }
        }
    }
    
    async function deleteChat(chatId) {
        if (!confirm('Are you sure you want to delete this chat?')) return;
        try {
            await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
            if (currentChatId === chatId) {
                await createNewChat();
            }
            await renderChatList();
        } catch (error) {
            console.error('Error deleting chat:', error);
        }
    }
    
    function handleFileSelection(file) {
        if (file.type !== 'application/pdf') {
            alert('Please upload a PDF file.');
            return;
        }
        if (file.size > 10 * 1024 * 1024) {
            alert('File size exceeds 10MB limit.');
            return;
        }
        
        currentDocument = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.style.display = 'block';
        processDocument.disabled = false;
    }
    
    function resetUploadForm() {
        fileInput.value = '';
        fileInfo.style.display = 'none';
        processDocument.disabled = true;
        currentDocument = null;
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    async function processUploadedDocument(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('chat_id', currentChatId);
        
        // Create progress message for document
        const progressMessage = createProgressMessage(file.name, 'document');
        
        try {
            // Simulate progress
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += 10;
                if (progress <= 90) {
                    updateProgress(progressMessage, progress);
                }
            }, 150);
            
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            clearInterval(progressInterval);
            updateProgress(progressMessage, 100);
            
            const result = await response.json();
            if (response.ok) {
                completeProgress(progressMessage, `✅ Uploaded: ${file.name}`);
                const docIndicator = document.createElement('div');
                docIndicator.classList.add('document-indicator');
                docIndicator.innerHTML = `<i class="fas fa-file-pdf"></i> ${result.message}`;
                chatContainer.insertBefore(docIndicator, typingIndicator);
                updateSuggestionsForDocument();
                uploadModal.style.display = 'none';
                resetUploadForm();
                chatContainer.scrollTop = chatContainer.scrollHeight;
            } else {
                completeProgress(progressMessage, `❌ Failed: ${file.name}`);
                const errMsg = result.error || result.details || result.message || 'Failed to upload document.';
                alert(errMsg);
            }
        } catch (error) {
            completeProgress(progressMessage, `❌ Failed: ${file.name}`);
            console.error('Error uploading document:', error);
            alert('Failed to upload document.');
        }
    }
    
    function updateSuggestionsForDocument() {
        const suggestionsContainer = document.querySelector('.suggestions');
        suggestionsContainer.innerHTML = '';
        const newSuggestions = [
            { question: "Can you summarize the document?", text: "Summarize the document" },
            { question: "What are the main arguments in the document?", text: "Main arguments" },
            { question: "How does this document relate to water management?", text: "Water management relevance" },
            { question: "What methodologies are used in this research?", text: "Research methodologies" }
        ];
        
        newSuggestions.forEach(suggestion => {
            const suggestionElement = document.createElement('div');
            suggestionElement.classList.add('suggestion');
            suggestionElement.setAttribute('data-question', suggestion.question);
            suggestionElement.textContent = suggestion.text;
            suggestionElement.addEventListener('click', function() {
                userInput.value = this.getAttribute('data-question');
                sendMessage();
            });
            suggestionsContainer.appendChild(suggestionElement);
        });
    }
    
    async function sendMessage() {
        const message = userInput.value.trim();
        if (message === '') return;

        addMessageToChat(message, 'user');
        userInput.value = '';
        typingIndicator.style.display = 'block';
        chatContainer.scrollTop = chatContainer.scrollHeight;

        try {
            const response = await fetch('/api/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, chat_id: currentChatId })
            });
            const result = await response.json();
            typingIndicator.style.display = 'none';
            if (response.ok) {
                addMessageToChat(result.response, 'bot');
            } else {
                addMessageToChat(`Error: ${result.error}`, 'bot');
            }
        } catch (error) {
            typingIndicator.style.display = 'none';
            addMessageToChat('Error: Failed to connect to the server.', 'bot');
        }
    }
    
    function addMessageToChat(message, sender, isSystem = false) {
        if (isSystem) {
            const systemMessage = document.createElement('div');
            systemMessage.classList.add('message', 'bot-message');
            systemMessage.style.fontStyle = 'italic';
            systemMessage.style.opacity = '0.8';
            systemMessage.innerHTML = `
                <div>${message}</div>
                <div class="message-time">${getCurrentTime()}</div>
            `;
            chatContainer.insertBefore(systemMessage, typingIndicator);
        } else {
            const messageElement = document.createElement('div');
            messageElement.classList.add('message');
            messageElement.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
            messageElement.innerHTML = `
                <div>${message}</div>
                <div class="message-time">${getCurrentTime()}</div>
            `;
            chatContainer.insertBefore(messageElement, typingIndicator);
        }
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    
    function getCurrentTime() {
        const now = new Date();
        return now.getHours().toString().padStart(2, '0') + ':' + 
               now.getMinutes().toString().padStart(2, '0');
    }
});

// Mini sidebar functionality for large screens
function initMiniSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');
    if (window.innerWidth >= 1025) {
        const savedState = localStorage.getItem('sidebarCollapsed');
        if (savedState === 'true') {
            sidebar.classList.add('collapsed');
            mainContent.classList.add('expanded');
            sidebar.style.display = 'flex';
            sidebar.style.transform = 'none';
        }
    }
}