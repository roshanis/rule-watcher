// JavaScript for CMS Rule Watcher - HackerNews style interactions

// Global state
let searchVisible = false;
let csrfToken = null;

// Get CSRF token from meta tag only (secure approach)
function getCSRFToken() {
    if (!csrfToken) {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        csrfToken = metaTag ? metaTag.getAttribute('content') : null;
    }
    return csrfToken;
}

// HTML escaping function to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
        const noDocsDiv = document.createElement('div');
        noDocsDiv.style.padding = '20px';
        noDocsDiv.style.textAlign = 'center';
        noDocsDiv.style.color = '#828282';
        noDocsDiv.textContent = 'No documents found.';
        content.appendChild(noDocsDiv);
        return;
    }
    
    // Render new documents
    documents.forEach((doc, index) => {
        const item = createDocumentElement(doc, index);
        content.appendChild(item);
    });
}

// Create document element with proper XSS protection
function createDocumentElement(doc, index) {
    const div = document.createElement('div');
    div.className = 'item';
    div.setAttribute('data-id', escapeHtml(doc.id || doc.document_number || ''));
    
    // Create vote section
    const voteSection = document.createElement('div');
    voteSection.className = 'vote-section';
    
    const voteBtn = document.createElement('button');
    voteBtn.className = 'vote-btn';
    voteBtn.textContent = '▲';
    voteBtn.onclick = () => vote(doc.id || doc.document_number);
    
    const voteCount = document.createElement('span');
    voteCount.className = 'vote-count';
    voteCount.textContent = doc.votes || doc.vote_count || 0;
    
    voteSection.appendChild(voteBtn);
    voteSection.appendChild(voteCount);
    
    // Create content section
    const itemContent = document.createElement('div');
    itemContent.className = 'item-content';
    
    // Title section
    const titleDiv = document.createElement('div');
    titleDiv.className = 'item-title';
    
    const titleLink = document.createElement('a');
    titleLink.href = doc.url || doc.html_url || '';
    titleLink.target = '_blank';
    titleLink.className = 'title-link';
    const title = doc.title || 'Untitled Document';
    titleLink.textContent = title.length > 120 ? title.substring(0, 120) + '...' : title;
    
    const domain = document.createElement('span');
    domain.className = 'domain';
    domain.textContent = '(federalregister.gov)';
    
    titleDiv.appendChild(titleLink);
    titleDiv.appendChild(domain);
    
    // Meta section
    const metaDiv = document.createElement('div');
    metaDiv.className = 'item-meta';
    
    const points = document.createElement('span');
    points.className = 'points';
    points.textContent = `${doc.votes || doc.vote_count || 0} points`;
    
    const sep1 = document.createElement('span');
    sep1.className = 'separator';
    sep1.textContent = '|';
    
    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = formatTimeAgo(doc.date || doc.publication_date);
    
    const sep2 = document.createElement('span');
    sep2.className = 'separator';
    sep2.textContent = '|';
    
    const agency = document.createElement('span');
    agency.className = 'agency';
    const agencyNames = doc.agency || (doc.agency_names || []).slice(0, 2).join(', ') || 'Unknown Agency';
    agency.textContent = agencyNames;
    
    const sep3 = document.createElement('span');
    sep3.className = 'separator';
    sep3.textContent = '|';
    
    const discussLink = document.createElement('a');
    discussLink.href = '#';
    discussLink.className = 'comment-link';
    discussLink.textContent = 'discuss';
    discussLink.onclick = (e) => {
        e.preventDefault();
        toggleComments(doc.id || doc.document_number);
    };
    
    metaDiv.appendChild(points);
    metaDiv.appendChild(sep1);
    metaDiv.appendChild(time);
    metaDiv.appendChild(sep2);
    metaDiv.appendChild(agency);
    metaDiv.appendChild(sep3);
    metaDiv.appendChild(discussLink);
    
    // Comments section
    const commentsSection = document.createElement('div');
    commentsSection.id = `comments-${doc.id || doc.document_number}`;
    commentsSection.className = 'comments-section hidden';
    
    // Comment form
    const commentForm = document.createElement('div');
    commentForm.className = 'comment-form';
    
    const textarea = document.createElement('textarea');
    textarea.id = `comment-text-${doc.id || doc.document_number}`;
    textarea.placeholder = 'Add your thoughts on this rule...';
    
    const formFooter = document.createElement('div');
    formFooter.className = 'comment-form-footer';
    
    const authorInput = document.createElement('input');
    authorInput.type = 'text';
    authorInput.id = `comment-author-${doc.id || doc.document_number}`;
    authorInput.placeholder = 'Your name';
    authorInput.style.width = '150px';
    
    const submitBtn = document.createElement('button');
    submitBtn.textContent = 'Add Comment';
    submitBtn.onclick = () => addComment(doc.id || doc.document_number);
    
    formFooter.appendChild(authorInput);
    formFooter.appendChild(submitBtn);
    
    commentForm.appendChild(textarea);
    commentForm.appendChild(formFooter);
    
    const commentList = document.createElement('div');
    commentList.id = `comment-list-${doc.id || doc.document_number}`;
    commentList.className = 'comment-list';
    
    commentsSection.appendChild(commentForm);
    commentsSection.appendChild(commentList);
    
    // Assemble everything
    itemContent.appendChild(titleDiv);
    itemContent.appendChild(metaDiv);
    itemContent.appendChild(commentsSection);
    
    div.appendChild(voteSection);
    div.appendChild(itemContent);
    
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