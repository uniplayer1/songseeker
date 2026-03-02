import QrScanner from "https://unpkg.com/qr-scanner/qr-scanner.min.js";

// --- GLOBAL VARIABLES & STATE ---
let player; // YouTube player instance
let playbackTimer; // Reference for the random playback timeout
let playbackDuration = 30; // Default playback duration in seconds
let qrScanner;
let csvCache = {};
let lastDecodedText = ""; // Store the last decoded text to prevent double-scans
let currentScannedLink = ""; // Store the link for the currently active song
let currentStartTime = 0;
let currentPlayerType = 'youtube'; // 'youtube' or 'local'
let audioCtx;
let audioSource;
let compressor;

// --- CONSTANTS ---
const UI = {
    video: () => document.getElementById('qr-video'),
    reader: () => document.getElementById('qr-reader'),
    startScanBtn: () => document.getElementById('startScanButton'),
    cancelScanBtn: () => document.getElementById('cancelScanButton'),
    reportBtn: () => document.getElementById('reportButton'),
    playStopBtn: () => document.getElementById('startstop-video'),
    localPlayer: () => document.getElementById('local-player'),
    videoId: () => document.getElementById('video-id'),
    videoTitle: () => document.getElementById('video-title'),
    videoDuration: () => document.getElementById('video-duration'),
    videoYear: () => document.getElementById('video-year'),
    autoplayCb: () => document.getElementById('autoplay'),
    normalizeCb: () => document.getElementById('normalize'),
    normalizeSettingCb: () => document.getElementById('normalize-setting'),
    randomPlaybackCb: () => document.getElementById('randomplayback'),
    playbackDurationInput: () => document.getElementById('playback-duration'),
    songInfoCb: () => document.getElementById('songinfo'),
    cookiesCb: () => document.getElementById('cookies'),
    cookieList: () => document.getElementById('cookielist'),
    reportModal: () => document.getElementById('reportModal'),
    reportSongTitle: () => document.getElementById('reportSongTitle'),
    reportReason: () => document.getElementById('reportReason'),
    reportListModal: () => document.getElementById('reportListModal'),
    reportsList: () => document.getElementById('reportsList'),
    equalizer: () => document.getElementById('equalizer')
};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    initQrScanner();
    initEventListeners();
    initYouTubeApi();
    loadPersistedSettings();
});

function initQrScanner() {
    qrScanner = new QrScanner(UI.video(), result => {
        console.log('Decoded QR code:', result);
        if (result.data !== lastDecodedText) {
            lastDecodedText = result.data;
            handleScannedLink(result.data);
        }
    }, { 
        highlightScanRegion: true,
        highlightCodeOutline: true,
    });
    
    // Initial UI state
    UI.reader().style.display = 'none';
}

function initEventListeners() {
    // Reporting
    UI.reportBtn().addEventListener('click', () => {
        const currentTitle = UI.videoTitle().textContent;
        UI.reportSongTitle().textContent = currentTitle || "Unknown";
        UI.reportModal().classList.remove('hidden');
    });

    document.getElementById('cancelReport').addEventListener('click', () => {
        UI.reportModal().classList.add('hidden');
    });

    document.getElementById('submitReport').addEventListener('click', submitReport);

    // Scanning
    UI.startScanBtn().addEventListener('click', startScanning);
    UI.cancelScanBtn().addEventListener('click', stopScanning);

    // Playback
    UI.playStopBtn().addEventListener('click', togglePlayback);

    // Settings & UI Toggles
    document.getElementById('settingsIcon').addEventListener('click', toggleSettings);
    document.getElementById('autoplayIcon').addEventListener('click', toggleAutoplay);
    document.getElementById('normalizeIcon').addEventListener('click', toggleNormalization);
    document.getElementById('reportsIcon').addEventListener('click', showReports);
    document.getElementById('closeReports').addEventListener('click', () => {
        UI.reportListModal().classList.add('hidden');
    });

    UI.songInfoCb().addEventListener('click', toggleSongInfoVisibility);
    UI.cookiesCb().addEventListener('click', toggleCookieListVisibility);
    UI.randomPlaybackCb().addEventListener('click', () => {
        saveSetting("RandomPlaybackChecked", UI.randomPlaybackCb().checked);
    });
    UI.autoplayCb().addEventListener('click', () => {
        saveSetting("autoplayChecked", UI.autoplayCb().checked);
        updateAutoplayIcon();
    });
    UI.normalizeSettingCb().addEventListener('click', () => {
        UI.normalizeCb().checked = UI.normalizeSettingCb().checked;
        saveSetting("normalizeChecked", UI.normalizeCb().checked);
        updateNormalizeIcon();
        applyNormalization();
    });

    // Debug button
    document.getElementById('debugButton').addEventListener('click', () => {
        handleScannedLink("https://www.hitstergame.com/de-aaaa0012/237");
    });
}

// --- CORE LOGIC: SCANNING ---
async function handleScannedLink(decodedText) {
    currentScannedLink = decodedText; // Save the link for reporting
    // Check if local audio
    if (decodedText.toLowerCase().endsWith('.mp3') || decodedText.toLowerCase().endsWith('.wav')) {
        playLocalAudio(decodedText);
        return;
    }

    let youtubeURL = "";
    currentPlayerType = 'youtube';

    if (isYoutubeLink(decodedText)) {
        youtubeURL = decodedText;
    } else if (isHitsterLink(decodedText)) {
        const hitsterData = parseHitsterUrl(decodedText);
        if (hitsterData) {
            try {
                const csvContent = await getCachedCsv(`/playlists/hitster-${hitsterData.lang}.csv`);
                youtubeURL = lookupYoutubeLink(hitsterData.id, csvContent);
            } catch (error) {
                console.error("Failed to fetch Hitster CSV:", error);
            }
        }
    } else if (isRockster(decodedText)) {
        try {
            const urlObj = new URL(decodedText);
            const ytCode = urlObj.searchParams.get("yt");
            if (ytCode) youtubeURL = `https://www.youtube.com/watch?v=${ytCode}`;
        } catch (error) {
            console.error("Invalid Rockster URL:", error);
        }
    }

    if (youtubeURL) {
        const youtubeLinkData = parseYoutubeLink(youtubeURL);
        if (youtubeLinkData) {
            prepareUIForPlayback();
            UI.videoId().textContent = youtubeLinkData.videoId;
            currentStartTime = youtubeLinkData.startTime || 0;
            player.cueVideoById(youtubeLinkData.videoId, currentStartTime);
            UI.playStopBtn().disabled = false;
        }
    }
}

function startScanning() {
    const localPlayer = UI.localPlayer();
    // Reset local player to unlock audio context on mobile
    localPlayer.onloadedmetadata = null;
    clearTimeout(playbackTimer);

    // Audio unlock trick for mobile browsers
    localPlayer.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
    localPlayer.play().then(() => localPlayer.pause()).catch(() => {});
    
    if (player && player.pauseVideo) player.pauseVideo();

    resetPlaybackUI();
    UI.startScanBtn().style.display = 'none';
    UI.cancelScanBtn().style.display = 'block';
    UI.reader().style.display = 'block'; 
    
    qrScanner.start()
        .then(() => qrScanner.setInversionMode('both'))
        .catch(err => {
            console.error('Unable to start QR Scanner', err);
            UI.startScanBtn().style.display = 'block';
        });
}

function stopScanning() {
    qrScanner.stop();
    UI.reader().style.display = 'none';
    UI.cancelScanBtn().style.display = 'none';
    UI.startScanBtn().style.display = 'block';
}

function prepareUIForPlayback() {
    stopScanning();
    UI.reportBtn().style.display = 'block';
    lastDecodedText = ""; // Reset scanner so same link can be scanned again later
}

// --- CORE LOGIC: PLAYBACK ---
function togglePlayback() {
    const isPlaying = UI.playStopBtn().innerHTML === "Stop";
    
    if (isPlaying) {
        setPlaybackState(false);
        if (currentPlayerType === 'local') {
            UI.localPlayer().pause();
        } else {
            player.pauseVideo();
        }
        clearTimeout(playbackTimer);
    } else {
        setPlaybackState(true);
        if (UI.randomPlaybackCb().checked) {
            currentPlayerType === 'local' ? playLocalAtRandom() : playVideoAtRandom();
        } else {
            currentPlayerType === 'local' ? UI.localPlayer().play() : player.playVideo();
        }
    }
}

function setPlaybackState(playing) {
    const btn = UI.playStopBtn();
    if (playing) {
        btn.innerHTML = "Stop";
        btn.style.background = "var(--accent-stop)";
        toggleAnimation(true);
    } else {
        btn.innerHTML = "Play";
        btn.style.background = "var(--accent-play)";
        toggleAnimation(false);
    }
}

function calculateRandomTimes(duration, customStartTime = 0) {
    const minPct = 0.10;
    const maxPct = 0.90;
    const playbackLen = parseInt(UI.playbackDurationInput().value, 10) || 30;
    
    const minStart = Math.max(customStartTime, duration * minPct);
    const maxEnd = duration * maxPct;
    
    let startTime = customStartTime;
    let endTime = playbackLen;

    if (endTime > maxEnd) {
        endTime = maxEnd;
        startTime = Math.max(minStart, endTime - playbackLen);
    }

    if (startTime <= minStart) {
        const range = maxEnd - minStart - playbackLen;
        startTime = minStart + (Math.random() * Math.max(0, range));
        endTime = startTime + playbackLen;
    }

    return { startTime, endTime, duration: (endTime - startTime) * 1000 };
}

// --- LOCAL PLAYER ---
function setupAudioNodes() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        audioSource = audioCtx.createMediaElementSource(UI.localPlayer());
        compressor = audioCtx.createDynamicsCompressor();
        
        // Settings for "normalization"
        compressor.threshold.setValueAtTime(-24, audioCtx.currentTime);
        compressor.knee.setValueAtTime(40, audioCtx.currentTime);
        compressor.ratio.setValueAtTime(12, audioCtx.currentTime);
        compressor.attack.setValueAtTime(0, audioCtx.currentTime);
        compressor.release.setValueAtTime(0.25, audioCtx.currentTime);
        
        applyNormalization();
    } else if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function applyNormalization() {
    if (!audioSource) return;
    audioSource.disconnect();
    if (UI.normalizeCb().checked) {
        audioSource.connect(compressor);
        compressor.connect(audioCtx.destination);
    } else {
        audioSource.connect(audioCtx.destination);
    }
}

function playLocalAudio(url) {
    prepareUIForPlayback();
    currentPlayerType = 'local';
    
    setupAudioNodes();
    const localPlayer = UI.localPlayer();
    localPlayer.src = url;
    
    const fileName = url.substring(url.lastIndexOf('/') + 1);
    UI.videoId().textContent = "Local File";
    UI.videoTitle().textContent = `Loading... (${fileName})`;
    UI.videoYear().textContent = "Loading...";

    // Metadata extraction
    if (window.jsmediatags) {
        window.jsmediatags.read(url, {
            onSuccess: (tag) => {
                UI.videoTitle().textContent = tag.tags.title || fileName;
                UI.videoYear().textContent = tag.tags.year || "Unknown";
            },
            onError: (error) => {
                console.warn('Metadata not found:', error);
                UI.videoTitle().textContent = fileName;
                UI.videoYear().textContent = "Unknown";
            }
        });
    } else {
        UI.videoTitle().textContent = fileName;
        UI.videoYear().textContent = "Unknown";
    }

    localPlayer.onloadedmetadata = () => {
        UI.videoDuration().textContent = formatDuration(localPlayer.duration);
        UI.playStopBtn().disabled = false;
        UI.playStopBtn().style.background = "var(--accent-play)";
        
        if (UI.autoplayCb().checked) {
            togglePlayback();
        }
    };

    localPlayer.onended = () => setPlaybackState(false);
}

function playLocalAtRandom() {
    const lp = UI.localPlayer();
    const times = calculateRandomTimes(lp.duration);
    
    lp.currentTime = times.startTime;
    lp.play()
        .then(() => {
            toggleAnimation(true);
            clearTimeout(playbackTimer); 
            playbackTimer = setTimeout(() => {
                lp.pause();
                setPlaybackState(false);
            }, times.duration); 
        })
        .catch(err => {
            console.error("Local autoplay blocked:", err);
            setPlaybackState(false);
        });
}

// --- YOUTUBE PLAYER ---
function initYouTubeApi() {
    const tag = document.createElement('script');
    tag.src = "https://www.youtube.com/iframe_api";
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    window.onYouTubeIframeAPIReady = () => {
        player = new YT.Player('player', {
            height: '0',
            width: '0',
            events: {
                'onReady': (e) => { e.target.setVolume(100); e.target.unMute(); },
                'onStateChange': onPlayerStateChange
            }
        });
    };
}

function onPlayerStateChange(event) {
    if (event.data === YT.PlayerState.CUED) {
        UI.playStopBtn().style.background = "var(--accent-play)";
        const videoData = player.getVideoData();
        UI.videoTitle().textContent = videoData.title;
        UI.videoDuration().textContent = formatDuration(player.getDuration());
        UI.videoYear().textContent = "Unknown (YouTube API)";

        if (isIOS()) {
            player.playVideo();
        } else if (UI.autoplayCb().checked) {
            setPlaybackState(true);
            if (UI.randomPlaybackCb().checked) {
                playVideoAtRandom();
            } else {
                player.playVideo();
            }
        }
    } else if (event.data === YT.PlayerState.PLAYING) {
        setPlaybackState(true);
    } else if (event.data === YT.PlayerState.PAUSED || event.data === YT.PlayerState.ENDED) {
        setPlaybackState(false);
    } else if (event.data === YT.PlayerState.BUFFERING) {
        UI.playStopBtn().style.background = "orange";
    }
}

function playVideoAtRandom() {
    const times = calculateRandomTimes(player.getDuration(), currentStartTime);
    
    player.seekTo(times.startTime, true);
    player.playVideo();

    clearTimeout(playbackTimer);
    playbackTimer = setTimeout(() => {
        player.pauseVideo();
        setPlaybackState(false);
    }, times.duration);
}

// --- API & DATA ---
async function submitReport() {
    const reason = UI.reportReason().value;
    const title = UI.videoTitle().textContent;
    const videoIdText = UI.videoId().textContent;
    
    let resolvedUrl = "";
    if (currentPlayerType === 'local') {
        resolvedUrl = UI.localPlayer().src || currentScannedLink;
    } else {
        resolvedUrl = videoIdText ? `https://www.youtube.com/watch?v=${videoIdText}` : currentScannedLink;
    }

    try {
        await fetch('/api/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                type: currentPlayerType,
                title: title, 
                reason: reason,
                resolvedUrl: resolvedUrl,      
                originalScan: currentScannedLink  
            })
        });
        
        const btn = UI.reportBtn();
        const originalText = btn.textContent;
        btn.textContent = "Reported!";
        btn.style.borderColor = "var(--accent-play)";
        btn.style.color = "var(--accent-play)";
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.borderColor = "var(--accent-wait)";
            btn.style.color = "var(--accent-wait)";
        }, 3000);

    } catch (error) {
        console.error('Report failed:', error);
        alert('Could not submit report.');
    }
    
    UI.reportModal().classList.add('hidden');
}

async function showReports() {
    try {
        const response = await fetch('/api/reports');
        if (!response.ok) throw new Error('failed to fetch reports');
        const reports = await response.json();
        
        UI.reportsList().innerHTML = '';
        
        if (reports.length === 0) {
            UI.reportsList().textContent = 'No reports yet';
        } else {
            // Sort by latest first
            reports.reverse().forEach(report => {
                const reportEl = document.createElement('div');
                reportEl.className = 'report-entry';
                
                const date = new Date(report.timestamp).toLocaleString();
                
                reportEl.innerHTML = `
                    <div class="report-header">
                        <span class="report-type ${report.type.toLowerCase()}">${report.type}</span>
                        <span class="report-date">${date}</span>
                    </div>
                    <div class="report-title">${report.title}</div>
                    <div class="report-reason">Reason: ${formatReason(report.reason)}</div>
                    <div class="report-links">
                        <a href="${report.resolvedUrl}" target="_blank" title="Playing Link"><i class="fa fa-play-circle"></i> Played</a>
                        <a href="${report.originalScan}" target="_blank" title="Original Scan"><i class="fa fa-qrcode"></i> Scanned</a>
                    </div>
                `;
                UI.reportsList().appendChild(reportEl);
            });
        }
        
        UI.reportListModal().classList.remove('hidden');
    } catch (err) {
        console.error(err);
        alert('Unable to load report list');
    }
}

function formatReason(reason) {
    return reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

async function getCachedCsv(url) {
    if (!csvCache[url]) {
        const response = await fetch(url);
        const data = await response.text();
        csvCache[url] = parseCSV(data);
    }
    return csvCache[url];
}

// --- UTILITIES ---
function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function isHitsterLink(url) {
    return /^(?:http:\/\/|https:\/\/)?(www\.hitstergame|app\.hitsternordics)\.com\/.+/.test(url);
}

function isYoutubeLink(url) {
    return url.startsWith("https://www.youtube.com") || url.startsWith("https://youtu.be") || url.startsWith("https://music.youtube.com/");
}

function isRockster(url) {
    return url.startsWith("https://rockster.brettspiel.digital");
}

function parseHitsterUrl(url) {
    const gameMatch = url.match(/^(?:http:\/\/|https:\/\/)?www\.hitstergame\.com\/(.+?)\/(\d+)$/);
    if (gameMatch) {
        return { lang: gameMatch[1].replace(/\//g, "-"), id: gameMatch[2] };
    }
    const nordicMatch = url.match(/^(?:http:\/\/|https:\/\/)?app.hitster(nordics).com\/resources\/songs\/(\d+)$/);
    if (nordicMatch) {
        return { lang: nordicMatch[1], id: nordicMatch[2] };
    }
    return null;
}

function lookupYoutubeLink(id, csvContent) {
    const headers = csvContent[0];
    const cardIdx = headers.indexOf('Card#');
    const urlIdx = headers.indexOf('URL');
    if (cardIdx === -1 || urlIdx === -1) throw new Error('CSV columns missing');

    const targetId = parseInt(id, 10);
    for (let i = 1; i < csvContent.length; i++) {
        if (parseInt(csvContent[i][cardIdx], 10) === targetId) {
            return csvContent[i][urlIdx].trim();
        }
    }
    return null;
}

function parseCSV(text) {
    return text.split('\n').filter(l => l.trim()).map(line => {
        const result = [];
        let start = 0, inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            if (line[i] === '"' && line[i-1] !== '\\') inQuotes = !inQuotes;
            else if (line[i] === ',' && !inQuotes) {
                result.push(line.substring(start, i).trim().replace(/^"(.*)"$/, '$1'));
                start = i + 1;
            }
        }
        result.push(line.substring(start).trim().replace(/^"(.*)"$/, '$1'));
        return result;
    });
}

function parseYoutubeLink(url) {
    url = decodeURIComponent(url);
    const regex = /^https?:\/\/(www\.youtube\.com\/watch\?v=|youtu\.be\/|music\.youtube\.com\/watch\?v=)(.{11})(.*)/;
    const match = url.match(regex);
    if (match) {
        const queryParams = new URLSearchParams(match[3]);
        const videoId = match[2];
        const start = normalizeTime(queryParams.get('start') || queryParams.get('t'));
        const end = normalizeTime(queryParams.get('end'));
        return { videoId, startTime: start, endTime: end };
    }
    return null;
}

function normalizeTime(val) {
    if (!val) return null;
    const seconds = parseInt(val, 10);
    return isNaN(seconds) ? null : seconds;
}

function formatDuration(duration) {
    const mins = Math.floor(duration / 60);
    const secs = Math.floor(duration % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

// --- SETTINGS & COOKIES ---
function loadPersistedSettings() {
    if (isIOS()) {
        const autoplay = UI.autoplayCb();
        autoplay.checked = false;
        autoplay.disabled = true;
    } else {
        const autoplayCookie = getCookie("autoplayChecked");
        if (autoplayCookie !== "") UI.autoplayCb().checked = (autoplayCookie === 'true');
    }

    const randomCookie = getCookie("RandomPlaybackChecked");
    if (randomCookie !== "") UI.randomPlaybackCb().checked = (randomCookie === 'true');

    const normalizeCookie = getCookie("normalizeChecked");
    if (normalizeCookie !== "") {
        UI.normalizeCb().checked = (normalizeCookie === 'true');
    } else {
        // Default to true
        UI.normalizeCb().checked = true;
    }
    UI.normalizeSettingCb().checked = UI.normalizeCb().checked;

    updateAutoplayIcon();
    updateNormalizeIcon();
    renderCookieList();
}

function saveSetting(name, value) {
    document.cookie = `${name}=${value};max-age=2592000;path=/`; // 30 days
    renderCookieList();
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? match[2] : "";
}

function renderCookieList() {
    UI.cookieList().innerHTML = document.cookie;
}

// --- UI HELPERS ---
function toggleSettings() {
    const div = document.getElementById('settings_div');
    const icon = document.getElementById('settingsIcon');
    const isHidden = div.classList.toggle('hidden');
    icon.classList.toggle('active', !isHidden);
}

function toggleAutoplay() {
    const cb = UI.autoplayCb();
    if (cb.disabled) return;
    cb.checked = !cb.checked;
    saveSetting("autoplayChecked", cb.checked);
    updateAutoplayIcon();
}

function toggleNormalization() {
    const cb = UI.normalizeCb();
    cb.checked = !cb.checked;
    UI.normalizeSettingCb().checked = cb.checked;
    saveSetting("normalizeChecked", cb.checked);
    updateNormalizeIcon();
    applyNormalization();
}

function updateAutoplayIcon() {
    const icon = document.getElementById('autoplayIcon');
    const cb = UI.autoplayCb();
    if (!cb) return;

    icon.classList.toggle('active', cb.checked);
    const iconEl = icon.querySelector('i');
    iconEl.className = `fa ${cb.checked ? 'fa-pause' : 'fa-play'}`;

    if (cb.disabled) {
        icon.classList.add('disabled');
        iconEl.classList.add('fa-ban');
    } else {
        icon.classList.remove('disabled');
        iconEl.classList.remove('fa-ban');
    }
}

function updateNormalizeIcon() {
    const icon = document.getElementById('normalizeIcon');
    const cb = UI.normalizeCb();
    if (!cb) return;

    icon.classList.toggle('active', cb.checked);
}

function toggleSongInfoVisibility() {
    const show = UI.songInfoCb().checked;
    const elements = [UI.videoId().parentElement, UI.videoTitle().parentElement, UI.videoDuration().parentElement, UI.videoYear().parentElement];
    elements.forEach(el => el.style.display = show ? 'block' : 'none');
}

function toggleCookieListVisibility() {
    UI.cookieList().style.display = UI.cookiesCb().checked ? 'block' : 'none';
}

function toggleAnimation(isPlaying) {
    const eq = UI.equalizer();
    if (eq) eq.classList.toggle('playing', isPlaying);
}

function resetPlaybackUI() {
    setPlaybackState(false);
    UI.playStopBtn().disabled = true;
    toggleAnimation(false);
}
