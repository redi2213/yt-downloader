# Base image for redi2213/yt-downloader GitHub Actions workflow.
# Rebuilt daily by .github/workflows/rebuild-base-image.yml so yt-dlp
# always has the latest YouTube extraction fixes, while the main
# download workflow stays fast (no install step needed).

FROM python:3.11-slim

# Install ffmpeg + aria2 in one layer, clean apt lists to keep image small
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends ffmpeg aria2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Always install the latest yt-dlp at build time.
# Since this image is rebuilt daily, "latest" here effectively means
# "latest as of last night" — which is what you want for extraction fixes.
RUN pip install --no-cache-dir -U yt-dlp

# Deno is required for yt-dlp's --remote-components ejs:github flag,
# which solves YouTube's "n challenge" JS puzzle. Without this,
# yt-dlp can only see image/thumbnail formats, not video/audio.
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends curl unzip && \
    curl -fsSL https://deno.land/install.sh | sh -s -- -y && \
    ln -s /root/.deno/bin/deno /usr/local/bin/deno && \
    rm -rf /var/lib/apt/lists/*

# Sanity check that binaries are actually on PATH and working
RUN yt-dlp --version && ffmpeg -version && aria2c --version && deno --version

WORKDIR /workspace
