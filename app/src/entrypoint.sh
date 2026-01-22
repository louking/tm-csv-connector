#!/bin/sh

# this is primarily for crond service

set -e
set -x

SSH_DIR="/root/.ssh"

# 2. Change ownership and permissions
# -R: Recursive for all files
# 700: Strict permissions (only root user can read/write/execute)
chown -R root:root $SSH_DIR
chmod 700 $SSH_DIR
chmod 600 $SSH_DIR/*

exec "$@"
