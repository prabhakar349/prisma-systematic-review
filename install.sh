#!/usr/bin/env bash
# Install this plugin so Claude Code discovers it as
# .claude-plugin/plugin.json + skills/ + agents/, the documented
# "skills-directory plugin" layout Claude Code auto-loads on startup.
#
# Usage:
#   ./install.sh                    # personal install: ~/.claude/skills/prisma-systematic-review
#   ./install.sh --project [path]   # project install: [path or .]/.claude/skills/prisma-systematic-review
#   ./install.sh --copy             # copy instead of symlink (default is symlink, so `git pull` here updates the install)
#   ./install.sh --uninstall [--project [path]]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="prisma-systematic-review"

if [[ ! -f "$SCRIPT_DIR/.claude-plugin/plugin.json" ]]; then
  echo "error: $SCRIPT_DIR/.claude-plugin/plugin.json not found — run this script from inside the cloned repo." >&2
  exit 1
fi

MODE="global"
LINK_METHOD="symlink"
UNINSTALL=false
PROJECT_PATH="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      MODE="project"
      if [[ $# -ge 2 && "$2" != --* ]]; then
        PROJECT_PATH="$2"
        shift
      fi
      ;;
    --copy) LINK_METHOD="copy" ;;
    --uninstall) UNINSTALL=true ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "$MODE" == "global" ]]; then
  DEST_DIR="$HOME/.claude/skills"
else
  DEST_DIR="$(cd "$PROJECT_PATH" && pwd)/.claude/skills"
fi
DEST="$DEST_DIR/$PLUGIN_NAME"

if $UNINSTALL; then
  if [[ -e "$DEST" || -L "$DEST" ]]; then
    rm -rf "$DEST"
    echo "Removed $DEST"
  else
    echo "Nothing installed at $DEST"
  fi
  exit 0
fi

mkdir -p "$DEST_DIR"

if [[ -e "$DEST" || -L "$DEST" ]]; then
  echo "error: $DEST already exists — run with --uninstall first if you want to reinstall." >&2
  exit 1
fi

if [[ "$LINK_METHOD" == "symlink" ]]; then
  ln -s "$SCRIPT_DIR" "$DEST"
  echo "Symlinked $DEST -> $SCRIPT_DIR"
  echo "(git pull in $SCRIPT_DIR will update the installed plugin automatically)"
else
  cp -R "$SCRIPT_DIR" "$DEST"
  echo "Copied plugin to $DEST"
fi

echo
echo "Installed '$PLUGIN_NAME' for $([ "$MODE" == "global" ] && echo "all projects (personal scope)" || echo "this project ($PROJECT_PATH)")."
echo "Restart Claude Code (or start a new session) for it to be picked up."
