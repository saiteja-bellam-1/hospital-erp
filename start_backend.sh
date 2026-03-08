#!/bin/bash
echo "🏥 Starting Hospital ERP Backend..."
echo "=================================="

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to backend directory
cd "$DIR/backend"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run the setup script first:"
    echo "   python3 install_and_setup.py"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ main.py not found in backend directory"
    exit 1
fi

# Start the server
echo "Starting FastAPI server on http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo "Press Ctrl+C to stop the server"
echo ""

python start_server.py