#!/usr/bin/env bash

COMMIT_MESSAGE="${1:-Update: $(date '+%Y-%m-%d %H:%M:%S')}"

git add .
git commit -m "$COMMIT_MESSAGE"
git pull origin main --rebase
git push origin main
