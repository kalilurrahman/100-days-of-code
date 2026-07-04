#!/bin/sh
# Copy the watracker package + sample into the playground for static hosting.
# Run after changing any watracker/*.py file (tests/test_playground.py enforces sync).
cd "$(dirname "$0")"
mkdir -p watracker
cp ../watracker/*.py watracker/
cp ../samples/sample_chat.txt sample_chat.txt
echo "playground assets refreshed"
