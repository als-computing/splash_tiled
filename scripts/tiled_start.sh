#!/usr/bin/env bash
set -euo pipefail

exec tiled serve config "$@"
