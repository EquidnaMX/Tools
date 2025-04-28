#!/bin/bash
set -uo pipefail

# ─── Colors ─────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# ─── Defaults ───────────────────────────────────────────────────
TIMEOUT=1
MAX_PARALLEL=10
PROGRESS=false
CREATE_BASE=false
STRICT_HOST_CHECKING=false
SSH_KEY=""
DRY_RUN=false
COMPRESS=false
EMAIL_NOTIFY=""
WEBHOOK_URL=""
FILES_TO_UPLOAD=()
DIRS_TO_UPLOAD=()
EXCLUDES=()
FILE_LIST=""
LOG_FILE="/tmp/upload_log_$(date +%Y%m%d_%H%M%S).txt"
TEMP_PROGRESS_FILE="/tmp/upload_progress_counter.txt"

# ─── Usage ───────────────────────────────────────────────────────
print_usage() {
  cat <<EOF
Usage:
  $0 <remote_user> <network_spec> <remote_base_dir> [file_list.txt] [options]

Options:
  --file "path/to/file"        Add single file manually
  --dir "path/to/dir"          Add full directory recursively
  --exclude "pattern"          Exclude file or folder pattern
  --timeout N                  Ping timeout seconds (default 1)
  --progress                   Show real-time progress bar
  --dry-run                    Only simulate uploads
  --compress                   Compress files before upload
  --create-base-path           Create remote base path if missing
  --strict-host-checking       Enable StrictHostKeyChecking=yes
  --ssh-key /path/to/key        Use SSH key authentication
  --email you@example.com      Send summary email at end
  --webhook https://url         Send summary to webhook at end

Examples:
  ./update_hosts.sh pi 10.8.0.0/24 /home/pi/MK5 --dir "./site" --file "config.ini" --exclude "*.log" --progress --compress
EOF
}

if [ $# -lt 3 ]; then
  print_usage
  exit 1
fi

# ─── Parse Arguments ─────────────────────────────────────────────
REMOTE_USER=$1
NETWORK_SPEC=$2
REMOTE_BASE=$3
shift 3

while (( $# )); do
  case $1 in
    --file) FILES_TO_UPLOAD+=("$2"); shift 2 ;;
    --dir) DIRS_TO_UPLOAD+=("$2"); shift 2 ;;
    --exclude) EXCLUDES+=("$2"); shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --compress) COMPRESS=true; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --progress) PROGRESS=true; shift ;;
    --create-base-path) CREATE_BASE=true; shift ;;
    --strict-host-checking) STRICT_HOST_CHECKING=true; shift ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    --email) EMAIL_NOTIFY="$2"; shift 2 ;;
    --webhook) WEBHOOK_URL="$2"; shift 2 ;;
    *)
      if [[ -z "$FILE_LIST" && -f "$1" ]]; then
        FILE_LIST="$1"
        shift
      else
        echo "❌ Unknown or invalid parameter: $1"
        print_usage
        exit 1
      fi
      ;;
  esac
done

# ─── Setup SSH Options ───────────────────────────────────────────
SSH_OPTIONS="-o ConnectTimeout=3 -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=3 -o ServerAliveCountMax=1"

if [ "$STRICT_HOST_CHECKING" = true ]; then
  SSH_OPTIONS="$SSH_OPTIONS -o StrictHostKeyChecking=yes"
else
  SSH_OPTIONS="$SSH_OPTIONS -o StrictHostKeyChecking=no"
fi

if [ -n "$SSH_KEY" ]; then
  SSH_OPTIONS="$SSH_OPTIONS -i $SSH_KEY"
  echo -e "${CYAN}🔐 Using SSH Key Authentication${NC}" | tee -a "$LOG_FILE"
else
  echo -e "${YELLOW}🔑 Using Password Authentication${NC}" | tee -a "$LOG_FILE"
fi

# ─── Dependency Check ───────────────────────────────────────────
required_cmds=( ssh scp ping )
[[ -z "$SSH_KEY" ]] && required_cmds+=( sshpass )
$COMPRESS && required_cmds+=( gzip )
for cmd in "${required_cmds[@]}"; do
  if ! command -v "$cmd" &>/dev/null; then
    echo -e "❌ Required command not found: ${RED}$cmd${NC}"
    exit 1
  fi
done

# ─── Ask Password Early ─────────────────────────────────────────
if [ "$DRY_RUN" = false ] && [ -z "${SSH_KEY:-}" ]; then
  read -s -p "Enter SSH password: " SSHPASS
  echo
fi

# ─── Helpers ─────────────────────────────────────────────────────
log() { echo -e "$@" | tee -a "$LOG_FILE"; }

is_excluded() {
  local filepath="$1"
  for pattern in "${EXCLUDES[@]:-}"; do
    if [[ "$filepath" == $pattern ]]; then
      return 0
    fi
  done
  return 1
}

expand_directories_and_files() {
  for dir in "${DIRS_TO_UPLOAD[@]:-}"; do
    while IFS= read -r -d '' file; do
      relative_path="${file#${dir}/}"
      if ! is_excluded "$relative_path"; then
        FILES_TO_UPLOAD+=("$relative_path")
      fi
    done < <(find "$dir" -type f -print0)
  done

  if [[ -n "$FILE_LIST" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ -z "$line" ]] && continue
      if ! is_excluded "$line"; then
        FILES_TO_UPLOAD+=("$line")
      fi
    done < "$FILE_LIST"
  fi
}

cidr2ips() {
  local cidr=$1
  IFS=/ read ip mask <<<"$cidr"
  IFS=. read -r a b c d <<<"$ip"
  local ipd=$((a<<24|b<<16|c<<8|d))
  local m=$((0xFFFFFFFF<<(32-mask) & 0xFFFFFFFF))
  local net=$((ipd & m)); local bc=$((net|(~m&0xFFFFFFFF)))
  for ((i=net+1; i<bc; i++)); do
    alive_hosts+=("$((i>>24&0xFF)).$((i>>16&0xFF)).$((i>>8&0xFF)).$((i&0xFF))")
  done
}

parse_ips() {
  if [[ $NETWORK_SPEC == */* ]]; then
    cidr2ips "$NETWORK_SPEC"
  elif [[ $NETWORK_SPEC == *-* ]]; then
    IFS=- read -r s e <<<"$NETWORK_SPEC"
    base=${s%.*}.; start=${s##*.}; end=${e##*.}
    for ((i=start; i<=end; i++)); do alive_hosts+=("${base}${i}"); done
  else
    echo "❌ Invalid network spec: $NETWORK_SPEC"
    exit 1
  fi
}

# ─── Progress Monitor ───────────────────────────────────────────
start_progress_monitor() {
  echo 0 > "$TEMP_PROGRESS_FILE"
  (
    while true; do
      done=$(< "$TEMP_PROGRESS_FILE")
      printf "\rProgress: ["
      width=50
      filled=$((done * width / total_hosts))
      empty=$((width - filled))
      printf "#%.0s" $(seq 1 $filled)
      printf " %.0s" $(seq 1 $empty)
      printf "] %3d%% (%d/%d)" $((done * 100 / total_hosts)) "$done" "$total_hosts"

      if [ "$done" -ge "$total_hosts" ]; then
        echo
        exit 0
      fi
      sleep 0.2
    done
  ) &
  progress_pid=$!
}

increment_progress() {
  (
    flock 200
    count=$(< "$TEMP_PROGRESS_FILE")
    echo $((count + 1)) > "$TEMP_PROGRESS_FILE"
  ) 200>"$TEMP_PROGRESS_FILE.lock"
}

# ─── Upload Function ────────────────────────────────────────────
upload_to_host() {
  local IP="$1"
  local PASS="$2"

  log "[${IP}] Connecting..."

  if [[ -z "$SSH_KEY" ]]; then
    sshpass -p "$PASS" ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "[ -d \"$REMOTE_BASE\" ]"
  else
    ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "[ -d \"$REMOTE_BASE\" ]"
  fi
  if [ $? -ne 0 ]; then
    if [ "$CREATE_BASE" = true ]; then
      log "[${IP}] 🛠️ Creating base directory $REMOTE_BASE"
      if [[ -z "$SSH_KEY" ]]; then
        sshpass -p "$PASS" ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "mkdir -p \"$REMOTE_BASE\""
      else
        ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "mkdir -p \"$REMOTE_BASE\""
      fi
    else
      log "[${IP}] ❌ Base directory missing. Skipping."
      increment_progress
      return
    fi
  fi

  for LOCAL_FILE in "${FILES_TO_UPLOAD[@]}"; do
    if [ ! -f "$LOCAL_FILE" ]; then
      log "[${IP}] ❌ Local file missing: $LOCAL_FILE"
      continue
    fi
    REMOTE_PATH="$REMOTE_BASE/$LOCAL_FILE"
    REMOTE_DIR=$(dirname "$REMOTE_PATH")

    if [[ "$REMOTE_DIR" != "$REMOTE_BASE" ]]; then
      if [[ -z "$SSH_KEY" ]]; then
        sshpass -p "$PASS" ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "mkdir -p \"$REMOTE_DIR\""
      else
        ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "mkdir -p \"$REMOTE_DIR\""
      fi
    fi

    if [ "$COMPRESS" = true ]; then
      tmp_gz="/tmp/$(basename "$LOCAL_FILE").gz"
      gzip -c "$LOCAL_FILE" > "$tmp_gz"
      if [[ -z "$SSH_KEY" ]]; then
        sshpass -p "$PASS" scp $SSH_OPTIONS "$tmp_gz" "$REMOTE_USER@$IP:$REMOTE_PATH.gz"
      else
        scp $SSH_OPTIONS "$tmp_gz" "$REMOTE_USER@$IP:$REMOTE_PATH.gz"
      fi
      scp_status=$?
      rm -f "$tmp_gz"
      if [ $scp_status -eq 0 ]; then
        if [[ -z "$SSH_KEY" ]]; then
          sshpass -p "$PASS" ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "gunzip -f \"$REMOTE_PATH.gz\""
        else
          ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "gunzip -f \"$REMOTE_PATH.gz\""
        fi
        log "[${IP}] ✅ Uploaded compressed $(basename "$LOCAL_FILE")"
      else
        log "[${IP}] ❌ Upload failed (compressed): $LOCAL_FILE"
      fi
    else
      if [[ -z "$SSH_KEY" ]]; then
        sshpass -p "$PASS" scp $SSH_OPTIONS "$LOCAL_FILE" "$REMOTE_USER@$IP:$REMOTE_PATH"
      else
        scp $SSH_OPTIONS "$LOCAL_FILE" "$REMOTE_USER@$IP:$REMOTE_PATH"
      fi
      if [ $? -eq 0 ]; then
        log "[${IP}] ✅ Uploaded $(basename "$LOCAL_FILE")"
      else
        log "[${IP}] ❌ Upload failed: $LOCAL_FILE"
      fi
    fi
  done

  increment_progress
}

# ─── Expand all inputs ───────────────────────────────────────────
expand_directories_and_files

# ─── Alive Hosts Scan ────────────────────────────────────────────
declare -a alive_hosts
declare -A HOST_SUCCESS HOST_FAIL

log "🔍 Scanning alive hosts (timeout=${TIMEOUT}s)..."
parse_ips

final_hosts=()
for ip in "${alive_hosts[@]}"; do
  ping -c1 -W"$TIMEOUT" "$ip" &>/dev/null && final_hosts+=("$ip")
done

total_hosts=${#final_hosts[@]}

if (( total_hosts == 0 )); then
  echo "❌ No alive hosts found!"
  exit 1
fi

log "✅ Found $total_hosts alive hosts."

# ─── Upload Phase ─────────────────────────────────────────────────
> "$TEMP_PROGRESS_FILE"

if [ "$PROGRESS" = true ]; then
  start_progress_monitor
fi

active_jobs=0
for ip in "${final_hosts[@]}"; do
  upload_to_host "$ip" "$SSHPASS" &
  ((active_jobs++))
  if (( active_jobs >= MAX_PARALLEL )); then
    wait
    active_jobs=0
  fi
done

wait

if [ "$PROGRESS" = true ]; then
  wait "$progress_pid" 2>/dev/null || true
fi

# ─── Final Summary ───────────────────────────────────────────────
log ""
log "🎯 ${GREEN}All uploads completed!${NC}"
log "${CYAN}═══════════════════════════════════════"
log "               Upload Summary          "
log "═══════════════════════════════════════${NC}"

for ip in "${final_hosts[@]}"; do
  log "[${ip}] Upload complete."
done

log "${CYAN}═══════════════════════════════════════${NC}"
log "📄 Detailed session log saved to: ${YELLOW}${LOG_FILE}${NC}"

# ─── Email Notification ──────────────────────────────────────────
if [[ -n "$EMAIL_NOTIFY" && $(command -v mail) ]]; then
  {
    echo "Upload session completed."
    echo ""
    cat "$LOG_FILE"
  } | mail -s "Upload Session Report" "$EMAIL_NOTIFY"
  log "📧 Email notification sent to ${YELLOW}$EMAIL_NOTIFY${NC}"
fi

# ─── Webhook Notification ────────────────────────────────────────
if [[ -n "$WEBHOOK_URL" && $(command -v curl) ]]; then
  webhook_data=$(jq -n \
    --arg log "$(cat "$LOG_FILE")" \
    '{
      event: "upload_complete",
      log: $log
    }')
  curl -s -X POST -H "Content-Type: application/json" -d "$webhook_data" "$WEBHOOK_URL"
  log "🌐 Webhook notification sent to ${YELLOW}$WEBHOOK_URL${NC}"
fi

# ─── Cleanup ─────────────────────────────────────────────────────
rm -f "$TEMP_PROGRESS_FILE" "$TEMP_PROGRESS_FILE.lock"

# ─── Done ────────────────────────────────────────────────────────
exit 0
