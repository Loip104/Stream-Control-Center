#!/bin/bash

PYTHON_EXE="./python_embed/bin/python3"

echo "Starte Stream Control Center..."

if [ ! -f "$PYTHON_EXE" ]; then
    echo "FEHLER: Python wurde nicht gefunden. Bitte führe zuerst setup.sh aus."
    exit 1
fi

"$PYTHON_EXE" web_manager.py