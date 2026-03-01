import QrScanner from "https://unpkg.com/qr-scanner/qr-scanner.min.js";

let player; // Define player globally
let playbackTimer; // hold the timer reference
let playbackDuration = 30; // Default playback duration
let qrScanner;
let csvCache = {};
let lastDecodedText = ""; // Store the last decoded text
let currentStartTime = 0;
let currentPlayerType = 'youtube'; // Track which player is active

// Function to detect iOS devices
function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

document.addEventListener('DOMContentLoaded', function () {

    const video = document.getElementById('qr-video');
    const resultContainer = document.getElementById("qr-reader-results");

    // If the user is on an iOS device, uncheck and disable the autoplay checkbox
    if (isIOS()) {
        var autoplayCheckbox = document.getElementById('autoplay');
        autoplayCheckbox.checked = false;
        autoplayCheckbox.disabled = true;
    }

    qrScanner = new QrScanner(video, result => {
        console.log('decoded qr code:', result);
        if (result.data !== lastDecodedText) {
            lastDecodedText = result.data; // Update the last decoded text
            handleScannedLink(result.data);
        }
    }, { 
        highlightScanRegion: true,
        highlightCodeOutline: true,
    }
    );
    
    // --- REPORT LOGIC ---
    document.getElementById('submitReport').addEventListener('click', async function() {
        const reason = document.getElementById('reportReason').value;
        const title = document.getElementById('video-title').textContent;
        const videoIdText = document.getElementById('video-id').textContent;
        
        // Figure out the actual playable URL based on the player type
        let resolvedUrl = "";
        if (currentPlayerType === 'local') {
            // For local files, grab the source from the audio element
            resolvedUrl = document.getElementById('local-player').src || lastDecodedText;
        } else {
            // For YouTube, reconstruct the full YouTube link
            resolvedUrl = videoIdText ? `https://www.youtube.com/watch?v=${videoIdText}` : lastDecodedText;
        }

        try {
            await fetch('/api/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    type: currentPlayerType,
                    title: title, 
                    reason: reason,
                    resolvedUrl: resolvedUrl,      // The actual MP3 path or YouTube link
                    originalScan: lastDecodedText  // What the QR code actually contained
                })
            });
            
            // Visual feedback
            const btn = document.getElementById('reportButton');
            btn.textContent = "Reported!";
            btn.style.borderColor = "var(--accent-play)";
            btn.style.color = "var(--accent-play)";
            setTimeout(() => {
                btn.textContent = "Report Song Issue";
                btn.style.borderColor = "var(--accent-wait)";
                btn.style.color = "var(--accent-wait)";
            }, 3000);

        } catch (error) {
            console.error('Report failed:', error);
            alert('Could not submit report. Check console.');
        }
        
        document.getElementById('reportModal').classList.add('hidden');
    });
    
    }
);

// Function to determine the type of link and act accordingly
async function handleScannedLink(decodedText) {
    if (decodedText.toLowerCase().endsWith('.mp3') || decodedText.toLowerCase().endsWith('.wav')) {
        playLocalAudio(decodedText);
        return; // Exit the function early so YouTube logic doesn't run
    }

    let youtubeURL = "";
    currentPlayerType = 'youtube';
    if (isYoutubeLink(decodedText)) {
        youtubeURL = decodedText;
    } else if (isHitsterLink(decodedText)) {
        const hitsterData = parseHitsterUrl(decodedText);
        if (hitsterData) {
            console.log("Hitster data:", hitsterData.id, hitsterData.lang);
            try {
                const csvContent = await getCachedCsv(`/playlists/hitster-${hitsterData.lang}.csv`);
                const youtubeLink = lookupYoutubeLink(hitsterData.id, csvContent);
                if (youtubeLink) {
                    // Handle YouTube link obtained from the CSV
                    console.log(`YouTube Link from CSV: ${youtubeLink}`);
                    youtubeURL = youtubeLink;
                    // Example: player.cueVideoById(parseYoutubeLink(youtubeLink).videoId);
                }
            } catch (error) {
              console.error("Failed to fetch CSV:", error);
            }
        }
        else {
            console.log("Invalid Hitster URL:", decodedText);
        }
    } else if (isRockster(decodedText)){
        try {
            const urlObj = new URL(decodedText); // Create URL object
            const ytCode = urlObj.searchParams.get("yt"); // Extract 'yt' parameter
    
            if (ytCode) {
                youtubeURL = `https://www.youtube.com/watch?v=${ytCode}`;
            } else {
                console.error("Rockster link is missing the 'yt' parameter:", decodedText);
            }
        } catch (error) {
            console.error("Invalid Rockster URL:", decodedText);
        }
    }

    console.log(`YouTube Video URL: ${youtubeURL}`);

    const youtubeLinkData = parseYoutubeLink(youtubeURL);
    if (youtubeLinkData) {
        qrScanner.stop(); // Stop scanning after a result is found
        document.getElementById('qr-reader').style.display = 'none'; // Hide the scanner after successful scan
        document.getElementById('cancelScanButton').style.display = 'none'; // Hide the cancel-button
        document.getElementById('startScanButton').style.display = 'block';
        document.getElementById('reportButton').style.display = 'block';
        lastDecodedText = ""; // Reset the last decoded text

        document.getElementById('video-id').textContent = youtubeLinkData.videoId;  

        console.log(youtubeLinkData.videoId);
        currentStartTime = youtubeLinkData.startTime || 0;
        player.cueVideoById(youtubeLinkData.videoId, currentStartTime);   
        
    }
    
}

    function isHitsterLink(url) {
        // Regular expression to match with or without "http://" or "https://"
        const regex = /^(?:http:\/\/|https:\/\/)?(www\.hitstergame|app\.hitsternordics)\.com\/.+/;
        return regex.test(url);
    }

    // Example implementation for isYoutubeLink
    function isYoutubeLink(url) {
        return url.startsWith("https://www.youtube.com") || url.startsWith("https://youtu.be") || url.startsWith("https://music.youtube.com/");
    }
    function isRockster(url){
        return url.startsWith("https://rockster.brettspiel.digital")
    }
    // Example implementation for parseHitsterUrl
    function parseHitsterUrl(url) {
        const regex = /^(?:http:\/\/|https:\/\/)?www\.hitstergame\.com\/(.+?)\/(\d+)$/;
        const match = url.match(regex);
        if (match) {
            // Hitster URL is in the format: https://www.hitstergame.com/{lang}/{id}
            // lang can be things like "en", "de", "pt", etc., but also "de/aaaa0007"
            const processedLang = match[1].replace(/\//g, "-");
            return { lang: processedLang, id: match[2] };
        }
        const regex_nordics = /^(?:http:\/\/|https:\/\/)?app.hitster(nordics).com\/resources\/songs\/(\d+)$/;
        const match_nordics = url.match(regex_nordics);
        if (match_nordics) {
            // Hitster URL can also be in the format: https://app.hitsternordics.com/resources/songs/{id}
            return { lang: match_nordics[1], id: match_nordics[2] };
        }
        return null;
    }

    // Looks up the YouTube link in the CSV content based on the ID
    function lookupYoutubeLink(id, csvContent) {
        const headers = csvContent[0]; // Get the headers from the CSV content
        const cardIndex = headers.indexOf('Card#');
        const urlIndex = headers.indexOf('URL');

        const targetId = parseInt(id, 10); // Convert the incoming ID to an integer
        const lines = csvContent.slice(1); // Exclude the first row (headers) from the lines

        if (cardIndex === -1 || urlIndex === -1) {
            throw new Error('Card# or URL column not found');
        }

        for (let row of lines) {
            const csvId = parseInt(row[cardIndex], 10);
            if (csvId === targetId) {
                return row[urlIndex].trim(); // Return the YouTube link
            }
        }
        return null; // If no matching ID is found

    }

    // Could also use external library, but for simplicity, we'll define it here
    function parseCSV(text) {
        const lines = text.split('\n');
        return lines.map(line => {
            const result = [];
            let startValueIdx = 0;
            let inQuotes = false;
            for (let i = 0; i < line.length; i++) {
                if (line[i] === '"' && line[i-1] !== '\\') {
                    inQuotes = !inQuotes;
                } else if (line[i] === ',' && !inQuotes) {
                    result.push(line.substring(startValueIdx, i).trim().replace(/^"(.*)"$/, '$1'));
                    startValueIdx = i + 1;
                }
            }
            result.push(line.substring(startValueIdx).trim().replace(/^"(.*)"$/, '$1')); // Push the last value
            return result;
        });
    }

    async function getCachedCsv(url) {
        if (!csvCache[url]) { // Check if the URL is not in the cache
            console.log(`URL not cached, fetching CSV from URL: ${url}`);
            const response = await fetch(url);
            const data = await response.text();
            csvCache[url] = parseCSV(data); // Cache the parsed CSV data using the URL as a key
        }
        return csvCache[url]; // Return the cached data for the URL
    }

    function parseYoutubeLink(url) {
        // First, ensure that the URL is decoded (handles encoded URLs)
        url = decodeURIComponent(url);
    
        const regex = /^https?:\/\/(www\.youtube\.com\/watch\?v=|youtu\.be\/|music\.youtube\.com\/watch\?v=)(.{11})(.*)/;
        const match = url.match(regex);
        if (match) {
            const queryParams = new URLSearchParams(match[3]); // Correctly capture and parse the query string part of the URL
            const videoId = match[2];
            let startTime = queryParams.get('start') || queryParams.get('t');
            const endTime = queryParams.get('end');

            // Normalize and parse 't' and 'start' parameters
            startTime = normalizeTimeParameter(startTime);
            const parsedEndTime = normalizeTimeParameter(endTime);
    
            return { videoId, startTime, endTime: parsedEndTime };
        }
        return null;
    }
    
    function normalizeTimeParameter(timeValue) {
        if (!timeValue) return null; // Return null if timeValue is falsy
    
        // Handle time formats (e.g., 't=1m15s' or '75s')
        let seconds = 0;
        if (timeValue.endsWith('s')) {
            seconds = parseInt(timeValue, 10);
        } else {
            // Additional parsing can be added here for 'm', 'h' formats if needed
            seconds = parseInt(timeValue, 10);
        }
    
        return isNaN(seconds) ? null : seconds;
    }

// --- NEW LOCAL AUDIO LOGIC ---
function playLocalAudio(url) {
    qrScanner.stop(); 
    document.getElementById('qr-reader').style.display = 'none'; 
    document.getElementById('cancelScanButton').style.display = 'none';
    document.getElementById('startScanButton').style.display = 'block';
    document.getElementById('reportButton').style.display = 'block';
    lastDecodedText = ""; 
    currentPlayerType = 'local'; // Switch context to local player

    const localPlayer = document.getElementById('local-player');
    localPlayer.src = url;
    
    const fallbackTitle = url.substring(url.lastIndexOf('/') + 1);
    
    // UI vorab aktualisieren
    document.getElementById('video-id').textContent = "Local File";
    document.getElementById('video-title').textContent = "Lade... (" + fallbackTitle + ")";
    document.getElementById('video-year').textContent = "Lade...";

    // MP3 Metadaten (ID3-Tags) auslesen
    if (window.jsmediatags) {
        window.jsmediatags.read(url, {
            onSuccess: function(tag) {
                const tags = tag.tags;
                // Wenn im MP3-Tag ein Titel steht, nimm den. Sonst Fallback auf Dateinamen.
                document.getElementById('video-title').textContent = tags.title ? tags.title : fallbackTitle;
                // Wenn ein Jahr im Tag steht, nimm das. Sonst "Unbekannt".
                document.getElementById('video-year').textContent = tags.year ? tags.year : "Unbekannt";
            },
            onError: function(error) {
                console.warn('Keine Metadaten gefunden, nutze Dateinamen.', error);
                document.getElementById('video-title').textContent = fallbackTitle;
                document.getElementById('video-year').textContent = "Unbekannt";
            }
        });
    } else {
        document.getElementById('video-title').textContent = fallbackTitle;
        document.getElementById('video-year').textContent = "Unbekannt";
    }

    localPlayer.onloadedmetadata = function() {
        document.getElementById('video-duration').textContent = formatDuration(localPlayer.duration);
        document.getElementById('startstop-video').style.background = "var(--accent-play)"; 
        
        // Let's force autoplay regardless of the device!
        if (document.getElementById('autoplay').checked == true) {
            document.getElementById('startstop-video').innerHTML = "Stop";
            document.getElementById('startstop-video').style.background = "var(--accent-stop)";
            
            if (document.getElementById('randomplayback').checked == true) {
                playLocalAtRandomStartTime();
            } else {
                localPlayer.play().then(() => {
                    toggleAnimation(true);
                }).catch(error => {
                    // If the browser STILL blocks it, safely revert the button
                    console.error("Autoplay was blocked by the browser:", error);
                    document.getElementById('startstop-video').innerHTML = "Play";
                    document.getElementById('startstop-video').style.background = "var(--accent-play)";
                    toggleAnimation(false);
                });
            }
        }
    };

    localPlayer.onended = function() {
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
        toggleAnimation(false); // Add this
    };
}

function playLocalAtRandomStartTime() {
    const localPlayer = document.getElementById('local-player');
    const minStartPercentage = 0.10;
    const maxEndPercentage = 0.90;
    let videoDuration = localPlayer.duration;
    playbackDuration = parseInt(document.getElementById('playback-duration').value, 10) || 30;
    
    let startTime = 0;
    let endTime = playbackDuration;

    const minStartTime = videoDuration * minStartPercentage;
    const maxEndTime = videoDuration * maxEndPercentage;

    if (endTime > maxEndTime) {
        endTime = maxEndTime;
        startTime = Math.max(minStartTime, endTime - playbackDuration);
    }

    if (startTime <= minStartTime) {
        const range = maxEndTime - minStartTime - playbackDuration;
        const randomOffset = Math.random() * range;
        startTime = minStartTime + randomOffset;
        endTime = startTime + playbackDuration;
    }

    localPlayer.currentTime = startTime;
    // NEU: play() mit Fehlerbehandlung (Catch-Block)
    localPlayer.play().then(() => {
        // Erst wenn es WIRKLICH spielt, Animation starten
        toggleAnimation(true);

        clearTimeout(playbackTimer); 
        playbackTimer = setTimeout(() => {
            localPlayer.pause();
            document.getElementById('startstop-video').innerHTML = "Play";
            document.getElementById('startstop-video').style.background = "var(--accent-play)"; // Direkt deine CSS-Variable genutzt
            toggleAnimation(false);
        }, (endTime - startTime) * 1000); 

    }).catch(error => {
        // Falls der Browser es doch blockiert: UI sauber zurücksetzen!
        console.error("Autoplay wurde vom Browser blockiert:", error);
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
        toggleAnimation(false);
    });
}
// --- END NEW LOCAL AUDIO LOGIC ---

// This function creates an <iframe> (and YouTube player) after the API code downloads.
function onYouTubeIframeAPIReady() {
    player = new YT.Player('player', {
        height: '0',
        width: '0',
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}
window.onYouTubeIframeAPIReady = onYouTubeIframeAPIReady;

// Load the YouTube IFrame API script
const tag = document.createElement('script');
tag.src = "https://www.youtube.com/iframe_api";
const firstScriptTag = document.getElementsByTagName('script')[0];
firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

// The API will call this function when the video player is ready.
function onPlayerReady(event) {
    // Cue a video using the videoId from the QR code (example videoId used here)
    // player.cueVideoById('dQw4w9WgXcQ');
    event.target.setVolume(100);
    event.target.unMute();
}

// Display video information when it's cued
function onPlayerStateChange(event) {
    if (event.data == YT.PlayerState.CUED) {
        document.getElementById('startstop-video').style.background = "green";
        // Display title and duration
        var videoData = player.getVideoData();
        document.getElementById('video-title').textContent = videoData.title;
        var duration = player.getDuration();
        document.getElementById('video-duration').textContent = formatDuration(duration);
        document.getElementById('video-year').textContent = "Unbekannt (YouTube API)";
        // We do need this on iOS devices otherwise one would need to press play twice
        if (isIOS()) {
            player.playVideo();
        }
        // Check for Autoplay, there is not autoplay on iOS
        else if (document.getElementById('autoplay').checked == true) {
            document.getElementById('startstop-video').innerHTML = "Stop";
            if (document.getElementById('randomplayback').checked == true) {
                playVideoAtRandomStartTime();
            }
            else {
                player.playVideo();
            }
        }
    }
    else if (event.data == YT.PlayerState.PLAYING) {
        document.getElementById('startstop-video').style.background = "red";
    }
    else if (event.data == YT.PlayerState.PAUSED || event.data == YT.PlayerState.ENDED) {
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "green";
    }
    else if (event.data == YT.PlayerState.BUFFERING) {
        document.getElementById('startstop-video').style.background = "orange";
    }
}

// Helper function to format duration from seconds to a more readable format
function formatDuration(duration) {
    var minutes = Math.floor(duration / 60);
    var seconds = Math.floor(duration % 60); // <-- Hier ist das Math.floor() neu!
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
}

// Add event listeners to Play and Stop buttons
document.getElementById('startstop-video').addEventListener('click', function() {
    const localPlayer = document.getElementById('local-player');

    if (this.innerHTML == "Play") {
        this.innerHTML = "Stop";
        this.style.background = "var(--accent-stop)"; // Updated to use the CSS variable
        toggleAnimation(true); // Trigger animation!

        if (document.getElementById('randomplayback').checked == true) {
            if (currentPlayerType === 'local') {
                playLocalAtRandomStartTime();
            } else {
                playVideoAtRandomStartTime();
            }
        } else {
            if (currentPlayerType === 'local') {
                localPlayer.play();
            } else {
                player.playVideo();
            }
        }
    } else {
        this.innerHTML = "Play";
        this.style.background = "var(--accent-play)"; // Updated to use the CSS variable
        toggleAnimation(false); // Stop animation!

        if (currentPlayerType === 'local') {
            localPlayer.pause();
            clearTimeout(playbackTimer); // Stop the random playback timer if active
        } else {
            player.pauseVideo();
            clearTimeout(playbackTimer); // Stop the random playback timer if active
        }
    }
});

function playVideoAtRandomStartTime() {
    const minStartPercentage = 0.10;
    const maxEndPercentage = 0.90;
    let videoDuration = player.getDuration()
    playbackDuration = parseInt(document.getElementById('playback-duration').value, 10) || 30;
    let startTime = currentStartTime;
    let endTime = playbackDuration;

    // Adjust start and end time based on video duration
    const minStartTime = Math.max(currentStartTime, videoDuration * minStartPercentage);
    const maxEndTime = videoDuration * maxEndPercentage;

    // Ensure the video ends by 90% of its total duration
    if (endTime > maxEndTime) {
        endTime = maxEndTime;
        startTime = Math.max(minStartTime, endTime - playbackDuration);
    }

    // If custom start time is 0 or very close to the beginning, pick a random start time within the range
    if (startTime <= minStartTime) {
        const range = maxEndTime - minStartTime - playbackDuration;
        const randomOffset = Math.random() * range;
        startTime = minStartTime + randomOffset;
        endTime = startTime + playbackDuration;
    }

    // Cue video at calculated start time and play
    console.log("play random", startTime, endTime)
    player.seekTo(startTime, true);
    player.playVideo();

    clearTimeout(playbackTimer); // Clear any existing timer
    // Schedule video stop after the specified duration
    playbackTimer = setTimeout(() => {
        player.pauseVideo();
        document.getElementById('startstop-video').innerHTML = "Play";
    }, (endTime - startTime) * 1000); // Convert to milliseconds
}

// Assuming you have an element with the ID 'qr-reader' for the QR scanner
document.getElementById('qr-reader').style.display = 'none'; // Initially hide the QR Scanner

document.getElementById('startScanButton').addEventListener('click', function() {
    const localPlayer = document.getElementById('local-player');
    
    // NEU 1: Wir löschen das Event, damit der Dummy-Sound nicht das Autoplay auslöst!
    localPlayer.onloadedmetadata = null;
    
    // NEU 2: Falls der Random-Timer noch läuft, stoppen wir ihn
    clearTimeout(playbackTimer);

    // --- DER KUGELSICHERE AUDIO-UNLOCK TRICK ---
    localPlayer.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
    localPlayer.play().then(() => {
        localPlayer.pause();
    }).catch(() => {});
    // -------------------------------------------
    
    if (typeof player !== 'undefined' && player && player.pauseVideo) {
        player.pauseVideo();
    }

    // UI zuverlässig zurücksetzen (Equalizer stoppen und auf Play stellen)
    document.getElementById('startstop-video').innerHTML = "Play";
    document.getElementById('startstop-video').style.background = "var(--accent-play)";
    toggleAnimation(false);

    // Buttons austauschen und Scanner anzeigen
    this.style.display = 'none';
    document.getElementById('cancelScanButton').style.display = 'block';
    document.getElementById('qr-reader').style.display = 'block'; 
    
    qrScanner.start().catch(err => {
        console.error('Unable to start QR Scanner', err);
        document.getElementById('startScanButton').style.display = 'block';
    });

    qrScanner.start().then(() => {
        qrScanner.setInversionMode('both'); 
    });
});

document.getElementById('debugButton').addEventListener('click', function() {
    handleScannedLink("https://www.hitstergame.com/de-aaaa0012/237");
    // handleScannedLink("https://rockster.brettspiel.digital/?yt=1bP-fFxAMOI");
});

document.getElementById('songinfo').addEventListener('click', function() {
    var cb = document.getElementById('songinfo');
    var videoid = document.getElementById('videoid');
    var videotitle = document.getElementById('videotitle');
    var videoduration = document.getElementById('videoduration');
    var videoyear = document.getElementById('videoyear'); // Jetzt das Jahr
    if(cb.checked == true){
        videoid.style.display = 'block';
        videotitle.style.display = 'block';
        videoduration.style.display = 'block';
        videoyear.style.display = 'block';
    } else {
        videoid.style.display = 'none';
        videotitle.style.display = 'none';
        videoduration.style.display = 'none';
        videoyear.style.display = 'none';
    }
});

document.getElementById('cancelScanButton').addEventListener('click', function() {
    qrScanner.stop(); // Stop scanning after a result is found
    document.getElementById('qr-reader').style.display = 'none'; // Hide the scanner after successful scan
    document.getElementById('cancelScanButton').style.display = 'none'; // Hide the cancel-button
    document.getElementById('startScanButton').style.display = 'block';
});

document.getElementById('cb_settings').addEventListener('click', function() {
    var cb = document.getElementById('cb_settings');
    if (cb.checked == true) {
        document.getElementById('settings_div').style.display = 'block';
    }
    else {
        document.getElementById('settings_div').style.display = 'none';
    }
});

document.getElementById('randomplayback').addEventListener('click', function() {
    document.cookie = "RandomPlaybackChecked=" + this.checked + ";max-age=2592000"; //30 Tage
    listCookies();
});

document.getElementById('autoplay').addEventListener('click', function() {
    document.cookie = "autoplayChecked=" + this.checked + ";max-age=2592000"; //30 Tage
    listCookies();
});

document.getElementById('cookies').addEventListener('click', function() {
    var cb = document.getElementById('cookies');
    if (cb.checked == true) {
        document.getElementById('cookielist').style.display = 'block';
    }
    else {
        document.getElementById('cookielist').style.display = 'none';
    }
});

function listCookies() {
    var result = document.cookie;
    document.getElementById("cookielist").innerHTML=result;
 }

function getCookieValue(name) {
    const regex = new RegExp(`(^| )${name}=([^;]+)`);
    const match = document.cookie.match(regex);
    if (match) {
        return match[2];
    }
}

function getCookies() {
    var isTrueSet;
    if (getCookieValue("RandomPlaybackChecked") != "") {
        isTrueSet = (getCookieValue("RandomPlaybackChecked") === 'true');
        document.getElementById('randomplayback').checked = isTrueSet;
    }
    if (getCookieValue("autoplayChecked") != "") {
        isTrueSet = (getCookieValue("autoplayChecked") === 'true');
        document.getElementById('autoplay').checked = isTrueSet;  
    }
    listCookies();
}

// --- ANIMATION HELPER ---
function toggleAnimation(isPlaying) {
    const eq = document.getElementById('equalizer');
    if (eq) {
        if (isPlaying) {
            eq.classList.add('playing');
        } else {
            eq.classList.remove('playing');
        }
    }
}

window.addEventListener("DOMContentLoaded", getCookies());