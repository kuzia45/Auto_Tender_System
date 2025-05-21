#!/bin/bash

set -e

# tail -f /dev/null

exec uvicorn app:app --host 0.0.0.0 --port 8000