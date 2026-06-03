// Configuration
const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    PAGE_SIZE: 20,
};

const API_URL = `${CONFIG.API_BASE_URL}/media-assets/library`;

// Application State
const state = {
    currentPage: 1,
    totalPages: 1,

    filters: {
        search: '',
        media_type: '',
    },

    hlsPlayer: null,
};

// DOM Elements
const elements = {
    searchInput: document.getElementById('searchInput'),
    searchBtn: document.getElementById('searchBtn'),
    mediaTypeFilter: document.getElementById('mediaTypeFilter'),

    videosGrid: document.getElementById('videosGrid'),

    playerSection: document.getElementById('playerSection'),
    videoPlayer: document.getElementById('videoPlayer'),

    currentTitle: document.getElementById('currentTitle'),
    currentDescription: document.getElementById('currentDescription'),
    videoDuration: document.getElementById('videoDuration'),

    prevPage: document.getElementById('prevPage'),
    nextPage: document.getElementById('nextPage'),
    pageInfo: document.getElementById('pageInfo'),
};


// Initialization
document.addEventListener('DOMContentLoaded', init);

function init() {
    bindEvents();
    loadMedia();
}

function bindEvents() {
    elements.searchBtn.addEventListener('click', performSearch);

    elements.searchInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            performSearch();
        }
    });

    elements.mediaTypeFilter.addEventListener('change', () => {
        state.currentPage = 1;
        updateFilters();
        loadMedia();
    });

    elements.prevPage.addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            loadMedia();
        }
    });

    elements.nextPage.addEventListener('click', () => {
        if (state.currentPage < state.totalPages) {
            state.currentPage++;
            loadMedia();
        }
    });
}

// Search
function performSearch() {
    state.currentPage = 1;
    updateFilters();
    loadMedia();
}

function updateFilters() {
    state.filters.search = elements.searchInput.value.trim();
    state.filters.media_type = elements.mediaTypeFilter.value;
}

// API
async function fetchLibrary() {
    const params = new URLSearchParams({
        limit: CONFIG.PAGE_SIZE,
        offset: (state.currentPage - 1) * CONFIG.PAGE_SIZE,
    });

    if (state.filters.search) {
        params.append('search', state.filters.search);
    }

    if (state.filters.media_type) {
        params.append('media_type', state.filters.media_type);
    }

    const response = await fetch(`${API_URL}?${params}`);

    if (!response.ok) {
        throw new Error(
            `Request failed with status ${response.status}`
        );
    }

    return response.json();
}


// Media Loading
async function loadMedia() {
    showLoading();

    try {
        setLoadingState(true);

        const data = await fetchLibrary();

        state.totalPages = data.pages || 1;

        updatePagination();

        if (!data.items?.length) {
            showEmptyState();
            return;
        }

        renderMediaCards(data.items);

    } catch (error) {
        console.error(error);
        showErrorState();
    } finally {
        setLoadingState(false);
    }
}

// Rendering
function renderMediaCards(mediaItems) {
    elements.videosGrid.innerHTML = '';

    mediaItems.forEach((item) => {
        const card = createMediaCard(item);
        elements.videosGrid.appendChild(card);
    });
}

function createMediaCard(media) {
    const card = document.createElement('div');
    card.className = 'video-card';

    const thumbnail =
        media.thumbnail_medium ||
        media.thumbnail_small ||
        'images/default-thumbnail.jpg';

    const duration = formatDuration(
        media.duration_seconds
    );

    const qualityBadge =
        media.available_qualities?.length
            ? `<span class="quality-badge">${media.available_qualities[0]}</span>`
            : '';

    card.innerHTML = `
        <div class="thumbnail">
            <img
                src="${thumbnail}"
                alt="${escapeHtml(media.title)}"
                loading="lazy"
                onerror="this.src='images/default-thumbnail.jpg'"
            >
            <span class="duration">${duration}</span>
        </div>

        <div class="card-content">
            <div class="card-title">
                ${escapeHtml(media.title)}
            </div>

            <div class="card-description">
                ${escapeHtml(
                    media.description || 'No description available'
                )}
            </div>

            <div class="card-stats">
                <span>${media.media_type || 'Media'}</span>
                ${qualityBadge}
            </div>
        </div>
    `;

    card.addEventListener('click', () => {
        playMedia(media);

        document
            .querySelectorAll('.video-card')
            .forEach((c) =>
                c.classList.remove('active')
            );

        card.classList.add('active');
    });

    return card;
}


// Player
function playMedia(media) {
    elements.playerSection.style.display = 'block';

    elements.currentTitle.textContent =
        media.title;

    elements.currentDescription.textContent =
        media.description || 'No description available';

    elements.videoDuration.textContent =
        formatDuration(media.duration_seconds);

    elements.playerSection.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
    });

    initializePlayer(media.hls_master_playlist);
}

function initializePlayer(hlsUrl) {
    if (!hlsUrl) {
        alert('No streaming source available.');
        return;
    }

    const videoElement = elements.videoPlayer;

    cleanupPlayer();

    if (Hls.isSupported()) {
        state.hlsPlayer = new Hls({
            debug: false,
            enableWorker: true,
        });

        state.hlsPlayer.loadSource(hlsUrl);
        state.hlsPlayer.attachMedia(videoElement);

        state.hlsPlayer.on(
            Hls.Events.ERROR,
            handleHlsError
        );

        return;
    }

    if (
        videoElement.canPlayType(
            'application/vnd.apple.mpegurl'
        )
    ) {
        videoElement.src = hlsUrl;
        return;
    }

    alert(
        'Your browser does not support HLS playback.'
    );
}

function cleanupPlayer() {
    if (state.hlsPlayer) {
        state.hlsPlayer.destroy();
        state.hlsPlayer = null;
    }
}

function handleHlsError(event, data) {
    console.error('HLS Error:', data);

    if (!data.fatal) return;

    switch (data.type) {
        case Hls.ErrorTypes.NETWORK_ERROR:
            state.hlsPlayer?.startLoad();
            break;

        case Hls.ErrorTypes.MEDIA_ERROR:
            state.hlsPlayer?.recoverMediaError();
            break;

        default:
            cleanupPlayer();
    }
}


// Pagination
function updatePagination() {
    elements.prevPage.disabled =
        state.currentPage <= 1;

    elements.nextPage.disabled =
        state.currentPage >= state.totalPages;

    elements.pageInfo.textContent =
        `Page ${state.currentPage} of ${state.totalPages}`;
}


// UI States
function showLoading() {
    elements.videosGrid.innerHTML = `
        <div class="loading">
            Loading media...
        </div>
    `;
}

function showEmptyState() {
    elements.videosGrid.innerHTML = `
        <div class="loading">
            No media found.
        </div>
    `;
}

function showErrorState() {
    elements.videosGrid.innerHTML = `
        <div class="loading">
            Unable to load media library.
        </div>
    `;
}

function setLoadingState(isLoading) {
    elements.searchBtn.disabled = isLoading;

    elements.searchBtn.textContent = isLoading
        ? 'Loading...'
        : 'Search';
}

// Utilities
function formatDuration(seconds) {
    if (!seconds) return '0:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor(
        (seconds % 3600) / 60
    );
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(
            2,
            '0'
        )}:${String(secs).padStart(2, '0')}`;
    }

    return `${minutes}:${String(secs).padStart(
        2,
        '0'
    )}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}