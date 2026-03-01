// backend/server.js
const http = require('http');
const fs = require('fs');
const path = require('path');

const logFile = path.join(__dirname, 'reports.log');

const server = http.createServer((req, res) => {
    // Only accept POST requests on /report
    if (req.method === 'POST' && req.url === '/report') {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                const timestamp = new Date().toISOString();
                const logEntry = `[${timestamp}] TYPE: ${data.type} | ID/URL: ${data.songId} | TITLE: ${data.title} | REASON: ${data.reason}\n`;
                
                // Append to our log file
                fs.appendFileSync(logFile, logEntry);
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'success' }));
            } catch (err) {
                res.writeHead(500);
                res.end(JSON.stringify({ error: 'Server error' }));
            }
        });
    } else {
        res.writeHead(404);
        res.end();
    }
});

server.listen(3000, () => console.log('Logger listening on port 3000'));