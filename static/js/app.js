// JavaScript for CMS Rule Watcher - HackerNews style interactions

// Global state
let searchVisible = false;
let csrfToken = null;

// Get CSRF token from meta tag or global variable
function getCSRFToken() {
    if (!csrfToken) {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        csrfToken = metaTag ? metaTag.getAttribute('content') : window.csrfToken;
    }
    return csrfToken;
}

// Toggle search bar
function toggleSearch() {
    const searchBar = document.getElementById('search-bar');
    const searchInput = document.getElementById('search-input');
    
    searchVisible = !searchVisible;
    
    if (searchVisible) {
        searchBar.classList.remove('hidden');
        searchInput.focus();
    } else {
        searchBar.classList.add('hidden');
        searchInput.value = '';
    }
}

// Handle search input
function handleSearch(event) {
    if (event.key === 'Enter') {
        const query = event.target.value.trim();
        if (query) {
            searchDocuments(query);
        }
    }
}

// Search documents via API
async function searchDocuments(query) {
    try {
        const response = await fetch(`/api/documents?q=${encodeURIComponent(query)}`);
        const documents = await response.json();
        
        // Update page with search results
        updateDocumentList(documents);
        
        // Update URL without page reload
        const url = new URL(window.location);
        url.searchParams.set('q', query);
        window.history.pushState({}, '', url);
        
    } catch (error) {
        console.error('Search error:', error);
        alert('Search failed. Please try again.');
    }
}

// Update document list (for search results)
function updateDocumentList(documents) {
    const content = document.querySelector('.content');
    
    // Clear existing content
    content.innerHTML = '';
    
    if (documents.length === 0) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #828282;">No documents found.</div>';
        return;
    }
    
    // Render new documents
    documents.forEach((doc, index) => {
        const item = createDocumentElement(doc, index);
        content.appendChild(item);
    });
}

// Create document element
function createDocumentElement(doc, index) {
    const div = document.createElement('div');
    div.className = 'item';
    div.setAttribute('data-id', doc.document_number);
    
    div.innerHTML = `
        <div class="vote-section">
            <button class="vote-btn" onclick="vote('${doc.document_number}')">▲</button>
            <span class="vote-count">${doc.vote_count || 0}</span>
        </div>
        
        <div class="item-content">
            <div class="item-title">
                <a href="${doc.html_url}" target="_blank" class="title-link">
                    ${doc.title.length > 120 ? doc.title.substring(0, 120) + '...' : doc.title}
                </a>
                <span class="domain">(federalregister.gov)</span>
            </div>
            
            <div class="item-meta">
                <span class="points">${doc.vote_count || 0} points</span>
                <span class="separator">|</span>
                <span class="time">${formatTimeAgo(doc.publication_date)}</span>
                <span class="separator">|</span>
                <span class="agency">${(doc.agency_names || []).slice(0, 2).join(', ')}</span>
                <span class="separator">|</span>
                <a href="#" onclick="toggleComments('${doc.document_number}')" class="comment-link">discuss</a>
            </div>

            <div id="comments-${doc.document_number}" class="comments-section hidden">
                <div class="comment-form">
                    <textarea id="comment-text-${doc.document_number}" placeholder="Add your thoughts on this rule..."></textarea>
                    <div class="comment-form-footer">
                        <input type="text" id="comment-author-${doc.document_number}" placeholder="Your name" style="width: 150px;">
                        <button onclick="addComment('${doc.document_number}')">Add Comment</button>
                    </div>
                </div>
                <div id="comment-list-${doc.document_number}" class="comment-list">
                    <!-- Comments will be loaded here -->
                </div>
            </div>
        </div>
    `;
    
    return div;
}

// Format time ago (client-side version)
function formatTimeAgo(dateStr) {
    try {
        const date = new Date(dateStr);
        const now = new Date();
        const diffTime = Math.abs(now - date);
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays === 0) return 'today';
        if (diffDays === 1) return '1 day ago';
        if (diffDays < 30) return `${diffDays} days ago`;
        if (diffDays < 365) {
            const months = Math.floor(diffDays / 30);
            return `${months} month${months > 1 ? 's' : ''} ago`;
        }
        const years = Math.floor(diffDays / 365);
        return `${years} year${years > 1 ? 's' : ''} ago`;
    } catch {
        return dateStr;
    }
}

// Vote on a document
async function vote(documentId) {
    const voteBtn = document.querySelector(`[data-id="${documentId}"] .vote-btn`);
    const voteCount = document.querySelector(`[data-id="${documentId}"] .vote-count`);
    const pointsSpan = document.querySelector(`[data-id="${documentId}"] .points`);
    
    // Prevent double voting
    if (voteBtn.classList.contains('voted')) {
        return;
    }
    
    // Optimistic UI update
    voteBtn.classList.add('voted');
    const currentCount = parseInt(voteCount.textContent) || 0;
    const newCount = currentCount + 1;
    voteCount.textContent = newCount;
    pointsSpan.textContent = `${newCount} points`;
    
    try {
        const response = await fetch('/vote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                document_id: documentId,
                csrf_token: getCSRFToken()
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Update with server response
            voteCount.textContent = result.vote_count;
            pointsSpan.textContent = `${result.vote_count} points`;
        } else {
            // Revert on error
            voteBtn.classList.remove('voted');
            voteCount.textContent = currentCount;
            pointsSpan.textContent = `${currentCount} points`;
            
            if (result.error) {
                console.warn('Vote error:', result.error);
            }
        }
        
    } catch (error) {
        console.error('Vote error:', error);
        // Revert on error
        voteBtn.classList.remove('voted');
        voteCount.textContent = currentCount;
        pointsSpan.textContent = `${currentCount} points`;
    }
}

// Toggle comments section
function toggleComments(documentId) {
    const commentsSection = document.getElementById(`comments-${documentId}`);
    const isHidden = commentsSection.classList.contains('hidden');
    
    if (isHidden) {
        commentsSection.classList.remove('hidden');
        loadComments(documentId);
    } else {
        commentsSection.classList.add('hidden');
    }
}

// Load comments for a document
async function loadComments(documentId) {
    const commentList = document.getElementById(`comment-list-${documentId}`);
    
    // For now, comments are stored in memory on the server
    // In a real app, you'd fetch from a database
    commentList.innerHTML = '<div style="color: #828282; font-size: 8pt;">No comments yet. Be the first to discuss this rule!</div>';
}

// Add comment to a document
async function addComment(documentId) {
    const commentText = document.getElementById(`comment-text-${documentId}`).value.trim();
    const author = document.getElementById(`comment-author-${documentId}`).value.trim() || 'Anonymous';
    
    if (!commentText) {
        alert('Please enter a comment');
        return;
    }
    
    if (commentText.length > 1000) {
        alert('Comment too long (max 1000 characters)');
        return;
    }
    
    if (author.length > 50) {
        alert('Author name too long (max 50 characters)');
        return;
    }
    
    try {
        const response = await fetch('/comment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                document_id: documentId,
                comment: commentText,
                author: author,
                csrf_token: getCSRFToken()
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Clear form
            document.getElementById(`comment-text-${documentId}`).value = '';
            document.getElementById(`comment-author-${documentId}`).value = '';
            
            // Add comment to UI
            const commentList = document.getElementById(`comment-list-${documentId}`);
            const commentDiv = document.createElement('div');
            commentDiv.className = 'comment';
            commentDiv.innerHTML = `
                <div class="comment-header">
                    <strong>${escapeHtml(author)}</strong> • just now
                </div>
                <div class="comment-text">${escapeHtml(commentText)}</div>
            `;
            
            // Replace "no comments" message or add to existing
            if (commentList.textContent.includes('No comments yet')) {
                commentList.innerHTML = '';
            }
            commentList.appendChild(commentDiv);
            
            // Update comment count in meta
            const commentLink = document.querySelector(`[data-id="${documentId}"] .comment-link`);
            const metaDiv = commentLink.parentElement;
            
            // Update or add comment count
            let commentCountSpan = metaDiv.querySelector('.comments');
            if (commentCountSpan) {
                commentCountSpan.textContent = `${result.comment_count} comments`;
            } else {
                const separator = document.createElement('span');
                separator.className = 'separator';
                separator.textContent = '|';
                
                commentCountSpan = document.createElement('span');
                commentCountSpan.className = 'comments';
                commentCountSpan.textContent = `${result.comment_count} comments`;
                
                commentLink.parentElement.insertBefore(separator, commentLink);
                commentLink.parentElement.insertBefore(commentCountSpan, commentLink);
            }
            
        } else {
            alert(result.error || 'Failed to add comment. Please try again.');
        }
        
    } catch (error) {
        console.error('Comment error:', error);
        alert('Failed to add comment. Please try again.');
    }
}

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Handle browser back/forward
window.addEventListener('popstate', function(event) {
    const url = new URL(window.location);
    const query = url.searchParams.get('q');
    
    if (query) {
        document.getElementById('search-input').value = query;
        searchDocuments(query);
    } else {
        // Reload page to show default content
        window.location.reload();
    }
});

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Check if there's a search query in URL
    const url = new URL(window.location);
    const query = url.searchParams.get('q');
    
    if (query) {
        document.getElementById('search-input').value = query;
        toggleSearch();
    }
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        // Press '/' to focus search
        if (event.key === '/' && !searchVisible) {
            event.preventDefault();
            toggleSearch();
        }
        
        // Press 'Escape' to close search
        if (event.key === 'Escape' && searchVisible) {
            toggleSearch();
        }
    });
}); 