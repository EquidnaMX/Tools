#!/bin/bash
set -uo pipefail

# Colors
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Usage
print_usage(){
  cat <<EOF
Usage:
  $0 <remote_user> <network_spec> [--command "cmd"] [--script /path/to/script.sh]
      [--max_parallel N] [--key /path/to/private_key] [--email you@example.com]
      [--retry N] [--save_logs] [--webhook URL]...
EOF
}

# Parse arguments
if [ $# -lt 2 ]; then print_usage; exit 1; fi
REMOTE_USER=$1; NETWORK_SPEC=$2; shift 2

SSH_COMMAND=""; SCRIPT_FILE=""; PRIVATE_KEY=""; EMAIL=""
MAX_PARALLEL=10; RETRY_TIMES=0; SAVE_LOGS=false; WEBHOOKS=()

while (( $# )); do
  case $1 in
    --command)       SSH_COMMAND=$2; shift 2 ;;
    --script)        SCRIPT_FILE=$2; shift 2 ;;
    --key)           PRIVATE_KEY=$2; shift 2 ;;
    --email)         EMAIL=$2; shift 2 ;;
    --max_parallel)  MAX_PARALLEL=$2; shift 2 ;;
    --retry)         RETRY_TIMES=$2; shift 2 ;;
    --save_logs)     SAVE_LOGS=true; shift ;;
    --webhook)       WEBHOOKS+=("$2"); shift 2 ;;
    *) echo "Unknown option: $1"; print_usage; exit 1 ;;
  esac
done

if [[ -z $SSH_COMMAND && -z $SCRIPT_FILE ]]; then
  echo "Error: must specify --command or --script."; print_usage; exit 1
fi

# SSH options
SSH_OPTIONS="-o ConnectTimeout=3 -o StrictHostKeyChecking=no \
-o UserKnownHostsFile=/dev/null -o ServerAliveInterval=3 -o ServerAliveCountMax=1"
[[ -n $PRIVATE_KEY ]] && SSH_OPTIONS+=" -i $PRIVATE_KEY"

timestamp=$(date +%Y%m%d_%H%M%S)
csv_file="ssh_results_${timestamp}.csv"
html_file="ssh_results_${timestamp}.html"
log_dir="logs_${timestamp}"

declare -A RESULTS TIMES
alive_hosts=() final_hosts=()

# Password if no key
if [[ -z $PRIVATE_KEY ]]; then
  read -s -p "Enter SSH password: " SSHPASS; echo
  export SSHPASS
fi

# IP list
cidr2ips(){
  local cidr=$1; IFS=/ read ip mask <<<"$cidr"
  IFS=. read -r a b c d <<<"$ip"
  local ipd=$((a<<24|b<<16|c<<8|d))
  local m=$((0xFFFFFFFF<< (32-mask) & 0xFFFFFFFF))
  local net=$((ipd & m)); local bc=$((net|(~m&0xFFFFFFFF)))
  for ((i=net+1; i<bc; i++)); do
    alive_hosts+=("$((i>>24&0xFF)).$((i>>16&0xFF)).$((i>>8&0xFF)).$((i&0xFF))")
  done
}
parse_ips(){
  if [[ $NETWORK_SPEC == */* ]]; then
    cidr2ips "$NETWORK_SPEC"
  elif [[ $NETWORK_SPEC == *-* ]]; then
    IFS=- read -r s e <<<"$NETWORK_SPEC"
    base=${s%.*}.; start=${s##*.}; end=${e##*.}
    for ((i=start; i<=end; i++)); do alive_hosts+=("${base}${i}"); done
  else
    echo "Invalid network spec"; exit 1
  fi
}

# Webhook helper
send_webhooks(){
  for url in "${WEBHOOKS[@]}"; do
    curl -s -X POST -H "Content-Type: application/json" \
      -d "{\"status\":\"$1\",\"info\":\"$2\"}" "$url" &>/dev/null
  done
}

# SSH execution
execute_on_host(){
  local IP=$1 tries=0
  while :; do
    local start=$(date +%s)
    if [[ -n $SCRIPT_FILE ]]; then
      output=$(sshpass -e ssh $SSH_OPTIONS "$REMOTE_USER@$IP" 'bash -s' <"$SCRIPT_FILE" 2>&1)
    else
      output=$(sshpass -e ssh $SSH_OPTIONS "$REMOTE_USER@$IP" "$SSH_COMMAND" 2>&1)
    fi
    local status=$?; local end=$(date +%s)
    TIMES["$IP"]=$((end-start))

    if grep -qE "Permission denied|Authentication failed|Host key verification failed" <<<"$output"; then
      RESULTS["$IP"]="Auth Failed"
      $SAVE_LOGS && { mkdir -p "$log_dir"; echo "$output" >"$log_dir/$IP.log"; }
      echo -e "[${IP}] ${YELLOW}⚠️ Auth Failed${NC}"
      break
    fi

    if (( status==0 )); then
      RESULTS["$IP"]="Success"
      $SAVE_LOGS && { mkdir -p "$log_dir"; echo "$output" >"$log_dir/$IP.log"; }
      echo -e "[${IP}] ${GREEN}✅ Success${NC}"
      break
    else
      ((tries++))
      if (( tries>RETRY_TIMES )); then
        RESULTS["$IP"]="Failed"
        $SAVE_LOGS && { mkdir -p "$log_dir"; echo "$output" >"$log_dir/$IP.log"; }
        echo -e "[${IP}] ${RED}❌ Failed after $RETRY_TIMES retries${NC}"
        break
      else
        echo "[${IP}] Retry $tries/$RETRY_TIMES..."
      fi
    fi
  done
}

### MAIN ###
send_webhooks "start" "SSH run started"
parse_ips

# Alive scan with spinner
echo -n "🔍 Scanning alive hosts... "
spinner=( '|' '/' '-' '\\' )
spin_pid=""
spin() {
  while :; do
    for c in "${spinner[@]}"; do
      printf "\\r🔍 Scanning alive hosts... %s" "$c"
      sleep 0.1
    done
  done
}
spin & spin_pid=$!

for ip in "${alive_hosts[@]}"; do
  ping -c1 -W1 "$ip" &>/dev/null && final_hosts+=("$ip")
done

kill "$spin_pid" 2>/dev/null
wait "$spin_pid" 2>/dev/null || true
echo -e "\\r✅ Found ${#final_hosts[@]} alive hosts.          "

# Launch SSH jobs
pids=()
for ip in "${final_hosts[@]}"; do
  RESULTS["$ip"]="Pending"
  execute_on_host "$ip" & pids+=($!)
  if (( ${#pids[@]} >= MAX_PARALLEL )); then
    wait "${pids[@]}" || true
    pids=()
  fi
done

# Final wait for leftover jobs
if (( ${#pids[@]} > 0 )); then
  wait "${pids[@]}" || true
fi

echo -e "\n🎯 Execution complete!"

# Save CSV and HTML
echo "Host,Status,Time(s)" >"$csv_file"
{
  echo "<html><body><h2>SSH Results</h2><table border=1>"
  echo "<tr><th>Host</th><th>Status</th><th>Time(s)</th></tr>"
  for ip in "${final_hosts[@]}"; do
    color="black"
    [[ ${RESULTS[$ip]} == "Success" ]] && color="green"
    [[ ${RESULTS[$ip]} == "Auth Failed" ]] && color="orange"
    [[ ${RESULTS[$ip]} == "Failed" ]] && color="red"
    echo "<tr><td>$ip</td><td style='color:$color'>${RESULTS[$ip]}</td><td>${TIMES[$ip]:-0}</td></tr>"
    echo "$ip,${RESULTS[$ip]},${TIMES[$ip]:-0}" >>"$csv_file"
  done
  echo "</table></body></html>"
} >"$html_file"

# Super summary
success=0; authfail=0; failed=0
for st in "${RESULTS[@]}"; do
  [[ $st == "Success" ]] && ((success++))
  [[ $st == "Auth Failed" ]] && ((authfail++))
  [[ $st == "Failed" ]] && ((failed++))
done

echo -e "${CYAN}═══════════════════════"
echo    "      Final Summary     "
echo -e "═══════════════════════${NC}"
echo -e "✅ Success: ${GREEN}$success${NC}"
echo -e "⚠️  Auth Failed: ${YELLOW}$authfail${NC}"
echo -e "❌ Failed: ${RED}$failed${NC}"
echo -e "${CYAN}═══════════════════════${NC}"

# Email if configured
if [[ -n $EMAIL ]]; then
  {
    echo "Subject: SSH Execution Report"
    echo "MIME-Version: 1.0"
    echo "Content-Type: multipart/mixed; boundary=\"BND\""
    echo "--BND"; echo "Content-Type: text/html"; echo; cat "$html_file"
    echo "--BND"; echo "Content-Type: text/csv; name=\"$(basename "$csv_file")\""
    echo "Content-Disposition: attachment; filename=\"$(basename "$csv_file")\""; echo; cat "$csv_file"
    echo "--BND--"
  } | sendmail "$EMAIL"
fi

send_webhooks "completed" "SSH run completed"

echo
echo "📄 CSV saved: $csv_file"
echo "🌐 HTML saved: $html_file"
$SAVE_LOGS && echo "📝 Logs saved in: $log_dir/"
