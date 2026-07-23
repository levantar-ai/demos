#!/usr/bin/env bash
# Emit a JSON array of demo directories (e.g. ["agentcore/01-first-agent"])
# whose files changed between BASE_SHA and HEAD_SHA. A demo is any
# <category>/<demo>/ directory containing a terraform/ subdirectory.
set -euo pipefail

BASE_SHA="${1:?usage: changed-demos.sh <base-sha> <head-sha>}"
HEAD_SHA="${2:?usage: changed-demos.sh <base-sha> <head-sha>}"

git diff --name-only "$BASE_SHA" "$HEAD_SHA" |
  awk -F/ 'NF>=3 {print $1"/"$2}' |
  sort -u |
  while read -r dir; do
    [ -d "$dir/terraform" ] && echo "$dir"
  done |
  jq -R -s -c 'split("\n") | map(select(length > 0))'
