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
                
                const logData = {
                    id: Date.now().toString() + Math.floor(Math.random() * 1000).toString(),
                    timestamp,
                    type: (data.type || 'UNKNOWN').toUpperCase(),
                    reason: data.reason,
                    title: data.title,
                    resolvedUrl: data.resolvedUrl,
                    originalScan: data.originalScan
                };
                
                await fs.appendFile(logFile, JSON.stringify(logData) + '\n');
                
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
            let fileContent = '';
            try {
                fileContent = await fs.readFile(logFile, 'utf8');
            } catch (readErr) {
                if (readErr.code === 'ENOENT') {
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify([]));
                    return;
                } else {
                    throw readErr;
                }
            }
            
            const lines = fileContent.split('\n').filter(line => line.trim() !== '');
            const reports = lines.map(line => {
                try {
                    return JSON.parse(line);
                } catch (e) {
                    // Fallback for old format if necessary, or just ignore
                    return null;
                }
            }).filter(r => r !== null);
            
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(reports));
        } catch (err) {
            console.error('Error reading reports:', err);
            res.writeHead(500);
            res.end(JSON.stringify({ error: 'Unable to read reports' }));
        }
    } 
    // --- REPORT DELETION (DELETE) ---
    else if (method === 'DELETE' && (url === '/report' || url === '/api/report')) {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', async () => {
            try {
                const { id } = JSON.parse(body);
                if (!id) throw new Error('No ID provided');

                const fileContent = await fs.readFile(logFile, 'utf8');
                const lines = fileContent.split('\n').filter(line => line.trim() !== '');
                const updatedLines = lines.filter(line => {
                    try {
                        return JSON.parse(line).id !== id;
                    } catch (e) {
                        return true; // Keep lines that aren't JSON
                    }
                });

                await fs.writeFile(logFile, updatedLines.length > 0 ? updatedLines.join('\n') + '\n' : '');
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'success' }));
            } catch (err) {
                console.error('Error deleting report:', err);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Server error deleting report' }));
            }
        });
    }
    // --- 404 NOT FOUND ---
    else {
        res.writeHead(404);
        res.end('Not Found');
    }
});

server.listen(PORT, () => console.log(`SongSeeker backend listening on port ${PORT}`));
