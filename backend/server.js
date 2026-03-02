const http = require('http');
const fs = require('fs');
const path = require('path');

const logFile = path.join(__dirname, 'reports.log');

const server = http.createServer((req, res) => {
    if (req.method === 'POST' && (req.url === '/report' || req.url === '/api/report')) {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                const timestamp = new Date().toISOString();
                
                // Formatted log entry with all the new info
                const logEntry = `[${timestamp}] [${data.type.toUpperCase()}] REASON: ${data.reason}
   -> TITLE:   ${data.title}
   -> PLAYING: ${data.resolvedUrl}
   -> SCANNED: ${data.originalScan}
--------------------------------------------------\n`;
                
                fs.appendFileSync(logFile, logEntry);
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'success' }));
            } catch (err) {
                res.writeHead(500);
                res.end(JSON.stringify({ error: 'Server error' }));
            }
        });
    } else if (req.method === 'GET' && (req.url === '/reports' || req.url === '/api/reports')) {
        // return the contents of the log file so admin can inspect reported songs
        try {
            const data = fs.readFileSync(logFile, { encoding: 'utf8' });
            res.writeHead(200, { 'Content-Type': 'text/plain' });
            res.end(data);
        } catch (err) {
            res.writeHead(500);
            res.end('Unable to read reports');
        }
    } else {
        res.writeHead(404);
        res.end();
    }
});

server.listen(3000, () => console.log('Logger listening on port 3000'));