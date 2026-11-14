#!/bin/bash
# Wall-E Companion - Start Script (Linux/Mac)
# Usage: ./start.sh [--mock] [--no-web]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Iniciando Wall-E Companion..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Instalando dependencias..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run main
python main.py "$@"