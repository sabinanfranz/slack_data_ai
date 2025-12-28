#!/usr/bin/env bash
set -euo pipefail

exec python -m app.jobs.daily_report
