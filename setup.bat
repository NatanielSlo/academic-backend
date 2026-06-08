@echo off
REM Setup script for the backend (Windows)

echo 🚀 Setting up AI Academic Assistant Backend...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.9 or higher.
    exit /b 1
)

echo ✅ Python found
python --version

REM Create virtual environment
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
) else (
    echo ✅ Virtual environment already exists
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Check if yt-dlp is available
where yt-dlp >nul 2>&1
if errorlevel 1 (
    echo ⚠️  yt-dlp not found in PATH. Installing via pip...
    pip install yt-dlp
)

echo ✅ yt-dlp installed

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo 📝 Creating .env file from template...
    copy .env.example .env
    echo ⚠️  Please edit .env and add your API keys!
) else (
    echo ✅ .env file already exists
)

REM Create downloads directory
if not exist "downloads\audio" mkdir downloads\audio
echo ✅ Created downloads directory

echo.
echo ✅ Setup complete!
echo.
echo Next steps:
echo 1. Edit .env and add your API keys
echo 2. Run the server: uvicorn app.main:app --reload
echo 3. Visit http://localhost:8000/docs for API documentation
echo.
pause
