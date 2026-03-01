FROM nginx:latest

# Copy custom Nginx configuration
COPY imagebuild/default.conf /etc/nginx/conf.d/default.conf

# Clear default Nginx web root
RUN rm -rf /usr/share/nginx/html/*

# Copy your modified SongSeeker web files
COPY *.js *.json *.csv *.html *.css *.png icons/* /usr/share/nginx/html/

# Create the playlists directory
RUN mkdir -m 755 -p /usr/share/nginx/html/playlists

# Create the music directory with public read permissions
RUN mkdir -m 755 -p /usr/share/nginx/html/music