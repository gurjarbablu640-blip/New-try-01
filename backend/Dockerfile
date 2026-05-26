FROM python:3.12-slim

WORKDIR /app

# ============================================================
# SYSTEM DEPENDENCIES
# ============================================================

RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    unzip \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcb1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# COPY REQUIREMENTS
# ============================================================

COPY requirements.txt .

# ============================================================
# INSTALL PYTHON PACKAGES
# ============================================================

RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# INSTALL PLAYWRIGHT
# ============================================================

RUN pip install playwright

RUN python -m playwright install chromium

# ============================================================
# COPY PROJECT
# ============================================================

COPY . .

# ============================================================
# EXPOSE PORT
# ============================================================

EXPOSE 8000

# ============================================================
# START APPLICATION
# ============================================================

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]