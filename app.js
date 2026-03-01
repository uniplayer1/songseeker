import QrScanner from "https://unpkg.com/qr-scanner/qr-scanner.min.js";

let player; 
let playbackTimer; 
let playbackDuration = 30; 
let qrScanner;
let csvCache = {};
let lastDecodedText = ""; 
let currentStartTime = 0;
let currentPlayerType = 'youtube'; 

function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

document.addEventListener('DOMContentLoaded', function () {
    const video = document.getElementById('qr-video');

    if (isIOS()) {
        var autoplayCheckbox = document.getElementById('autoplay');
        autoplayCheckbox.checked = false;
        // We will no longer disable the checkbox, giving users the option to try!
    }

    qrScanner = new QrScanner(video, result => {
        console.log('decoded qr code:', result);
        if (result.data !== lastDecodedText) {
            lastDecodedText = result.data; 
            handleScannedLink(result.data);
        }
    }, { 
        highlightScanRegion: true,
        highlightCodeOutline: true,
    });
});

async function handleScannedLink(decodedText) {
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
                const youtubeLink = lookupYoutubeLink(hitsterData.id, csvContent);
                if (youtubeLink) {
                    youtubeURL = youtubeLink;
                }
            } catch (error) {
              console.error("Failed to fetch CSV:", error);
            }
        }
    } else if (isRockster(decodedText)){
        try {
            const urlObj = new URL(decodedText); 
            const ytCode = urlObj.searchParams.get("yt"); 
            if (ytCode) {
                youtubeURL = `https://www.youtube.com/watch?v=${ytCode}`;
            }
        } catch (error) {}
    }

    const youtubeLinkData = parseYoutubeLink(youtubeURL);
    if (youtubeLinkData) {
        qrScanner.stop(); 
        document.getElementById('qr-reader').style.display = 'none'; 
        document.getElementById('cancelScanButton').style.display = 'none'; 
        document.getElementById('startScanButton').style.display = 'block'; // Show Start button again
        lastDecodedText = ""; 

        document.getElementById('video-id').textContent = youtubeLinkData.videoId;  
        currentStartTime = youtubeLinkData.startTime || 0;
        
        // Pause any local audio that might be playing!
        const localPlayer = document.getElementById('local-player');
        localPlayer.pause();
        clearTimeout(playbackTimer);
        toggleAnimation(false);

        player.cueVideoById(youtubeLinkData.videoId, currentStartTime);   
    }
}

function isHitsterLink(url) {
    const regex = /^(?:http:\/\/|https:\/\/)?(www\.hitstergame|app\.hitsternordics)\.com\/.+/;
    return regex.test(url);
}

function isYoutubeLink(url) {
    return url.startsWith("https://www.youtube.com") || url.startsWith("https://youtu.be") || url.startsWith("https://music.youtube.com/");
}

function isRockster(url){
    return url.startsWith("https://rockster.brettspiel.digital")
}

function parseHitsterUrl(url) {
    const regex = /^(?:http:\/\/|https:\/\/)?www\.hitstergame\.com\/(.+?)\/(\d+)$/;
    const match = url.match(regex);
    if (match) {
        const processedLang = match.replace(/\//g, "-");
        return { lang: processedLang, id: match };
    }
    const regex_nordics = /^(?:http:\/\/|https:\/\/)?app.hitster(nordics).com\/resources\/songs\/(\d+)$/;
    const match_nordics = url.match(regex_nordics);
    if (match_nordics) {
        return { lang: match_nordics, id: match_nordics };
    }
    return null;
}

function lookupYoutubeLink(id, csvContent) {
    const headers = csvContent; 
    const cardIndex = headers.indexOf('Card#');
    const urlIndex = headers.indexOf('URL');
    const targetId = parseInt(id, 10); 
    const lines = csvContent.slice(1); 

    if (cardIndex === -1 || urlIndex === -1) return null;

    for (let row of lines) {
        if (parseInt(row[cardIndex], 10) === targetId) {
            return row[urlIndex].trim(); 
        }
    }
    return null; 
}

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
        result.push(line.substring(startValueIdx).trim().replace(/^"(.*)"$/, '$1')); 
        return result;
    });
}

async function getCachedCsv(url) {
    if (!csvCache[url]) { 
        const response = await fetch(url);
        const data = await response.text();
        csvCache[url] = parseCSV(data); 
    }
    return csvCache[url]; 
}

function parseYoutubeLink(url) {
    url = decodeURIComponent(url);
    const regex = /^https?:\/\/(www\.youtube\.com\/watch\?v=|youtu\.be\/|music\.youtube\.com\/watch\?v=)(.{11})(.*)/;
    const match = url.match(regex);
    if (match) {
        const queryParams = new URLSearchParams(match); 
        const videoId = match;
        let startTime = queryParams.get('start') || queryParams.get('t');
        const endTime = queryParams.get('end');

        document.getElementById('video-start').textContent = startTime;
        startTime = normalizeTimeParameter(startTime);
        const parsedEndTime = normalizeTimeParameter(endTime);

        return { videoId, startTime, endTime: parsedEndTime };
    }
    return null;
}

function normalizeTimeParameter(timeValue) {
    if (!timeValue) return null; 
    let seconds = 0;
    if (timeValue.endsWith('s')) {
        seconds = parseInt(timeValue, 10);
    } else {
        seconds = parseInt(timeValue, 10);
    }
    return isNaN(seconds) ? null : seconds;
}

// --- NEW LOCAL AUDIO LOGIC ---
function playLocalAudio(url) {
    qrScanner.stop(); 
    document.getElementById('qr-reader').style.display = 'none'; 
    document.getElementById('cancelScanButton').style.display = 'none'; 
    document.getElementById('startScanButton').style.display = 'block'; // Show Start button again
    lastDecodedText = ""; 
    currentPlayerType = 'local'; 

    const localPlayer = document.getElementById('local-player');
    
    // FIX: Pause any currently playing audio and clear timers before loading a new one
    localPlayer.pause();
    clearTimeout(playbackTimer);
    toggleAnimation(false);

    // Pause YouTube player if active
    if (player && typeof player.pauseVideo === 'function') {
        player.pauseVideo();
    }

    localPlayer.src = url;
    
    document.getElementById('video-id').textContent = "Local File";
    document.getElementById('video-title').textContent = url.substring(url.lastIndexOf('/') + 1);
    document.getElementById('startstop-video').style.background = "var(--accent-wait)"; 

    localPlayer.onloadedmetadata = function() {
        document.getElementById('video-duration').textContent = formatDuration(localPlayer.duration);
        document.getElementById('startstop-video').style.background = "var(--accent-play)"; 
        
        if (document.getElementById('autoplay').checked == true) {
            document.getElementById('startstop-video').innerHTML = "Stop";
            document.getElementById('startstop-video').style.background = "var(--accent-stop)";
            
            if (document.getElementById('randomplayback').checked == true) {
                playLocalAtRandomStartTime();
            } else {
                localPlayer.play().then(() => {
                    toggleAnimation(true);
                }).catch(error => {
                    console.error("Autoplay blocked. User tap required:", error);
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
        toggleAnimation(false);
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
        startTime = minStartTime + (Math.random() * range);
        endTime = startTime + playbackDuration;
    }

    localPlayer.currentTime = startTime;
    localPlayer.play().then(() => {
        toggleAnimation(true);
    }).catch(e => {
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
        toggleAnimation(false);
    });

    clearTimeout(playbackTimer); 
    playbackTimer = setTimeout(() => {
        localPlayer.pause();
        document.getElementById('startstop-video').innerHTML = "Play";
        // FIX: Removed the buggy 'green' color
        document.getElementById('startstop-video').style.background = "var(--accent-play)"; 
        toggleAnimation(false);
    }, (endTime - startTime) * 1000); 
}

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

const tag = document.createElement('script');
tag.src = "https://www.youtube.com/iframe_api";
const firstScriptTag = document.getElementsByTagName('script');
firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

function onPlayerReady(event) {
    event.target.setVolume(100);
    event.target.unMute();
}

function onPlayerStateChange(event) {
    if (event.data == YT.PlayerState.CUED) {
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
        var videoData = player.getVideoData();
        document.getElementById('video-title').textContent = videoData.title;
        var duration = player.getDuration();
        document.getElementById('video-duration').textContent = formatDuration(duration);
        
        if (document.getElementById('autoplay').checked == true) {
            document.getElementById('startstop-video').innerHTML = "Stop";
            if (document.getElementById('randomplayback').checked == true) {
                playVideoAtRandomStartTime();
            } else {
                player.playVideo();
            }
        }
    } else if (event.data == YT.PlayerState.PLAYING) {
        document.getElementById('startstop-video').style.background = "var(--accent-stop)";
    } else if (event.data == YT.PlayerState.PAUSED || event.data == YT.PlayerState.ENDED) {
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
    } else if (event.data == YT.PlayerState.BUFFERING) {
        document.getElementById('startstop-video').style.background = "var(--accent-wait)";
    }
}

function formatDuration(duration) {
    var minutes = Math.floor(duration / 60);
    var seconds = Math.floor(duration % 60);
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
}

document.getElementById('startstop-video').addEventListener('click', function() {
    const localPlayer = document.getElementById('local-player');

    if (this.innerHTML == "Play") {
        this.innerHTML = "Stop";
        this.style.background = "var(--accent-stop)"; 
        toggleAnimation(true); 

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
        this.style.background = "var(--accent-play)"; 
        toggleAnimation(false); 

        if (currentPlayerType === 'local') {
            localPlayer.pause();
            clearTimeout(playbackTimer); 
        } else {
            player.pauseVideo();
            clearTimeout(playbackTimer); 
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

    const minStartTime = Math.max(currentStartTime, videoDuration * minStartPercentage);
    const maxEndTime = videoDuration * maxEndPercentage;

    if (endTime > maxEndTime) {
        endTime = maxEndTime;
        startTime = Math.max(minStartTime, endTime - playbackDuration);
    }

    if (startTime <= minStartTime) {
        const range = maxEndTime - minStartTime - playbackDuration;
        startTime = minStartTime + (Math.random() * range);
        endTime = startTime + playbackDuration;
    }

    player.seekTo(startTime, true);
    player.playVideo();

    clearTimeout(playbackTimer); 
    playbackTimer = setTimeout(() => {
        player.pauseVideo();
        document.getElementById('startstop-video').innerHTML = "Play";
        document.getElementById('startstop-video').style.background = "var(--accent-play)";
    }, (endTime - startTime) * 1000); 
}

document.getElementById('startScanButton').addEventListener('click', function() {
    // FIX: Hide Start button, Show Cancel button
    this.style.display = 'none';
    document.getElementById('cancelScanButton').style.display = 'block';
    
    // We use display: flex instead of block so the square aspect ratio stays intact
    document.getElementById('qr-reader').style.display = 'flex'; 

    qrScanner.start().catch(err => {
        console.error('Unable to start QR Scanner', err);
        // If it fails, revert the buttons
        document.getElementById('cancelScanButton').style.display = 'none';
        this.style.display = 'block';
        document.getElementById('qr-reader').style.display = 'none';
    });

    qrScanner.start().then(() => {
        qrScanner.setInversionMode('both'); 
    });
});

document.getElementById('cancelScanButton').addEventListener('click', function() {
    qrScanner.stop(); 
    document.getElementById('qr-reader').style.display = 'none'; 
    this.style.display = 'none'; // Hide cancel
    document.getElementById('startScanButton').style.display = 'block'; // Show start
});

document.getElementById('cb_settings').addEventListener('click', function() {
    var cb = document.getElementById('cb_settings');
    if (cb.checked == true) {
        document.getElementById('settings_div').style.display = 'block';
    } else {
        document.getElementById('settings_div').style.display = 'none';
    }
});

document.getElementById('randomplayback').addEventListener('click', function() {
    document.cookie = "RandomPlaybackChecked=" + this.checked + ";max-age=2592000"; 
    listCookies();
});

document.getElementById('autoplay').addEventListener('click', function() {
    document.cookie = "autoplayChecked=" + this.checked + ";max-age=2592000"; 
    listCookies();
});

document.getElementById('cookies').addEventListener('click', function() {
    var cb = document.getElementById('cookies');
    if (cb.checked == true) {
        document.getElementById('cookielist').style.display = 'block';
    } else {
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
        return match;
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

document.getElementById('debugButton').addEventListener('click', function() {
    handleScannedLink("https://www.hitstergame.com/de-aaaa0012/237");
});

document.getElementById('songinfo').addEventListener('click', function() {
    var cb = document.getElementById('songinfo');
    var videoid = document.getElementById('videoid');
    var videotitle = document.getElementById('videotitle');
    var videoduration = document.getElementById('videoduration');
    var videostart = document.getElementById('videostart');
    if(cb.checked == true){
        videoid.style.display = 'block';
        videotitle.style.display = 'block';
        videoduration.style.display = 'block';
        videostart.style.display = 'block';
    } else {
        videoid.style.display = 'none';
        videotitle.style.display = 'none';
        videoduration.style.display = 'none';
        videostart.style.display = 'none';
    }
});

window.addEventListener("DOMContentLoaded", getCookies());