#!/usr/bin/env bash
#
# Pre-flight environment check for Gemini Video Gen plugin.
# Validates API key configuration and dependencies.
#
# Usage:
#   ./check_env.sh [plugin_dir]
#
# Arguments:
#   plugin_dir: Optional path to the plugin directory (default: script's parent)
#
# Exit codes:
#   0: All checks passed
#   1: General error
#   2: Environment check failed (shown to Claude)

set -o errexit
set -o nounset
set -o pipefail

# Determine plugin directory (where this script lives)
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PLUGIN_DIR="${1:-$(dirname "${SCRIPT_DIR}")}"
readonly MAIN_SCRIPT="${PLUGIN_DIR}/main.py"
readonly HOME_ENV="${HOME}/.config/video-gen-4-claude/.env"

# ANSI color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'  # No Color

#######################################
# Print a success message.
# Arguments:
#   Message to print
#######################################
print_ok() {
  echo -e "${GREEN}[OK]${NC} $1"
}

#######################################
# Print an error message.
# Arguments:
#   Message to print
#######################################
print_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

#######################################
# Print a warning message.
# Arguments:
#   Message to print
#######################################
print_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

#######################################
# Check if an .env file holds a real GOOGLE_AI_API_KEY.
# Keeps everything after the first '=', strips CR and surrounding quotes.
# Arguments:
#   Path to the .env file
# Returns:
#   0 if a non-placeholder key is present, 1 otherwise
#######################################
env_file_has_key() {
  local file="$1"
  [[ -f "${file}" ]] || return 1

  local line key_value
  line="$(grep -m1 "^GOOGLE_AI_API_KEY=" "${file}" || true)"
  [[ -n "${line}" ]] || return 1

  key_value="${line#GOOGLE_AI_API_KEY=}"
  key_value="${key_value%$'\r'}"
  key_value="${key_value#[\"\']}"
  key_value="${key_value%[\"\']}"

  [[ -n "${key_value}" ]] \
    && [[ "${key_value}" != "your_key_here" ]] \
    && [[ "${key_value}" != "your_api_key_here" ]]
}

#######################################
# Check if GOOGLE_AI_API_KEY is available from any source.
# Checks in order:
#   1. Environment variable
#   2. ~/.config/video-gen-4-claude/.env
#   3. Plugin directory .env
# Returns:
#   0 if valid, 1 if not found
#######################################
check_api_key() {
  # 1. Check environment variable
  if [[ -n "${GOOGLE_AI_API_KEY:-}" ]] \
      && [[ "${GOOGLE_AI_API_KEY}" != "your_key_here" ]] \
      && [[ "${GOOGLE_AI_API_KEY}" != "your_api_key_here" ]]; then
    print_ok "GOOGLE_AI_API_KEY is set in environment"
    return 0
  fi

  # 2. Check home config (recommended), 3. plugin directory .env
  local env_file
  for env_file in "${HOME_ENV}" "${PLUGIN_DIR}/.env"; do
    if env_file_has_key "${env_file}"; then
      print_ok "GOOGLE_AI_API_KEY found in ${env_file}"
      return 0
    fi
  done

  print_error "GOOGLE_AI_API_KEY not found"
  echo "       Set it using one of these methods:"
  echo "       1. Create ~/.config/video-gen-4-claude/.env with: GOOGLE_AI_API_KEY=your_key"
  echo "       2. export GOOGLE_AI_API_KEY=your_key"
  echo "       Get API key from: https://aistudio.google.com/apikey"
  return 1
}

#######################################
# Check if uv package manager is installed.
# Returns:
#   0 if installed, 1 if not
#######################################
check_uv_installed() {
  if command -v uv &> /dev/null; then
    print_ok "uv package manager is installed"
    return 0
  fi

  print_error "uv package manager not found"
  echo "       Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "       Windows: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
  return 1
}

#######################################
# Check if main.py exists.
# Returns:
#   0 if exists, 1 if not
#######################################
check_main_script() {
  if [[ -f "${MAIN_SCRIPT}" ]]; then
    print_ok "main.py found"
    return 0
  fi

  print_error "main.py not found at ${MAIN_SCRIPT}"
  return 1
}

#######################################
# Main entry point.
#######################################
main() {
  local checks_passed=true

  echo "=== Gemini Video Gen Environment Check ==="
  echo "Plugin directory: ${PLUGIN_DIR}"
  echo ""

  check_api_key || checks_passed=false
  check_uv_installed || checks_passed=false
  check_main_script || checks_passed=false

  echo ""

  if [[ "${checks_passed}" == true ]]; then
    echo -e "${GREEN}=== All checks passed! Ready to generate videos. ===${NC}"
    exit 0
  else
    echo -e "${RED}=== Environment check failed. Fix issues above. ===${NC}"
    exit 2
  fi
}

main "$@"
