const http = require('http');
const fs = require('fs').promises;
const path = require('path');

const logFile = path.join(__dirname, 'reports.log');
const PORT = 3000;

const server = http.createServer(async (req, res) => {
    const { method, url } = req;

    // --- REPORT SUBMISSION (POST) ---
    if (method === 'POST' && (url === '/report' || url === '/api/report')) {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', async () => {
            try {
                const data = JSON.parse(body);
                const timestamp = new Date().toISOString();
                
                const logEntry = `[${timestamp}] [${(data.type || 'UNKNOWN').toUpperCase()}] REASON: ${data.reason}
   -> TITLE:   ${data.title}
   -> PLAYING: ${data.resolvedUrl}
   -> SCANNED: ${data.originalScan}
--------------------------------------------------\n`;
                
                await fs.appendFile(logFile, logEntry);
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'success' }));
            } catch (err) {
                console.error('Error processing report:', err);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Server error processing report' }));
            }
        });
    } 
    // --- REPORT RETRIEVAL (GET) ---
    else if (method === 'GET' && (url === '/reports' || url === '/api/reports')) {
        try {
            // Check if file exists first to avoid throwing error on initial load
            let data = '';
            try {
                data = await fs.readFile(logFile, 'utf8');
            } catch (readErr) {
                if (readErr.code === 'ENOENT') {
                    data = 'No reports found yet.';
                } else {
                    throw readErr;
                }
            }
            
            res.writeHead(200, { 'Content-Type': 'text/plain' });
            res.end(data);
        } catch (err) {
            console.error('Error reading reports:', err);
            res.writeHead(500);
            res.end('Unable to read reports');
        }
    } 
    // --- 404 NOT FOUND ---
    else {
        res.writeHead(404);
        res.end('Not Found');
    }
});

server.listen(PORT, () => console.log(`SongSeeker backend listening on port ${PORT}`));
