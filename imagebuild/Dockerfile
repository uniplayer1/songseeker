FROM nginx:latest

# Copy custom Nginx configuration
COPY imagebuild/default.conf /etc/nginx/conf.d/default.conf

# Clear default Nginx web root
RUN rm -rf /usr/share/nginx/html/*

# Copy SongSeeker web app files (local-audio edition; no legacy CSVs or unused root assets)
COPY index.html app.js style.css manifest.json /usr/share/nginx/html/
# Icons must land flat in root to match <link href="icon-*.png"> references
COPY icons/icon-*.png icons/favicon.ico icons/icon.webp /usr/share/nginx/html/

# Create the playlists directory
RUN mkdir -m 755 -p /usr/share/nginx/html/playlists

# Create the music directory with public read permissions
RUN mkdir -m 755 -p /usr/share/nginx/html/music