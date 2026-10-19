#!/usr/bin/env bash
# Run the demo on macOS or Linux.
# First run: creates a virtual environment in .venv and installs the packages.
# Extra options are passed on, for example:  ./run_demo.sh --inject 50
set -e

cd "$(dirname "$0")"

# run_demo.py needs Python 3.11 or newer; on macOS the default python3 is often older.
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python 3.11 or newer was not found. See \"Install Python\" in README.md." >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PY" -m venv .venv
fi

echo "Installing packages (first run can take a minute) ..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

.venv/bin/python run_demo.py "$@"
