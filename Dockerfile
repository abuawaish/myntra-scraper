# Use Python 3.9 with full Debian packages
FROM python:3.9-bullseye

# Install system dependencies with man page support
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    man-db \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxtst6 \
    xdg-utils \
    --no-install-recommends

# Install Chrome stable version
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable=114.0.5735.198-1

# Install matching ChromeDriver
RUN CHROME_DRIVER_VERSION=114.0.5735.90 \
    && wget -q https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip

# Configure Python environment
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Set production environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PORT 10000

EXPOSE $PORT

# Clean up package lists to reduce image size
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:$PORT/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "3", "app:app"]