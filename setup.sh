#!/bin/bash
# Setup script for the backend

echo "🚀 Setting up AI Academic Assistant Backend..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if yt-dlp is available
if ! command -v yt-dlp &> /dev/null; then
    echo "⚠️  yt-dlp not found in PATH. Installing via pip..."
    pip install yt-dlp
fi

echo "✅ yt-dlp found: $(yt-dlp --version | head -n 1)"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys!"
else
    echo "✅ .env file already exists"
fi

# Create downloads directory
mkdir -p downloads/audio
echo "✅ Created downloads directory"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your API keys"
echo "2. Run the server: uvicorn app.main:app --reload"
echo "3. Visit http://localhost:8000/docs for API documentation"
echo ""
