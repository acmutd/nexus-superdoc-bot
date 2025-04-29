# Use Ubuntu as the base image
FROM ubuntu:22.04

# Update package lists and install dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    wget \
    curl \
    gnupg2 \
    systemd \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS version from NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs

# Install Redis
RUN apt-get update && \
    apt-get install -y redis-server && \
    rm -rf /var/lib/apt/lists/*

# Configure Redis to run in the foreground (required for Docker)
RUN sed -i 's/supervised no/supervised systemd/g' /etc/redis/redis.conf && \
    sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf

# Expose Redis default port
EXPOSE 6379

# Start Redis when the container launches
CMD ["redis-server", "--bind", "0.0.0.0"]