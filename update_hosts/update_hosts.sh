#!/bin/bash
set -euo pipefail

### Globals & Configuration
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
TEMP_ARCHIVE="$(mktemp /tmp/upload_package_XXXXXX.tar.gz)"

LOG_FILE="upload_log_$(date +%Y%m%d_%H%M%S).txt"

TIMEOUT=1
DRY_RUN=false
COMPRESS=false
VERBOSE=false

FILE_LIST_FILE=""
FILES_TO_UPLOAD=()
DIRS_TO_UPLOAD=()
EXCLUDES=()
LOCAL_ROOT=""

SSH_KEY=""
HOST_FILE=""
STRICT_CHECKING=false
CREATE_BASE=false

EMAIL_NOTIFY=""
WEBHOOK_URL=""

declare -a alive_hosts
declare -A upload_results

cleanup() { 
  [[ -f "$TEMP_ARCHIVE" ]] && rm -f "$TEMP_ARCHIVE"; 
}

print_usage() {
  cat <<EOF
Usage: $0 <remote_user> <network_spec_or_hostfile> [options]
Options:
  --remote-path <path>    Specify the remote base directory (default: /home/<REMOTE_USER>)
  --file <file>            Upload a file
  --dir <directory>        Upload contents of directory
  --file-list <file>       Load file paths from list
  --exclude <pattern>      Exclude file pattern
  --local-path <path>      Prepend path to local files
  --ssh-key <path>         SSH private key
  --host-file <file>       Use a file of hosts
  --timeout <seconds>      Ping timeout (default: 1)
  --compress               Compress before upload
  --create-base-path       Create target path on remote if missing
  --strict-host-checking   Enforce strict SSH checking
  --dry-run                Show what would be done
  --verbose                Show verbose SSH/SCP output and save to log
  --email <address>        Send result by email
  --webhook <url>          Send result to webhook
  --help                   Show this help
EOF
}

validate_input() {
  local input="$1"
  local regex='^[a-zA-Z0-9._/-]+$'
  if [[ ! $input =~ $regex ]]; then
    echo -e "${RED}❌ Invalid input detected: $input${NC}" >&2
    exit 1
  fi
}

remote_exec() {
  local host="$1" cmd="$2"

  if [ -n "$SSH_KEY" ]; then
    if [ "$VERBOSE" = true ]; then
      ssh -i "$SSH_KEY" $SSH_OPTIONS "$REMOTE_USER@$host" "$cmd" 2>>"$LOG_FILE"
    else
      ssh -i "$SSH_KEY" $SSH_OPTIONS "$REMOTE_USER@$host" "$cmd"
    fi
  else
    if [ "$VERBOSE" = true ]; then
      sshpass -p "$SSHPASS" ssh $SSH_OPTIONS "$REMOTE_USER@$host" "$cmd" 2>>"$LOG_FILE"
    else
      sshpass -p "$SSHPASS" ssh $SSH_OPTIONS "$REMOTE_USER@$host" "$cmd"
    fi
  fi
}

remote_copy() {
  local src="$1" dst="$2" host="$3"

  if [ -n "$SSH_KEY" ]; then
    if [ "$VERBOSE" = true ]; then
      scp -i "$SSH_KEY" $SSH_OPTIONS "$src" "$REMOTE_USER@$host:$dst" 2>>"$LOG_FILE"
    else
      scp -i "$SSH_KEY" $SSH_OPTIONS "$src" "$REMOTE_USER@$host:$dst"
    fi
  else
    if [ "$VERBOSE" = true ]; then
      sshpass -p "$SSHPASS" scp $SSH_OPTIONS "$src" "$REMOTE_USER@$host:$dst" 2>>"$LOG_FILE"
    else
      sshpass -p "$SSHPASS" scp $SSH_OPTIONS "$src" "$REMOTE_USER@$host:$dst"
    fi
  fi
}

upload_files() {

  local host="$1"

  if [ "$COMPRESS" = true ]; then
    echo -e "[${host}] Uploading compressed package..."
  
    remote_copy "$TEMP_ARCHIVE" "$REMOTE_BASE/upload_package.tar.gz" "$host"
    remote_exec "$host" "cd '$REMOTE_BASE' && tar -xzf upload_package.tar.gz && rm upload_package.tar.gz" || {
      upload_results[$host]="upload failed"
      return 1
    }
  else
  
    for file in "${FILES_TO_UPLOAD[@]}"; do
    
      if [ ! -f "$file" ]; then
        echo -e "${RED}[${host}] Missing file: $file${NC}"
        upload_results[$host]="file failed: $file (not found)"
        continue
      fi
      
      local remote_file="$REMOTE_BASE/${file#${LOCAL_ROOT%/}/}"

      if [ "$VERBOSE" = true ]; then
        echo -e "[${CYAN}${host}] Uploading $file to $remote_file...${NC}"      
      fi
      
      remote_copy "$file" "$remote_file" "$host" || {
        upload_results[$host]="file failed: $file"
        return 1
      }
    done
  fi

  return 0
}

parse_ips() {
  echo -en "${CYAN}Scanning hosts...${NC}"

  if [ -z "$NETWORK_SPEC" ]; then
    echo -e "${RED}❌ NETWORK_SPEC is not set.${NC}"; exit 1
  fi

  local cidr="$NETWORK_SPEC"
  local potential=()
  local base s e ip mask a b c d ipd m net bc j host

  alive_hosts=()

  if [[ $cidr == */* ]]; then
    IFS=/ read -r ip mask <<< "$cidr"
    IFS=. read -r a b c d <<< "$ip"

    ipd=$((a<<24 | b<<16 | c<<8 | d))
    m=$((0xFFFFFFFF << (32 - mask) & 0xFFFFFFFF))
    net=$((ipd & m))
    bc=$((net | (~m & 0xFFFFFFFF)))

    for ((j=net+1; j<bc; j++)); do
      potential+=("$((j>>24&255)).$((j>>16&255)).$((j>>8&255)).$((j&255))")
    done

  elif [[ $cidr == *-* ]]; then
    IFS=- read -r start end <<< "$cidr"
    base=${start%.*}.
    s=${start##*.}
    e=${end##*.}

    for ((j=s; j<=e; j++)); do 
      potential+=("${base}${j}")
    done

  elif [[ $cidr =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    potential+=("$cidr")
  else
    echo -e "${RED}❌ Invalid network spec: $cidr${NC}"
    exit 1
  fi

  for host in "${potential[@]}"; do
    if ping -c1 -W "${TIMEOUT:=1}" "$host" &>/dev/null; then
      alive_hosts+=("$host")
    fi
  done

  echo -e "${GREEN}✅ Found ${#alive_hosts[@]} alive host(s).${NC}"
}

# Validate remote path existence before any transfer
validate_remote_path() {
  local host="$1" remote_path="$2"

  if [ -n "$SSH_KEY" ]; then
    ssh -i "$SSH_KEY" $SSH_OPTIONS "$REMOTE_USER@$host" "[ -d '$remote_path' ]" || {
      echo -e "${RED}❌ Remote path does not exist on $host: $remote_path${NC}" >&2
      return 1
    }
  else
    sshpass -p "$SSHPASS" ssh $SSH_OPTIONS "$REMOTE_USER@$host" "[ -d '$remote_path' ]" || {
      echo -e "${RED}❌ Remote path does not exist on $host: $remote_path${NC}" >&2
      return 1
    }
  fi

  return 0
}

# Ensure remote folders are created for files in subfolders, avoiding redundant creation
create_remote_folders() {
  local host="$1"
  declare -A created_dirs=()

  for file in "${FILES_TO_UPLOAD[@]}"; do    

    local remote_dir="$(dirname "${file#${LOCAL_ROOT%/}/}")"
    local segments=$REMOTE_BASE

    IFS='/' read -ra parts <<< "$remote_dir"
   
    for segment in "${parts[@]}"; do
      segments+="/$segment"
      
      if [ -z "${created_dirs[$segments]:-}" ]; then
        
        if [ "$VERBOSE" = true ]; then
          echo -e "${CYAN}📁 [${host}] Creating remote directory:$segments${NC}"
        fi

        remote_exec "$host" "mkdir -p '$segments'" || {
          echo -e "${RED}❌ Failed to create remote directory: $segments on $host${NC}" >&2
          upload_results[$host]="mkdir failed"
          return 1
        }

        created_dirs[$segments]=1
      fi

    done
  done
}

#####  MAIN LOOP  #####

trap 'cleanup; echo -e "\n${RED}\u26a0 Script interrupted!${NC}"; exit 1' SIGHUP SIGINT SIGTERM
trap 'cleanup' EXIT

if [ $# -lt 2 ]; then 
  print_usage; exit 1; 
fi

REMOTE_USER="$1"; 
NETWORK_SPEC="$2"; 

validate_input "$REMOTE_USER"
validate_input "$NETWORK_SPEC"

shift 2

while (( $# )); do
  case "$1" in
    --remote-path) REMOTE_BASE="$2"; shift 2;;
    --file) FILES_TO_UPLOAD+=("$2"); shift 2;;
    --dir) DIRS_TO_UPLOAD+=("$2"); shift 2;;
    --file-list) FILE_LIST_FILE="$2"; shift 2;;
    --exclude) EXCLUDES+=("$2"); shift 2;;
    --local-path) LOCAL_ROOT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --host-file) HOST_FILE="$2"; shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    --dry-run) DRY_RUN=true; shift;;
    --compress) COMPRESS=true; shift;;
    --create-base-path) CREATE_BASE=true; shift;;
    --strict-host-checking) STRICT_CHECKING=true; shift;;
    --verbose) VERBOSE=true; shift;;
    --email) EMAIL_NOTIFY="$2"; shift 2;;
    --webhook) WEBHOOK_URL="$2"; shift 2;;
    --help) print_usage; exit 0;;
    *) echo -e "${RED}\u274c Unknown option: $1${NC}"; print_usage; exit 1;;
  esac
done

# Ensure REMOTE_BASE is initialized with a default value if not set
if [ -z "${REMOTE_BASE:-}" ]; then
  REMOTE_BASE="/home/$REMOTE_USER"
  echo -e "${YELLOW}⚠️ - Remote PATH not set. Using default: $REMOTE_BASE${NC}"
fi

# 0 -- Set log level
LOGLEVEL="ERROR"
[ "$VERBOSE" = true ] && LOGLEVEL="INFO"

# Ensure the log file is initialized and writable
if [ "$VERBOSE" = true ]; then
  touch "$LOG_FILE" || {
    echo -e "${RED}❌ Failed to create or write to log file: $LOG_FILE${NC}" >&2
    exit 1
  }
fi

# 1 -- Validate HOST_FILE and NETWORK_SPEC
[ -n "$LOCAL_ROOT" ] && validate_input "$LOCAL_ROOT"
[ -n "$SSH_KEY" ] && validate_input "$SSH_KEY"
[ -n "$HOST_FILE" ] && validate_input "$HOST_FILE"

# 2 -- Validate FILE_LIST_FILE and load items into FILES_TO_UPLOAD
if [ -n "$FILE_LIST_FILE" ]; then
  validate_input "$FILE_LIST_FILE"
  mapfile -t list_files < "$FILE_LIST_FILE"
  FILES_TO_UPLOAD+=("${list_files[@]}")
fi

# Ensure files from directories in DIRS_TO_UPLOAD are added to FILES_TO_UPLOAD
for dir in "${DIRS_TO_UPLOAD[@]}"; do
  
  # Only prepend LOCAL_PATH if the path is relative
  if [[ "$dir" != /* ]]; then    
    [ -n "$LOCAL_ROOT" ] && path="${LOCAL_ROOT%/}/$dir"
  else
    # Use absolute path as-is
    path="$dir"
  fi

  if [ -d "$path" ]; then
    while IFS= read -r -d $'\0' file; do
      if [ "$VERBOSE" = true ]; then 
        echo -e "${CYAN}📁 Adding file to upload list: $file${NC}"; 
      fi
      FILES_TO_UPLOAD+=("$file")
    done < <(find "$path" -type f -print0)
  else
    echo -e "${RED}❌ Directory not found: $path${NC}" >&2
    exit 1
  fi
done


# 4 -- IF no files or directories are specified, exit
if [ ${#FILES_TO_UPLOAD[@]} -eq 0 ] && [ ${#DIRS_TO_UPLOAD[@]} -eq 0 ]; then
  echo -e "${RED}❌ No files or directories specified for upload. Aborting.${NC}"
  exit 1
fi

# 5 -- Validate existence of files and directories
for file in "${FILES_TO_UPLOAD[@]}"; do 
  if [ ! -f "$file" ]; then
    echo -e "${RED}❌ File not found: $file${NC}" >&2
    exit 1
  fi
done

for dir in "${DIRS_TO_UPLOAD[@]}"; do
  path="$dir"  # Removed 'local' keyword
  [ -n "$LOCAL_ROOT" ] && path="${LOCAL_ROOT%/}/$dir"
  if [ ! -d "$path" ]; then
    echo -e "${RED}❌ Directory not found: $path${NC}" >&2
    exit 1
  fi
done

# 6 -- Validate SSH key and password (If not using SSH key or dry run)
if [ "$DRY_RUN" = false ] && [ -z "$SSH_KEY" ] ; then
  echo -n "Enter SSH password: "; read -s SSHPASS; echo;
fi

[ -n "$SSH_KEY" ] && [ ! -f "$SSH_KEY" ] && { echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"; exit 1; }

#7 set SSH options
SSH_OPTIONS="-o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null -o LogLevel=$LOGLEVEL"
[ "$STRICT_CHECKING" = true ] && SSH_OPTIONS="$SSH_OPTIONS -o StrictHostKeyChecking=yes" || SSH_OPTIONS="$SSH_OPTIONS -o StrictHostKeyChecking=no"


# 8 -- Validate that there are hosts available to upload to
[ -n "$HOST_FILE" ] && mapfile -t alive_hosts < "$HOST_FILE" || parse_ips
[ ${#alive_hosts[@]} -eq 0 ] && echo -e "${RED}❌ No alive hosts found.${NC}" && exit 1


# 9 -- Create compressed archive if needed
if [ "$COMPRESS" = true ]; then
  echo -e "${CYAN}📦 Compressing files...${NC}"  
  tar -czf "$TEMP_ARCHIVE" -C "${LOCAL_ROOT:-.}" "${FILES_TO_UPLOAD[@]}"
fi

# 10 -- Upload files to each host
for ip in "${alive_hosts[@]}"; do
  echo -e "🚀 [$ip] Upload started..."

  if [ "$DRY_RUN" = true ]; then
    echo -e "🧪 [DRY-RUN] Would upload to $ip"; 
    upload_results[$ip]="ok"; 
    continue; 
  fi

  if ! validate_remote_path "$ip" "$REMOTE_BASE"; then
    upload_results[$ip]="remote path missing"
    continue
  fi

  if [ "$CREATE_BASE" = true ]; then
    echo -e "📁 [$ip] Creating $REMOTE_BASE (If it does not exists)..."
    remote_exec "$ip" "mkdir -p '$REMOTE_BASE'" || {
      upload_results[$ip]="mkdir failed"
      continue
    }
  fi

  create_remote_folders "$ip" || continue
  upload_files "$ip" && upload_results[$ip]="ok"
done

# 11 -- Notify completion
[ -n "$EMAIL_NOTIFY" ] && echo "Upload completed." | mail -s "Upload Completed" "$EMAIL_NOTIFY"
[ -n "$WEBHOOK_URL" ] && curl -s -X POST -H "Content-Type: application/json" -d '{"text":"Upload completed"}' "$WEBHOOK_URL" >/dev/null || true

# 12 -- Print summary
echo -e "Upload Summary:"

for ip in "${!upload_results[@]}"; do
  status="${upload_results[$ip]}"
  [ "$status" = "ok" ] && echo -e "[${GREEN}✔${NC}] $ip" || echo -e "[${RED}✘${NC}] $ip - $status"
done

[ "$VERBOSE" = true ] && echo -e "📄 Log saved to: ${YELLOW}$LOG_FILE${NC}"

echo -e "${GREEN}All uploads completed!${NC}"