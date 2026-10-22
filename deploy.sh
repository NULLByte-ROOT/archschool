#!/usr/bin/env bash
set -Eeuo pipefail

# =============================================================================
#  ArchSchool deployment manager — blue-green
#
#  Two identical slots ("blue" and "green") can run side by side. A deploy
#  builds and starts the *inactive* slot, waits until it is genuinely healthy,
#  verifies it end-to-end, and only then flips the host Nginx upstream. The old
#  slot keeps running through a soak window so a bad release can be reverted by
#  flipping the upstream back.
#
#  Traffic switch: /etc/nginx/conf.d/00-archschool-upstream.conf
#    blue  -> 127.0.0.1:6241
#    green -> 127.0.0.1:6242
#
#  The database and the uploads volume are shared by both slots on purpose.
#  Schema changes must therefore stay backward compatible (expand/contract),
#  because the previous slot keeps serving for a short time and may be
#  restarted for a rollback.
#
#  Usage:
#    ./deploy.sh                 interactive menu
#    ./deploy.sh deploy          pull + build + start + verify + switch + soak
#    ./deploy.sh rollback        switch back to the previous slot
#    ./deploy.sh cleanup         remove the inactive slot's containers/images
#    ./deploy.sh status          slot/traffic overview
#    ./deploy.sh setup           first-time setup on a new server
#    ./deploy.sh backup          database + uploads + .env -> one .tar.gz
#    ./deploy.sh restore FILE    restore that archive on a fresh server
#    ./deploy.sh start|stop|restart|logs
#
#  Flags: --yes --skip-pull --soak=N --no-soak --keep-old --timeout=N
#         --backup --out=DIR
# =============================================================================

PROJECT_NAME="archschool"
BRANCH="${BRANCH:-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/backend/.env"
DB_URL="postgresql://postgres:postgres@archschool_db:5432/archschool_db"
PRODUCTION_DOMAIN="${PRODUCTION_DOMAIN:-archschool.vidxsepehr.ir}"
STATE_FILE="${SCRIPT_DIR}/.deploy-state"

SLOT_BLUE_PORT=6241
SLOT_GREEN_PORT=6242
UPSTREAM_NAME="archschool_app"
NGINX_UPSTREAM_CONF="${NGINX_UPSTREAM_CONF:-/etc/nginx/conf.d/00-archschool-upstream.conf}"
NGINX_SITE_CONF="${NGINX_SITE_CONF:-}"

# WebSocket (chat) forwarding. The host proxy must upgrade the connection for
# /api/ws, otherwise browsers report
#   "WebSocket is closed before the connection is established".
# deploy.sh inserts this block into every proxying `location` of the site file.
NGINX_WS_MARKER_BEGIN="# BEGIN archschool-websocket (managed by deploy.sh)"
NGINX_WS_MARKER_END="# END archschool-websocket (managed by deploy.sh)"
WS_PROBE_TIMEOUT="${WS_PROBE_TIMEOUT:-12}"

# Backup / restore
DB_CONTAINER="archschool_db"
DB_NAME="archschool_db"
DB_USER="postgres"
UPLOADS_VOLUME="archschool_uploads"
# Any image already on the server that ships tar+sh (the database image is
# guaranteed to exist, so a restore never needs to pull anything).
HELPER_IMAGE="${HELPER_IMAGE:-postgres:17-alpine}"
BACKUP_PREFIX="archschool_backup"
BACKUP_OUT_DIR="${BACKUP_OUT_DIR:-}"
BACKUP_BEFORE_DEPLOY=0
RESTORE_FILE=""

GIT_SHA="${GIT_SHA:-unknown}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SOAK_SECONDS="${SOAK_SECONDS:-60}"
SOAK_INTERVAL="${SOAK_INTERVAL:-5}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
PUBLIC_TIMEOUT="${PUBLIC_TIMEOUT:-10}"

COMMAND=""
ASSUME_YES=0
SKIP_PULL=0
KEEP_OLD=0
EDGE_MODE=1
PROBE_MODE="local"
PROBE_PORT="${SLOT_BLUE_PORT}"

cd "${SCRIPT_DIR}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { printf "${BLUE}[INFO]${NC} %s\n" "$*"; }
success() { printf "${GREEN}[ OK ]${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}[WARN]${NC} %s\n" "$*"; }
error()   { printf "${RED}[FAIL]${NC} %s\n" "$*" >&2; }
plain()   { printf "%s\n" "$*"; }

# ---------------------------------------------------------------- plumbing --

run_privileged() {
    if [[ ${EUID} -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

run_git() {
    if [[ ${EUID} -eq 0 && -n "${SUDO_USER:-}" ]]; then
        sudo -u "${SUDO_USER}" -H git "$@"
    else
        git "$@"
    fi
}

# Compose interpolation happens in the CLI process, so the image tag must be
# passed explicitly — sudo resets the environment.
compose() {
    run_privileged env \
        IMAGE_TAG="${IMAGE_TAG}" \
        GIT_SHA="${GIT_SHA}" \
        docker compose -p "${PROJECT_NAME}" "$@"
}

slot_compose() {
    local slot="$1"
    shift
    compose --profile "${slot}" "$@"
}

all_compose() {
    compose --profile blue --profile green "$@"
}

check_sudo() {
    if [[ ${EUID} -eq 0 ]]; then
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        error "sudo is required. Re-run this script as root or install sudo."
        exit 1
    fi
    if ! sudo -v; then
        error "Unable to obtain sudo privileges."
        exit 1
    fi
}

slot_port() {
    case "$1" in
        blue)  printf '%s' "${SLOT_BLUE_PORT}" ;;
        green) printf '%s' "${SLOT_GREEN_PORT}" ;;
        *) return 1 ;;
    esac
}

slot_other() {
    if [[ "$1" == "blue" ]]; then printf 'green'; else printf 'blue'; fi
}

slot_frontend() { printf 'archschool_frontend_%s' "$1"; }
slot_backend()  { printf 'archschool_backend_%s' "$1"; }

port_to_slot() {
    case "$1" in
        "${SLOT_BLUE_PORT}")  printf 'blue' ;;
        "${SLOT_GREEN_PORT}") printf 'green' ;;
        *) return 1 ;;
    esac
}

container_exists() {
    run_privileged docker inspect "$1" >/dev/null 2>&1
}

container_state() {
    run_privileged docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null || true
}

container_health() {
    local value
    value="$(run_privileged docker inspect \
        -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$1" 2>/dev/null || true)"
    printf '%s' "${value:-missing}"
}

container_revision() {
    local value
    value="$(run_privileged docker inspect \
        -f '{{index .Config.Labels "archschool.revision"}}' \
        "$1" 2>/dev/null || true)"
    printf '%s' "${value:-}"
}

container_running() {
    [[ "$(container_state "$1")" == "running" ]]
}

legacy_exists() {
    container_exists "archschool_frontend" || container_exists "archschool_backend"
}

state_get() {
    [[ -f "${STATE_FILE}" ]] || return 0
    awk -F= -v key="$1" '$1==key { sub(/^[^=]*=/, ""); print; exit }' "${STATE_FILE}"
}

# ------------------------------------------------------------- host nginx ---

nginx_present() { command -v nginx >/dev/null 2>&1; }

nginx_test() { run_privileged nginx -t >/dev/null 2>&1; }

nginx_reload() {
    if command -v systemctl >/dev/null 2>&1 \
        && run_privileged systemctl is-active --quiet nginx 2>/dev/null; then
        run_privileged systemctl reload nginx
    else
        run_privileged nginx -s reload
    fi
}

# A reload only re-reads the config for *new* worker processes: the old workers
# keep serving their keep-alive/WebSocket connections, so a switched upstream
# can look "not applied" for a while. Blue-green switching therefore restarts
# the master process, which tears down every old connection and forces fresh
# ones against the new slot.
nginx_restart() {
    if command -v systemctl >/dev/null 2>&1 \
        && run_privileged systemctl is-active --quiet nginx 2>/dev/null; then
        run_privileged systemctl restart nginx
    else
        nginx_reload
    fi
}

# Waits (up to ~15s) until the restarted master is active again, so the very
# next probe cannot race the restart.
wait_nginx_active() {
    local i=0
    if ! command -v systemctl >/dev/null 2>&1; then
        sleep 1
        return 0
    fi
    while (( i < 30 )); do
        if run_privileged systemctl is-active --quiet nginx 2>/dev/null; then
            return 0
        fi
        sleep 0.5
        i=$((i + 1))
    done
    return 1
}

read_upstream_port() {
    [[ -n "${NGINX_UPSTREAM_CONF}" ]] || return 0
    run_privileged grep -oE 'server[[:space:]]+127\.0\.0\.1:[0-9]+' \
        "${NGINX_UPSTREAM_CONF}" 2>/dev/null \
        | head -n1 | grep -oE '[0-9]+$' || true
}

write_upstream() {
    local port="$1" tmp dir
    dir="$(dirname "${NGINX_UPSTREAM_CONF}")"
    run_privileged mkdir -p "${dir}"

    tmp="$(mktemp)"
    cat > "${tmp}" <<EOF
# Managed by ArchSchool deploy.sh — do not edit by hand.
# Points host Nginx at the active blue-green slot:
#   6241 = blue, 6242 = green.
upstream ${UPSTREAM_NAME} {
    server 127.0.0.1:${port};
}
EOF
    # Write to a sibling file, then rename: atomic for nginx.
    run_privileged install -m 0644 "${tmp}" "${NGINX_UPSTREAM_CONF}.new"
    run_privileged mv -f "${NGINX_UPSTREAM_CONF}.new" "${NGINX_UPSTREAM_CONF}"
    rm -f "${tmp}"
}

restore_upstream() {
    local previous="$1" backup="$2"
    if [[ -n "${backup}" && -f "${backup}" ]]; then
        run_privileged cp -p "${backup}" "${NGINX_UPSTREAM_CONF}"
        rm -f "${backup}"
    elif [[ -n "${previous}" ]]; then
        write_upstream "${previous}"
    fi
    if nginx_test; then
        if nginx_restart; then
            wait_nginx_active || warn "Host Nginx did not report 'active' after the restart."
        else
            warn "Could not restart Nginx while restoring the previous upstream."
        fi
    else
        warn "Nginx configuration is invalid after the restore attempt."
    fi
}

detect_nginx_site_conf() {
    local candidate resolved
    local -a candidates=()
    if [[ -n "${NGINX_SITE_CONF}" ]]; then
        candidates+=("${NGINX_SITE_CONF}")
    fi
    candidates+=(
        /etc/nginx/sites-available/archschool
        /etc/nginx/sites-enabled/archschool
        /etc/nginx/conf.d/archschool.conf
    )
    for candidate in "${candidates[@]}"; do
        if run_privileged test -f "${candidate}"; then
            # Always edit the real file: `sed -i` on a symlink would replace
            # the link with a regular file and silently unhook sites-enabled.
            resolved="$(run_privileged readlink -f "${candidate}" 2>/dev/null || true)"
            printf '%s' "${resolved:-${candidate}}"
            return 0
        fi
    done
    return 1
}

# ------------------------------------------------- host nginx websockets ---
#
# Without these three directives the host proxy downgrades the request to
# HTTP/1.0 and drops `Upgrade`, so /api/ws never reaches the app as a
# WebSocket: browsers abort with "WebSocket is closed before the connection is
# established" and the chat stops receiving messages.

write_ws_block() {
    local out="$1"
    cat > "${out}" <<EOF
    ${NGINX_WS_MARKER_BEGIN}
    # Chat socket (wss://<domain>/api/ws). Keep this block inside the proxying
    # location; deploy.sh re-adds it after every pull.
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
    proxy_send_timeout 86400;
    proxy_buffering off;
    ${NGINX_WS_MARKER_END}
EOF
}

# Rewrites an nginx config: drops a stale managed block and inserts a fresh one
# into every `location` block that proxies, unless that block already upgrades.
patch_nginx_ws() {
    local src="$1" blockfile="$2"
    awk -v blockfile="${blockfile}" \
        -v mbegin="${NGINX_WS_MARKER_BEGIN}" \
        -v mend="${NGINX_WS_MARKER_END}" '
    function braces(s, wanted,   i, ch, c) {
        c = 0
        for (i = 1; i <= length(s); i++) {
            ch = substr(s, i, 1)
            if (ch == wanted) c++
        }
        return c
    }
    function emit(   i) {
        # The block goes *last* inside the location: nginx keeps the last value
        # for a repeated proxy_set_header, so this also overrides a stale
        # `Connection ""` or a shorter proxy_read_timeout.
        if (hasproxy && !(hasup && hasconn && hashttp)) {
            for (i = 1; i < n; i++) print buf[i]
            printf "%s", blk
            print buf[n]
        } else {
            for (i = 1; i <= n; i++) print buf[i]
        }
    }
    BEGIN {
        blk = ""
        while ((getline line < blockfile) > 0) blk = blk line "\n"
        close(blockfile)
        inmanaged = 0
        inloc = 0
    }
    {
        if (index($0, mbegin) > 0) { inmanaged = 1; next }
        if (inmanaged) { if (index($0, mend) > 0) inmanaged = 0; next }

        if (!inloc && $0 ~ /^[ \t]*location[ \t]/ && index($0, "{")) {
            inloc = 1; depth = 0; n = 0
            hasproxy = 0; hasup = 0; hasconn = 0; hashttp = 0
        }
        if (inloc) {
            n++; buf[n] = $0
            if ($0 ~ /proxy_pass/) hasproxy = 1
            if (tolower($0) ~ /proxy_set_header[ \t]+upgrade[ \t]+"?\$http_upgrade/) hasup = 1
            if (tolower($0) ~ /proxy_set_header[ \t]+connection[ \t]+"?(upgrade|\$connection_upgrade)/) hasconn = 1
            if ($0 ~ /proxy_http_version/) hashttp = 1
            depth += braces($0, "{") - braces($0, "}")
            if (depth <= 0) { emit(); inloc = 0 }
            next
        }
        print
    }
    END { if (inloc) for (i = 1; i <= n; i++) print buf[i] }
    ' "${src}"
}

host_ws_ok() {
    local conf="$1"
    run_privileged grep -qiE 'proxy_set_header[[:space:]]+Upgrade[[:space:]]+"?\$http_upgrade' "${conf}" 2>/dev/null \
        && run_privileged grep -qiE 'proxy_set_header[[:space:]]+Connection[[:space:]]+"?(upgrade|\$connection_upgrade)' "${conf}" 2>/dev/null \
        && run_privileged grep -qE 'proxy_http_version[[:space:]]+1\.1' "${conf}" 2>/dev/null
}

print_ws_manual() {
    local conf="$1"
    plain ""
    plain "Add this inside the 'location /' block of ${conf}:"
    plain "    proxy_http_version 1.1;"
    plain "    proxy_set_header Upgrade \$http_upgrade;"
    plain "    proxy_set_header Connection \"upgrade\";"
    plain "    proxy_read_timeout 86400;"
    plain "Then: sudo nginx -t && sudo systemctl reload nginx"
    plain ""
}

# Idempotent: patches the host site config so /api/ws is upgraded end to end.
ensure_host_ws() {
    local conf="${1:-${NGINX_SITE_CONF}}"
    local src tmp block backup

    if [[ -z "${conf}" ]]; then
        conf="$(detect_nginx_site_conf 2>/dev/null || true)"
    fi
    if [[ -z "${conf}" ]] || ! run_privileged test -f "${conf}"; then
        warn "Could not locate the host Nginx site config; skipping the WebSocket check."
        return 0
    fi
    NGINX_SITE_CONF="${conf}"

    # Patch per location, not per file. Header detection is what decides, never
    # a comment tag: `patch_nginx_ws` leaves locations that already upgrade
    # byte-for-byte untouched and only adds the block to proxying locations
    # that lack it. A file that is already correct produces an identical copy
    # and is never written.
    #
    # Per-location matters because `location /` upgrading does not help if a
    # more specific `location ^~ /api/` also proxies: /api/ws then takes that
    # branch, arrives at FastAPI as a plain HTTP GET and answers 404.

    src="$(mktemp)"
    tmp="$(mktemp)"
    block="$(mktemp)"

    run_privileged cat "${conf}" > "${src}"
    write_ws_block "${block}"
    patch_nginx_ws "${src}" "${block}" > "${tmp}"

    # Unusual layout (`location /` and `{` on separate lines): fall back to
    # inserting the block right before the first proxy_pass at the same depth.
    if ! host_ws_ok "${tmp}"; then
        awk -v blockfile="${block}" '
            BEGIN {
                blk = ""
                while ((getline l < blockfile) > 0) blk = blk l "\n"
                close(blockfile)
                done = 0
            }
            {
                if (!done && $0 ~ /proxy_pass/) { printf "%s", blk; done = 1 }
                print
            }
        ' "${tmp}" > "${tmp}.fb" && mv -f "${tmp}.fb" "${tmp}"
    fi

    if cmp -s "${src}" "${tmp}"; then
        rm -f "${src}" "${tmp}" "${block}"
        if host_ws_ok "${conf}"; then
            success "Host Nginx already upgrades WebSocket connections."
            return 0
        fi
        # Not fatal: the deploy must not be blocked by a proxy quirk. The
        # post-switch WebSocket probe reports the real state.
        warn "No proxying 'location' block could be patched automatically."
        print_ws_manual "${conf}"
        return 0
    fi

    backup="${conf}.bak.$(date +%Y%m%d%H%M%S)"
    info "Adding the WebSocket upgrade block to ${conf}..."
    run_privileged cp -p "${conf}" "${backup}"
    run_privileged cp "${tmp}" "${conf}.new"
    run_privileged chmod 644 "${conf}.new"
    run_privileged mv -f "${conf}.new" "${conf}"
    rm -f "${src}" "${tmp}" "${block}"

    if ! nginx_test; then
        run_privileged cp -p "${backup}" "${conf}"
        nginx_test || true
        error "nginx -t rejected the WebSocket patch; ${conf} was restored from ${backup}."
        print_ws_manual "${conf}"
        return 1
    fi
    # Restart (not reload): the workers that predate the patch must not keep
    # serving /api/ws without the upgrade headers.
    if ! nginx_restart; then
        run_privileged cp -p "${backup}" "${conf}"
        nginx_restart || true
        error "Nginx restart failed; ${conf} was restored from ${backup}."
        return 1
    fi
    wait_nginx_active || warn "Host Nginx did not report 'active' within 15s after the restart."

    success "WebSocket upgrade enabled in ${conf} (backup: ${backup})."
    return 0
}

# A wrong host config answers 404/400/502 here instead of upgrading, so the
# probe accepts only responses that prove the request reached the WS route.
#
# `--http1.1` is mandatory: WebSocket upgrades do not exist in HTTP/2, and over
# h2 curl/nginx silently drop `Connection: Upgrade`, so the request reaches
# FastAPI as a plain GET and answers 404 — a probe-only false negative.
public_ws_code() {
    curl -s -o /dev/null -w '%{http_code}' --max-time "${WS_PROBE_TIMEOUT}" \
        --http1.1 \
        --resolve "${PRODUCTION_DOMAIN}:443:127.0.0.1" \
        -H 'Connection: Upgrade' \
        -H 'Upgrade: websocket' \
        -H 'Sec-WebSocket-Version: 13' \
        -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
        "https://${PRODUCTION_DOMAIN}/api/ws?token=invalid&room=global" 2>/dev/null || true
}

verify_public_ws() {
    local code
    code="$(public_ws_code)"
    case "${code}" in
        # 101 = upgraded; 400/401/403/426 = the upgrade reached FastAPI, which
        # then rejected the dummy token/room. All prove the proxy path works.
        101|400|401|403|426)
            success "Public WebSocket endpoint upgrades correctly (HTTP ${code})."
            return 0
            ;;
    esac
    error "Public WebSocket endpoint did not upgrade (HTTP ${code:-no response})."
    if [[ "${code}" == "404" ]]; then
        error "404 on /api/ws means FastAPI saw a plain HTTP GET, not an upgrade:"
        error "the location that matches /api/ws is not forwarding Upgrade/Connection."
    elif [[ "${code}" == "502" || "${code}" == "503" || "${code}" == "504" ]]; then
        error "The proxy reached Nginx but the upstream slot is not answering."
    fi
    error "wss://${PRODUCTION_DOMAIN}/api/ws is broken for browsers."
    print_ws_manual "${NGINX_SITE_CONF:-/etc/nginx/sites-available/archschool}"
    return 1
}

check_public_ws() {
    if [[ "${EDGE_MODE}" != "1" ]]; then
        return 0
    fi
    if ! public_health >/dev/null 2>&1; then
        warn "Skipping the public WebSocket probe (${PRODUCTION_DOMAIN} is not answering locally)."
        return 0
    fi
    verify_public_ws
}


# One-time, idempotent, reversible: route the existing site through the
# managed upstream so traffic can be switched without touching it again.
ensure_edge() {
    local conf current_port backup
    EDGE_MODE=1

    if ! nginx_present; then
        warn "Host Nginx not detected — blue-green switching is unavailable."
        EDGE_MODE=0
        return 0
    fi

    if ! conf="$(detect_nginx_site_conf)"; then
        error "Could not locate the ArchSchool Nginx site config."
        error "Set it explicitly, e.g.: sudo NGINX_SITE_CONF=/etc/nginx/sites-available/archschool ./deploy.sh deploy"
        return 1
    fi
    NGINX_SITE_CONF="${conf}"
    info "Host Nginx site config: ${conf}"

    if [[ -z "$(read_upstream_port)" ]]; then
        current_port="$(detect_active_port || true)"
        current_port="${current_port:-${SLOT_BLUE_PORT}}"
        write_upstream "${current_port}"
        success "Created ${NGINX_UPSTREAM_CONF} -> 127.0.0.1:${current_port}"
    fi

    # Chat sockets must be upgraded by the host proxy too (see ensure_host_ws).
    ensure_host_ws "${conf}" || return 1

    # Any literal slot port must go through the managed upstream, otherwise
    # `switch_traffic` writes the upstream file and nginx happily keeps serving
    # the *old* slot from the hardcoded proxy_pass. Check both ports, not just
    # blue: a config edited by hand may point at either one.
    local literal_re="proxy_pass[[:space:]]+http://127\\.0\\.0\\.1:(${SLOT_BLUE_PORT}|${SLOT_GREEN_PORT})/?;"

    if ! run_privileged grep -qE "${literal_re}" "${conf}"; then
        if run_privileged grep -qE "proxy_pass[[:space:]]+http://${UPSTREAM_NAME}([;/]|$)" "${conf}"; then
            success "Site config already routes through the ${UPSTREAM_NAME} upstream."
            return 0
        fi
        error "Cannot find a '${UPSTREAM_NAME}' upstream or a literal '127.0.0.1:${SLOT_BLUE_PORT}' proxy_pass in ${conf}."
        error "Blue-green switching needs the proxying 'location' blocks to use the '${UPSTREAM_NAME}' upstream."
        plain ""
        plain "Apply this change manually, then re-run:"
        plain "  - proxy_pass http://127.0.0.1:${SLOT_BLUE_PORT};"
        plain "  + proxy_pass http://${UPSTREAM_NAME};"
        plain ""
        plain "(The upstream itself is managed in ${NGINX_UPSTREAM_CONF}.)"
        return 1
    fi

    backup="${conf}.bak.$(date +%Y%m%d%H%M%S)"
    run_privileged cp -p "${conf}" "${backup}"
    info "Backup written to ${backup}"

    info "Routing every literal slot proxy_pass through the '${UPSTREAM_NAME}' upstream..."
    run_privileged sed -i -E \
        "s#${literal_re}#proxy_pass http://${UPSTREAM_NAME};#g" \
        "${conf}"

    if run_privileged grep -qE "${literal_re}" "${conf}"; then
        run_privileged cp -p "${backup}" "${conf}"
        error "Some proxy_pass lines still point at a literal slot port; the original config was restored."
        return 1
    fi

    if ! nginx_test; then
        run_privileged cp -p "${backup}" "${conf}"
        error "nginx -t rejected the patched config; the original config was restored. Nothing was reloaded."
        return 1
    fi

    if ! nginx_restart; then
        run_privileged cp -p "${backup}" "${conf}"
        nginx_restart || true
        error "Nginx restart failed; the original config was restored."
        return 1
    fi
    wait_nginx_active || warn "Host Nginx did not report 'active' after the restart."

    success "Host Nginx now routes through '${UPSTREAM_NAME}' (traffic unchanged)."
}

switch_traffic() {
    local port="$1" previous backup
    previous="$(read_upstream_port)"

    if [[ "${EDGE_MODE}" != "1" ]]; then
        warn "Host Nginx switching is disabled; skipping the traffic switch."
        return 0
    fi

    if [[ "${previous}" == "${port}" ]]; then
        success "Host Nginx already points at 127.0.0.1:${port}."
        return 0
    fi

    backup=""
    if run_privileged test -f "${NGINX_UPSTREAM_CONF}"; then
        backup="$(mktemp)"
        run_privileged cp -p "${NGINX_UPSTREAM_CONF}" "${backup}"
    fi

    info "Switching host Nginx upstream to 127.0.0.1:${port}..."
    write_upstream "${port}"

    if ! nginx_test; then
        error "nginx -t rejected the new upstream; traffic was NOT switched."
        restore_upstream "${previous}" "${backup}"
        return 1
    fi

    # Restart, not reload: a reload leaves the old worker processes (and their
    # keep-alive/WebSocket connections to the previous slot) alive, which both
    # delays the switch and keeps chat sockets pinned to the dead slot.
    if ! nginx_restart; then
        error "Nginx restart failed; traffic was NOT switched."
        restore_upstream "${previous}" "${backup}"
        return 1
    fi
    if ! wait_nginx_active; then
        warn "Host Nginx has not reported 'active' yet; probes will retry."
    fi

    if [[ "$(read_upstream_port)" != "${port}" ]]; then
        error "${NGINX_UPSTREAM_CONF} does not point at 127.0.0.1:${port} after the switch."
        restore_upstream "${previous}" "${backup}"
        return 1
    fi

    [[ -n "${backup}" ]] && rm -f "${backup}"
    success "Traffic now points at 127.0.0.1:${port}."
}

# ------------------------------------------------------------ slot helpers --

detect_active_port() {
    local port
    port="$(read_upstream_port)"
    if [[ -n "${port}" ]]; then
        printf '%s' "${port}"
        return 0
    fi
    if container_running "$(slot_frontend blue)"; then
        printf '%s' "${SLOT_BLUE_PORT}"
        return 0
    fi
    if container_running "$(slot_frontend green)"; then
        printf '%s' "${SLOT_GREEN_PORT}"
        return 0
    fi
    if container_running "archschool_frontend"; then
        printf '%s' "${SLOT_BLUE_PORT}"
        return 0
    fi
    return 1
}

detect_active_slot() {
    local port
    if ! port="$(detect_active_port)"; then
        printf 'none'
        return 0
    fi
    port_to_slot "${port}" || printf 'none'
}

choose_target_slot() {
    case "$1" in
        blue)  printf 'green' ;;
        green) printf 'blue' ;;
        *)     if legacy_exists; then printf 'green'; else printf 'blue'; fi ;;
    esac
}

guard_port_free() {
    local slot="$1" port owner
    port="$(slot_port "${slot}")"
    owner="$(run_privileged docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null \
        | grep -F ":${port}->" | awk '{print $1}' | head -n1 || true)"
    if [[ -n "${owner}" && "${owner}" != "$(slot_frontend "${slot}")" ]]; then
        error "Port ${port} is already published by container '${owner}'."
        if [[ "${owner}" == "archschool_frontend" ]]; then
            error "That is a pre-blue-green container. It will be removed after the next successful switch,"
            error "or remove it now: docker rm -f ${owner}"
        fi
        return 1
    fi
}

wait_container_healthy() {
    local name="$1" deadline health
    deadline=$((SECONDS + HEALTH_TIMEOUT))

    while (( SECONDS < deadline )); do
        health="$(container_health "${name}")"
        case "${health}" in
            healthy)
                printf '\n'
                success "${name} is healthy."
                return 0
                ;;
            unhealthy|exited|dead|missing)
                printf '\n'
                error "${name} is '${health}'. Recent logs:"
                run_privileged docker logs --tail=40 "${name}" 2>&1 | sed 's/^/    /' || true
                return 1
                ;;
        esac
        printf '.'
        sleep 2
    done

    printf '\n'
    error "Timed out after ${HEALTH_TIMEOUT}s waiting for ${name} (state: ${health:-unknown})."
    return 1
}

wait_slot_healthy() {
    local slot="$1"
    info "Waiting for the ${slot} backend to become healthy (timeout ${HEALTH_TIMEOUT}s)..."
    wait_container_healthy "$(slot_backend "${slot}")" || return 1
    info "Waiting for the ${slot} frontend to become healthy..."
    wait_container_healthy "$(slot_frontend "${slot}")" || return 1
}

slot_smoke() {
    local slot="$1" port base failed=0 version ws_code body
    port="$(slot_port "${slot}")"
    base="http://127.0.0.1:${port}"

    info "Smoke-testing the ${slot} slot on ${base} ..."

    if ! curl -fsS --max-time 10 "${base}/healthz" >/dev/null 2>&1; then
        error "  [${slot}] /healthz failed (frontend container is not serving)."
        failed=1
    else
        success "  [${slot}] static frontend responds."
    fi

    if version="$(curl -fsS --max-time 10 "${base}/version" 2>/dev/null)"; then
        version="${version//[[:space:]]/}"
        if [[ "${version}" != "${GIT_SHA}" ]]; then
            error "  [${slot}] /version is '${version}', expected '${GIT_SHA}'."
            failed=1
        else
            success "  [${slot}] build revision ${version} is live in the image."
        fi
    else
        error "  [${slot}] /version is unreachable."
        failed=1
    fi

    if body="$(curl -fsS --max-time 15 "${base}/api/health" 2>/dev/null)"; then
        if ! grep -q '"status":"ok"' <<<"${body}"; then
            error "  [${slot}] /api/health is not ok: ${body}"
            failed=1
        elif ! grep -qF "\"revision\":\"${GIT_SHA}\"" <<<"${body}"; then
            warn "  [${slot}] backend reports a different revision: ${body}"
        else
            success "  [${slot}] frontend -> backend -> database chain is healthy."
        fi
    else
        error "  [${slot}] /api/health failed (frontend cannot reach its backend)."
        failed=1
    fi

    # A dummy token is rejected after the upgrade, so 101/400/401/403/426 all
    # prove that the WebSocket route is proxied end-to-end.
    ws_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 --http1.1 \
        -H 'Connection: Upgrade' \
        -H 'Upgrade: websocket' \
        -H 'Sec-WebSocket-Version: 13' \
        -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
        "${base}/api/ws?token=invalid&room=global" 2>/dev/null || true)"
    case "${ws_code}" in
        101|400|401|403|426) success "  [${slot}] WebSocket route is reachable (HTTP ${ws_code})." ;;
        *)
            error "  [${slot}] WebSocket handshake returned '${ws_code:-no response}'."
            failed=1
            ;;
    esac

    return "${failed}"
}

# --------------------------------------------------------------- probing ----

public_health() {
    curl -fsS --max-time "${PUBLIC_TIMEOUT}" \
        --resolve "${PRODUCTION_DOMAIN}:443:127.0.0.1" \
        "https://${PRODUCTION_DOMAIN}/api/health" 2>/dev/null
}

probe_health() {
    if [[ "${PROBE_MODE}" == "public" ]]; then
        public_health
    else
        curl -fsS --max-time "${PUBLIC_TIMEOUT}" \
            "http://127.0.0.1:${PROBE_PORT}/api/health" 2>/dev/null
    fi
}

resolve_probe_mode() {
    PROBE_MODE="local"
    if [[ "${EDGE_MODE}" == "1" ]] && public_health >/dev/null 2>&1; then
        PROBE_MODE="public"
        success "Public endpoint answers; post-switch probes will use https://${PRODUCTION_DOMAIN}."
    else
        warn "Public endpoint is not reachable from the host; post-switch probes will use the slot port directly."
    fi
}

verify_public() {
    local sha="$1" attempt body
    [[ "${PROBE_MODE}" == "public" ]] || return 0

    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        body="$(public_health || true)"
        if [[ -n "${body}" ]] && grep -q '"status":"ok"' <<<"${body}"; then
            if grep -qF "\"revision\":\"${sha}\"" <<<"${body}"; then
                success "Public endpoint is serving revision ${sha}."
                return 0
            fi
            if ! grep -q '"revision":"' <<<"${body}"; then
                warn "Public endpoint is up but reports no revision; skipping the revision check."
                return 0
            fi
            warn "Public endpoint still reports '${body}' (attempt ${attempt}/10, expected ${sha})."
            # A reload can leave stale workers holding the old upstream; force a
            # clean master that re-reads the upstream file, then keep probing.
            if (( attempt == 4 )); then
                info "Restarting host Nginx so it re-reads ${NGINX_UPSTREAM_CONF}..."
                nginx_restart || warn "Could not restart Nginx."
                wait_nginx_active || true
            fi
        else
            warn "Public health probe failed (attempt ${attempt}/10)."
        fi
        sleep 1
    done

    error "The public endpoint never served revision ${sha} (last response: ${body:-none})."
    return 1
}

soak() {
    local remaining="${SOAK_SECONDS}" failures=0 body
    if (( SOAK_SECONDS <= 0 )); then
        warn "Soak window disabled."
        return 0
    fi

    info "Soaking for ${SOAK_SECONDS}s (auto-rollback after 3 consecutive failures)..."
    while (( remaining > 0 )); do
        if body="$(probe_health)" && grep -q '"status":"ok"' <<<"${body}"; then
            failures=0
        else
            failures=$((failures + 1))
            warn "Health probe failed (${failures}/3)."
            if (( failures >= 3 )); then
                return 1
            fi
        fi
        sleep "${SOAK_INTERVAL}"
        remaining=$((remaining - SOAK_INTERVAL))
    done

    success "Soak window passed."
}

# ------------------------------------------------------------ prerequisites --

install_packages() {
    if command -v apt-get >/dev/null 2>&1; then
        run_privileged apt-get update
        run_privileged apt-get install -y "$@"
    elif command -v dnf >/dev/null 2>&1; then
        run_privileged dnf install -y "$@"
    elif command -v yum >/dev/null 2>&1; then
        run_privileged yum install -y "$@"
    elif command -v apk >/dev/null 2>&1; then
        run_privileged apk add --no-cache "$@"
    else
        error "Unsupported package manager. Install these packages manually: $*"
        return 1
    fi
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && run_privileged docker compose version >/dev/null 2>&1; then
        success "Docker and Docker Compose are already installed."
        return 0
    fi

    info "Installing required packages (curl, ca-certificates, git)..."
    if ! command -v curl >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
        install_packages curl ca-certificates git
    fi

    info "Installing Docker Engine and the Compose plugin..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    run_privileged sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh

    if command -v systemctl >/dev/null 2>&1; then
        run_privileged systemctl enable --now docker
    fi

    if ! run_privileged docker compose version >/dev/null 2>&1; then
        error "Docker Compose plugin installation failed."
        return 1
    fi

    local real_user="${SUDO_USER:-${USER:-}}"
    if [[ -n "${real_user}" && "${real_user}" != "root" ]]; then
        run_privileged usermod -aG docker "${real_user}" || true
        warn "Added ${real_user} to the docker group. Log out and back in for it to take effect."
    fi

    success "Docker and Docker Compose installed."
}

pull_code() {
    local repo_url
    if run_git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if ! run_git remote get-url origin >/dev/null 2>&1; then
            if (( ASSUME_YES )); then
                warn "No 'origin' remote is configured; skipping the code pull."
                return 0
            fi
            warn "No 'origin' remote is configured."
            read -r -p "GitHub repository URL (leave blank to skip code pull): " repo_url || true
            if [[ -z "${repo_url}" ]]; then
                warn "Skipping code pull. Using the files already on disk."
                return 0
            fi
            run_git remote add origin "${repo_url}"
        fi
        info "Pulling latest code from origin/${BRANCH}..."
        run_git pull origin "${BRANCH}"
        return 0
    fi

    if (( ASSUME_YES )); then
        warn "No Git repository found in ${SCRIPT_DIR}; skipping the code pull."
        return 0
    fi

    warn "No Git repository found in ${SCRIPT_DIR}."
    read -r -p "GitHub repository URL (leave blank to skip code pull): " repo_url || true
    if [[ -z "${repo_url}" ]]; then
        warn "Skipping code pull. Using the files already on disk."
        return 0
    fi

    info "Initializing repository and fetching ${repo_url}..."
    run_git init
    run_git branch -M "${BRANCH}"
    if run_git remote get-url origin >/dev/null 2>&1; then
        run_git remote set-url origin "${repo_url}"
    else
        run_git remote add origin "${repo_url}"
    fi
    run_git fetch origin
    run_git reset --hard "origin/${BRANCH}"
    success "Code pulled from GitHub."
}

add_cors_origin() {
    local origin="$1"
    [[ -n "${origin}" ]] || return 0
    if grep -q '^CORS_ORIGINS=' "${ENV_FILE}"; then
        if ! grep -qF "\"${origin}\"" "${ENV_FILE}"; then
            sed -i "s|^CORS_ORIGINS=\(.*\)\]|CORS_ORIGINS=\1,\"${origin}\"]|" "${ENV_FILE}"
        fi
    else
        printf 'CORS_ORIGINS=["%s"]\n' "${origin}" >> "${ENV_FILE}"
    fi
}

ensure_env() {
    mkdir -p "${SCRIPT_DIR}/backend"

    if [[ ! -f "${ENV_FILE}" ]]; then
        if [[ -f "${SCRIPT_DIR}/backend/.env.example" ]]; then
            cp "${SCRIPT_DIR}/backend/.env.example" "${ENV_FILE}"
            info "Created backend/.env from backend/.env.example."
        else
            {
                printf 'DATABASE_URL=%s\n' "${DB_URL}"
                printf 'CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]\n'
                printf 'SECRET_KEY=change-me-to-a-long-random-string\n'
                printf 'ALGORITHM=HS256\n'
                printf 'ACCESS_TOKEN_EXPIRE_MINUTES=10080\n'
                printf 'ADMIN_CODE=ROOT01\n'
                printf 'MAX_UPLOAD_MB=25\n'
            } > "${ENV_FILE}"
            info "Created a new backend/.env."
        fi
    fi

    if grep -q '^DATABASE_URL=' "${ENV_FILE}"; then
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|" "${ENV_FILE}"
    else
        printf 'DATABASE_URL=%s\n' "${DB_URL}" >> "${ENV_FILE}"
    fi

    # Guarantee the production origin is present on every start/update.
    add_cors_origin "https://${PRODUCTION_DOMAIN}"
    add_cors_origin "http://${PRODUCTION_DOMAIN}"

    if ! grep -q '^MAX_UPLOAD_MB=' "${ENV_FILE}"; then
        printf 'MAX_UPLOAD_MB=25\n' >> "${ENV_FILE}"
    fi

    if ! grep -q '^SECRET_KEY=' "${ENV_FILE}" || grep -qE '^SECRET_KEY=(change-me.*)?$' "${ENV_FILE}"; then
        local secret
        secret="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
        if grep -q '^SECRET_KEY=' "${ENV_FILE}"; then
            sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${secret}|" "${ENV_FILE}"
        else
            printf 'SECRET_KEY=%s\n' "${secret}" >> "${ENV_FILE}"
        fi
        success "Generated a new SECRET_KEY."
    fi

    ensure_owner_env
}

# Owner account (top role: server stats + system settings).
# On first install the username/code are prompted; in non-interactive runs
# both are generated silently so deploys never hang. The backend creates the
# account on every boot from these two values.
generate_access_code() {
    # 6-char uppercase alphanumeric access code (matches backend rules).
    local pool="ABCDEFGHJKLMNPQRSTUVWXYZ23456789" pool_len="${#pool}" out="" i r
    for (( i = 0; i < 6; i++ )); do
        r="$(od -An -N1 -tu1 /dev/urandom | tr -d ' ' || echo 0)"
        out+="${pool:r % pool_len:1}"
    done
    printf '%s' "${out}"
}

ensure_owner_env() {
    local owner_username owner_code _reply
    owner_username="$(grep -E '^OWNER_USERNAME=' "${ENV_FILE}" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '"' || true)"
    owner_code="$(grep -E '^OWNER_ACCESS_CODE=' "${ENV_FILE}" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '"' || true)"

    if [[ -n "${owner_username}" && -n "${owner_code}" ]]; then
        return 0
    fi

    if [[ -z "${owner_username}" ]]; then
        if (( ! ASSUME_YES )); then
            echo
            info "Owner account (top-level role). Enter a username and press enter to accept the suggested one."
            read -r -p "OWNER_USERNAME [owner]: " _reply || _reply=""
            owner_username="${_reply:-owner}"
        else
            owner_username="owner"
        fi
        if grep -q '^OWNER_USERNAME=' "${ENV_FILE}"; then
            sed -i "s|^OWNER_USERNAME=.*|OWNER_USERNAME=${owner_username}|" "${ENV_FILE}"
        else
            printf 'OWNER_USERNAME=%s\n' "${owner_username}" >> "${ENV_FILE}"
        fi
    fi

    if [[ -z "${owner_code}" ]]; then
        owner_code="$(generate_access_code)"
        if grep -q '^OWNER_ACCESS_CODE=' "${ENV_FILE}"; then
            sed -i "s|^OWNER_ACCESS_CODE=.*|OWNER_ACCESS_CODE=${owner_code}|" "${ENV_FILE}"
        else
            printf 'OWNER_ACCESS_CODE=%s\n' "${owner_code}" >> "${ENV_FILE}"
        fi
        success "Generated OWNER_ACCESS_CODE for «${owner_username}»: ${owner_code}"
        warn "Save it now — it is only shown once from this script; it stays in backend/.env."
    fi
}

configure_domain() {
    echo
    info "Domain setup (optional). ArchSchool is reached through host Nginx -> slot port."
    local domain=""
    if (( ASSUME_YES )); then
        warn "Non-interactive mode: skipping the domain prompt."
    else
        read -r -p "Domain name (e.g. arch.example.com, leave blank to skip): " domain || true
    fi

    domain="${domain#http://}"
    domain="${domain#https://}"
    domain="${domain%/}"

    # Always keep the known production origin in CORS, even before/without
    # the interactive domain step, so API calls from the browser are allowed.
    add_cors_origin "https://${PRODUCTION_DOMAIN}"
    add_cors_origin "http://${PRODUCTION_DOMAIN}"

    if [[ -z "${domain}" ]]; then
        warn "No domain configured. Use the configured Nginx upstream to reach the app."
        return 0
    fi

    if [[ ! "${domain}" =~ ^[A-Za-z0-9.-]+$ ]]; then
        warn "Invalid domain name. Skipping domain configuration."
        return 0
    fi

    add_cors_origin "https://${domain}"
    add_cors_origin "http://${domain}"

    success "CORS_ORIGINS updated for ${domain}."
    info "Point your host Nginx virtual host for ${domain} at the '${UPSTREAM_NAME}' upstream."
    info "IMPORTANT: keep 'client_max_body_size 30m;' in that server block,"
    info "otherwise uploads larger than 25 MB fail with a 413 / 'Failed to fetch'."
}

read_revision() {
    GIT_SHA="$(run_git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    IMAGE_TAG="${GIT_SHA}"
    export GIT_SHA IMAGE_TAG
    info "Deploying revision: ${GIT_SHA}"

    if [[ -n "$(run_git status --porcelain 2>/dev/null || true)" ]]; then
        warn "The working tree has uncommitted changes; the images will contain them."
    fi
}

preflight() {
    check_sudo

    if ! command -v docker >/dev/null 2>&1 \
        || ! run_privileged docker compose version >/dev/null 2>&1; then
        error "Docker/Docker Compose is not installed. Run: ./deploy.sh setup"
        return 1
    fi

    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required for health checks. Install it and re-run."
        return 1
    fi

    if ! run_git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        error "This directory is not a Git repository, so no revision can be stamped."
        error "Run ./deploy.sh setup to initialise it."
        return 1
    fi

    local avail
    avail="$(df -Pk "${SCRIPT_DIR}" | awk 'NR==2 {print $4}' || true)"
    if [[ -n "${avail}" ]] && (( avail < 1048576 )); then
        warn "Less than 1 GB of free space on the project volume; the image build may fail."
    fi
}

# ----------------------------------------------------------------- deploy ---

build_slot() {
    local slot="$1"
    info "Building the ${slot} slot images (tag: ${IMAGE_TAG}). The running slot is untouched."
    if ! slot_compose "${slot}" build; then
        error "Image build failed. The active slot is still serving traffic."
        return 1
    fi
    success "Images built: archschool-backend:${IMAGE_TAG}, archschool-frontend:${IMAGE_TAG}"
}

ensure_database() {
    if [[ "$(container_health archschool_db)" == "healthy" ]]; then
        return 0
    fi
    info "Starting the database container..."
    # --no-deps: never touch the app slots from here.
    compose up -d --no-deps db || return 1
    info "Waiting for PostgreSQL..."
    wait_container_healthy archschool_db
}

# The backend is started before its frontend: the frontend's nginx resolves
# its BACKEND_HOST at startup, so the container must already exist. --no-deps
# on both calls keeps Compose from ever recreating the database container.
start_slot() {
    local slot="$1"
    ensure_database || return 1

    info "Starting backend-${slot}..."
    if ! slot_compose "${slot}" up -d --no-build --force-recreate --no-deps \
        "backend-${slot}"; then
        error "Could not start backend-${slot}."
        return 1
    fi
    if ! wait_container_healthy "$(slot_backend "${slot}")"; then
        return 1
    fi

    info "Starting frontend-${slot}..."
    if ! slot_compose "${slot}" up -d --no-build --force-recreate --no-deps \
        "frontend-${slot}"; then
        error "Could not start frontend-${slot}."
        return 1
    fi
    wait_container_healthy "$(slot_frontend "${slot}")"
}

stop_slot() {
    local slot="$1"
    if ! container_exists "$(slot_frontend "${slot}")" \
        && ! container_exists "$(slot_backend "${slot}")"; then
        return 0
    fi
    info "Stopping the ${slot} slot (containers and images are kept for rollback)..."
    # Service names are always explicit: `docker compose stop` without them
    # would stop *every* container of the project — i.e. the live slot too.
    slot_compose "${slot}" stop \
        "frontend-${slot}" "backend-${slot}" || warn "Could not stop the ${slot} slot cleanly."
}

# Restart an existing (stopped) slot without recreating it. The backend is
# started first so the frontend's nginx can resolve it at startup.
resume_slot() {
    local slot="$1"
    ensure_database || return 1

    slot_compose "${slot}" start "backend-${slot}" || return 1
    wait_container_healthy "$(slot_backend "${slot}")" || return 1

    slot_compose "${slot}" start "frontend-${slot}" || return 1
    wait_container_healthy "$(slot_frontend "${slot}")"
}

remove_legacy_containers() {
    legacy_exists || return 0
    info "Removing the legacy (pre-blue-green) containers..."
    run_privileged docker rm -f archschool_frontend archschool_backend >/dev/null 2>&1 || true
    success "Legacy containers removed; port ${SLOT_BLUE_PORT} is free for the next deploy."
}

# Compose interpolates the image tag, so commands that touch an existing slot
# (start/restart/status) must reuse the tag the containers were created with —
# otherwise Compose would try to pull/build a different image.
adopt_runtime_env() {
    local slot revision
    slot="$(detect_active_slot)"
    if [[ "${slot}" == "none" ]]; then
        return 0
    fi
    revision="$(container_revision "$(slot_frontend "${slot}")")"
    if [[ -n "${revision}" && "${revision}" != "unknown" ]]; then
        GIT_SHA="${revision}"
        IMAGE_TAG="${revision}"
        export GIT_SHA IMAGE_TAG
    fi
}

write_state() {
    local active_slot="$1" active_port="$2" active_rev="$3"
    local previous_slot="$4" previous_port="$5" previous_rev="$6"
    {
        printf 'ACTIVE_SLOT=%s\n' "${active_slot}"
        printf 'ACTIVE_PORT=%s\n' "${active_port}"
        printf 'ACTIVE_REVISION=%s\n' "${active_rev}"
        printf 'PREVIOUS_SLOT=%s\n' "${previous_slot}"
        printf 'PREVIOUS_PORT=%s\n' "${previous_port}"
        printf 'PREVIOUS_REVISION=%s\n' "${previous_rev}"
        printf 'DEPLOYED_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${STATE_FILE}" 2>/dev/null || warn "Could not write ${STATE_FILE}"
}

print_summary() {
    local slot="$1" port="$2" revision="$3"
    echo
    printf "${BOLD}=== Deployment summary ===${NC}\n"
    plain "  Active slot : ${slot}"
    plain "  Slot port   : 127.0.0.1:${port}"
    plain "  Revision    : ${revision}"
    if [[ "${EDGE_MODE}" == "1" ]]; then
        plain "  Traffic     : https://${PRODUCTION_DOMAIN} -> ${UPSTREAM_NAME} -> 127.0.0.1:${port}"
        plain "  Previous    : $(state_get PREVIOUS_SLOT) (kept for './deploy.sh rollback')"
    else
        plain "  Traffic     : http://SERVER_IP:${port} (no host Nginx switch)"
    fi
    plain ""
}

cmd_deploy() {
    local active target active_port target_port old_rev

    preflight || return 1

    if (( SKIP_PULL == 0 )); then
        pull_code || return 1
    fi
    ensure_env
    read_revision

    if (( BACKUP_BEFORE_DEPLOY )); then
        info "Creating a pre-deploy backup (--backup)..."
        if ! cmd_backup; then
            error "The pre-deploy backup failed; aborting so nothing is lost."
            return 1
        fi
    fi

    active="$(detect_active_slot)"
    target="$(choose_target_slot "${active}")"
    active_port="$(detect_active_port || true)"
    active_port="${active_port:-}"

    echo
    info "Active slot: ${active}${active_port:+ (127.0.0.1:${active_port})}"
    info "Target slot: ${target} (127.0.0.1:$(slot_port "${target}"))"
    if legacy_exists; then
        warn "Pre-blue-green containers found; they are removed after the switch succeeds."
    fi

    ensure_edge || return 1
    resolve_probe_mode
    PROBE_PORT="${active_port:-${SLOT_BLUE_PORT}}"

    if [[ "${EDGE_MODE}" != "1" ]]; then
        if [[ "${active}" != "none" && "$(slot_port "${target}")" != "${active_port}" ]]; then
            error "Host Nginx is required to move traffic between slots. Aborting."
            return 1
        fi
    fi

    if ! guard_port_free "${target}"; then
        return 1
    fi

    build_slot "${target}" || return 1

    if ! start_slot "${target}"; then
        error "The ${target} slot did not become healthy. Nothing was switched."
        echo
        slot_compose "${target}" logs --tail=40 \
            "frontend-${target}" "backend-${target}" >&2 || true
        stop_slot "${target}"
        return 1
    fi

    if ! slot_smoke "${target}"; then
        error "The ${target} slot failed its smoke test. Nothing was switched."
        stop_slot "${target}"
        return 1
    fi

    target_port="$(slot_port "${target}")"
    old_rev="$(container_revision "$(slot_frontend "${active}")")"
    [[ -n "${old_rev}" ]] || old_rev="$(state_get ACTIVE_REVISION)"
    [[ -n "${old_rev}" ]] || old_rev="unknown"

    if ! switch_traffic "${target_port}"; then
        error "Traffic switch failed; the ${active} slot keeps serving."
        stop_slot "${target}"
        return 1
    fi
    PROBE_PORT="${target_port}"

    if ! verify_public "${GIT_SHA}"; then
        error "The public endpoint did not confirm the new revision; rolling back."
        switch_traffic "${active_port:-${SLOT_BLUE_PORT}}" || warn "Could not switch traffic back automatically."
        PROBE_PORT="${active_port:-${SLOT_BLUE_PORT}}"
        stop_slot "${target}"
        return 1
    fi

    # Chat depends on the host proxy upgrading /api/ws. A broken host config
    # cannot be fixed by moving traffic back, so report it instead of rolling
    # back (ensure_host_ws has already patched what it could).
    if ! check_public_ws; then
        warn "HTTP traffic stays on the ${target} slot; only WebSocket is affected."
        warn "Re-run 'sudo ./deploy.sh fix-nginx' once the block above is fixed."
    fi

    if ! soak; then
        error "Post-switch health checks failed; rolling back to the ${active} slot."
        if switch_traffic "${active_port:-${SLOT_BLUE_PORT}}"; then
            PROBE_PORT="${active_port:-${SLOT_BLUE_PORT}}"
            stop_slot "${target}"
            error "Rolled back. The previous slot is serving again."
        else
            error "Rollback switch failed! Manual action required: ${NGINX_UPSTREAM_CONF}"
        fi
        return 1
    fi

    # The pre-blue-green containers can never be a slot target (different
    # names), so they are always safe to remove once traffic has moved.
    remove_legacy_containers

    if [[ "${active}" != "none" ]] && container_exists "$(slot_frontend "${active}")"; then
        if (( KEEP_OLD == 1 )); then
            warn "--keep-old: the ${active} slot is left running (chat sockets stay split until it stops)."
        else
            stop_slot "${active}"
        fi
    fi

    write_state "${target}" "${target_port}" "${GIT_SHA}" "${active}" "${active_port:-}" "${old_rev}"

    info "Pruning dangling images (tagged release images are kept)..."
    run_privileged docker image prune -f >/dev/null 2>&1 || true

    success "Deployment complete: ${target} is live on revision ${GIT_SHA}."
    print_summary "${target}" "${target_port}" "${GIT_SHA}"
    info "Rollback:  sudo ./deploy.sh rollback"
    info "Cleanup:   sudo ./deploy.sh cleanup"
}

# --------------------------------------------------------------- rollback ---

cmd_rollback() {
    local active active_port previous previous_port previous_rev current_rev

    check_sudo
    ensure_env

    active="$(detect_active_slot)"
    active_port="$(detect_active_port || true)"

    if [[ "${active}" == "none" ]]; then
        error "Could not determine the active slot (no upstream file and no running slot)."
        return 1
    fi

    previous="$(slot_other "${active}")"
    previous_port="$(slot_port "${previous}")"

    previous_rev="$(container_revision "$(slot_frontend "${previous}")")"
    if [[ -z "${previous_rev}" ]]; then
        previous_rev="$(state_get PREVIOUS_REVISION)"
    fi

    if [[ -z "${previous_rev}" || "${previous_rev}" == "unknown" ]]; then
        error "No rollback target is recorded."
        error "If you just migrated from the pre-blue-green setup, redeploy the previous commit instead:"
        error "  git checkout <previous-sha> && sudo ./deploy.sh deploy --skip-pull"
        return 1
    fi

    echo
    info "Active slot : ${active} (127.0.0.1:${active_port})"
    info "Rolling back to: ${previous} (127.0.0.1:${previous_port}, revision ${previous_rev})"
    warn "Schema rollback is not automatic. Only revert if the newer release kept the database backward compatible."

    if ! nginx_present; then
        error "Host Nginx is required to move traffic between slots. Aborting."
        return 1
    fi

    if [[ -z "$(read_upstream_port)" ]]; then
        error "No managed upstream found (${NGINX_UPSTREAM_CONF}). Run a normal deploy first."
        return 1
    fi

    IMAGE_TAG="${previous_rev}"
    GIT_SHA="${previous_rev}"
    export IMAGE_TAG GIT_SHA

    if container_exists "$(slot_frontend "${previous}")" \
        && container_exists "$(slot_backend "${previous}")"; then
        info "Resuming the existing ${previous} containers..."
        resume_slot "${previous}" || return 1
    else
        if ! run_privileged docker image inspect "archschool-frontend:${previous_rev}" >/dev/null 2>&1 \
            || ! run_privileged docker image inspect "archschool-backend:${previous_rev}" >/dev/null 2>&1; then
            error "Images for revision ${previous_rev} are gone (cleanup already removed them)."
            error "Redeploy the previous commit instead: git checkout ${previous_rev} && sudo ./deploy.sh deploy --skip-pull"
            return 1
        fi
        warn "The ${previous} containers were removed; recreating them from revision ${previous_rev}."
        start_slot "${previous}" || return 1
    fi

    if ! wait_slot_healthy "${previous}"; then
        error "The ${previous} slot did not become healthy; traffic was not switched."
        return 1
    fi

    if ! slot_smoke "${previous}"; then
        error "The ${previous} slot failed its smoke test; traffic was not switched."
        return 1
    fi

    resolve_probe_mode
    if ! switch_traffic "${previous_port}"; then
        error "Could not switch traffic back. The ${active} slot is still serving."
        return 1
    fi
    PROBE_PORT="${previous_port}"
    verify_public "${previous_rev}" || warn "The public endpoint did not confirm revision ${previous_rev}; check it manually."

    current_rev="$(container_revision "$(slot_frontend "${active}")")"
    stop_slot "${active}"
    write_state "${previous}" "${previous_port}" "${previous_rev}" "${active}" "${active_port:-}" "${current_rev:-unknown}"

    success "Rollback complete. ${previous} (revision ${previous_rev}) is live."
    print_summary "${previous}" "${previous_port}" "${previous_rev}"
    info "Roll forward again with: sudo ./deploy.sh deploy"
}

# --------------------------------------------------------------- fix-nginx ---

# Repairs the host reverse proxy in place: managed upstream + WebSocket upgrade
# headers, then reloads Nginx. No rebuild, no traffic switch, no downtime.
cmd_fix_nginx() {
    check_sudo

    echo
    printf "${BOLD}=== Host Nginx repair (upstream + WebSocket) ===${NC}\n"

    if ! nginx_present; then
        error "Host Nginx is not installed on this host."
        return 1
    fi

    ensure_edge || return 1
    EDGE_MODE=1

    # Workers started before the repair can still serve the old (non-upgrading)
    # config; a restart makes the fix apply to every connection immediately.
    info "Restarting host Nginx so every worker uses the repaired configuration..."
    if nginx_restart; then
        wait_nginx_active || warn "Host Nginx did not report 'active' within 15s."
    else
        warn "Could not restart Nginx; run 'sudo systemctl restart nginx' manually."
    fi

    local port port_slot
    port="$(read_upstream_port)"
    if [[ -z "${port}" ]]; then
        error "No managed upstream found in ${NGINX_UPSTREAM_CONF}."
        return 1
    fi
    port_slot="$(port_to_slot "${port}" || true)"

    echo
    info "Traffic target: ${NGINX_UPSTREAM_CONF} -> 127.0.0.1:${port}${port_slot:+ (${port_slot})}"

    # Slot-local handshake (proves frontend nginx + backend are fine).
    if curl -s -o /dev/null -w '%{http_code}' --max-time "${WS_PROBE_TIMEOUT}" --http1.1 \
        -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
        -H 'Sec-WebSocket-Version: 13' \
        -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
        "http://127.0.0.1:${port}/api/ws?token=invalid&room=global" 2>/dev/null \
        | grep -qE '^(101|400|401|403|426)$'; then
        success "Slot WebSocket handshake works on 127.0.0.1:${port}."
    else
        warn "The slot itself did not upgrade the WebSocket; check the backend logs."
    fi

    # Diagnostic that separates the two failure modes: with a *valid* token the
    # handshake must stay open, not close immediately.
    info "Backend WebSocket logs (last 10 lines):"
    slot_compose "${port_slot:-blue}" logs --tail=10 "backend-${port_slot:-blue}" 2>/dev/null || true

    if check_public_ws; then
        echo
        success "wss://${PRODUCTION_DOMAIN}/api/ws is ready. Reload the browser."
    else
        error "The WebSocket still fails through the host proxy. See the snippet above."
        return 1
    fi
}

# ---------------------------------------------------------------- cleanup ---

cmd_cleanup() {
    local active active_port target target_rev upstream_port

    check_sudo
    ensure_env

    active="$(detect_active_slot)"
    active_port="$(detect_active_port || true)"
    upstream_port="$(read_upstream_port)"

    if [[ "${active}" == "none" ]]; then
        error "Cannot determine the active slot; refusing to clean up."
        return 1
    fi

    if [[ -n "${upstream_port}" && "$(port_to_slot "${upstream_port}" || true)" != "${active}" ]]; then
        error "Traffic target (${upstream_port}) and detected slot (${active}) disagree; refusing to clean up."
        return 1
    fi

    if ! container_running "$(slot_frontend "${active}")"; then
        error "The active ${active} slot is not running; refusing to clean up."
        return 1
    fi

    target="$(slot_other "${active}")"
    target_rev="$(container_revision "$(slot_frontend "${target}")")"

    echo
    info "Active slot: ${active} (127.0.0.1:${active_port})"
    info "Removing the inactive ${target} slot${target_rev:+ (revision ${target_rev})}..."

    if container_exists "$(slot_frontend "${target}")" \
        || container_exists "$(slot_backend "${target}")"; then
        slot_compose "${target}" rm -sf \
            "frontend-${target}" "backend-${target}" >/dev/null 2>&1 \
            || warn "Could not remove every ${target} container."
    else
        info "No ${target} containers to remove."
    fi

    if [[ -n "${target_rev}" && "${target_rev}" != "unknown" ]]; then
        run_privileged docker image rm -f \
            "archschool-frontend:${target_rev}" \
            "archschool-backend:${target_rev}" >/dev/null 2>&1 \
            || warn "Could not remove images for revision ${target_rev} (still in use?)."
    fi

    run_privileged docker image prune -f >/dev/null 2>&1 || true

    write_state "${active}" "${active_port:-}" "$(container_revision "$(slot_frontend "${active}")")" \
        "none" "" ""

    success "Cleanup complete. Only the ${active} slot remains."
    warn "Rollback is no longer possible from local containers/images for the removed slot."
}

# ----------------------------------------------------------------- status ---

describe_slot() {
    local slot="$1" frontend backend fh bh fe_state be_state revision marker
    frontend="$(slot_frontend "${slot}")"
    backend="$(slot_backend "${slot}")"
    fe_state="$(container_state "${frontend}")"
    be_state="$(container_state "${backend}")"
    fh="$(container_health "${frontend}")"
    bh="$(container_health "${backend}")"
    revision="$(container_revision "${frontend}")"

    marker=" "
    if [[ "$(read_upstream_port)" == "$(slot_port "${slot}")" ]]; then
        marker="*"
    fi

    printf "  %s %-5s port %-4s frontend=%-8s/%-8s backend=%-8s/%-8s rev=%s\n" \
        "${marker}" "${slot}" "$(slot_port "${slot}")" \
        "${fe_state:-missing}" "${fh}" \
        "${be_state:-missing}" "${bh}" \
        "${revision:-unknown}"
}

cmd_status() {
    local active port public_rev site_conf
    check_sudo
    ensure_env
    adopt_runtime_env

    active="$(detect_active_slot)"
    port="$(detect_active_port || true)"
    site_conf="$(detect_nginx_site_conf 2>/dev/null || true)"

    # What the *public* URL really serves. When this differs from the active
    # slot's revision, host Nginx is not reading the upstream file (a literal
    # proxy_pass, a stale worker, or a file outside conf.d).
    public_rev="$(public_health 2>/dev/null | grep -oE '"revision":"[^"]*"' | head -n1 | cut -d'"' -f4 || true)"

    echo
    printf "${BOLD}=== ArchSchool blue-green status ===${NC}\n"
    plain "  Active slot : ${active}"
    plain "  Traffic     : Nginx upstream '${UPSTREAM_NAME}' -> 127.0.0.1:${port:-?}"
    plain "  Upstream f. : ${NGINX_UPSTREAM_CONF}"
    plain "  Site config : ${site_conf:-not found}"
    plain "  Public rev  : ${public_rev:-unreachable}"
    plain "  Deployed at : $(state_get DEPLOYED_AT)"
    if [[ -n "${site_conf}" ]] && run_privileged grep -qE 'proxy_pass[[:space:]]+http://127\.0\.0\.1:(6241|6242)' "${site_conf}" 2>/dev/null; then
        warn "The site config still hardcodes a slot port; the upstream switch is ignored."
        warn "Run 'sudo ./deploy.sh fix-nginx' to route it through '${UPSTREAM_NAME}'."
    fi
    echo
    printf "  (* = receiving traffic)\n"
    describe_slot blue
    describe_slot green
    echo
    all_compose ps
}

# ----------------------------------------------------- start/stop/restart ---

cmd_start() {
    local active
    check_sudo
    ensure_env
    adopt_runtime_env

    active="$(detect_active_slot)"
    if [[ "${active}" == "none" ]]; then
        active="blue"
        warn "No active slot detected; defaulting to blue."
    fi

    info "Starting the ${active} slot (and the database)..."
    slot_compose "${active}" up -d || return 1
    success "Started."
    cmd_status
}

cmd_stop() {
    check_sudo
    ensure_env
    info "Stopping ArchSchool (volumes and data are preserved)..."
    all_compose stop || return 1
    success "Stopped."
}

cmd_restart() {
    local active
    check_sudo
    ensure_env
    adopt_runtime_env

    active="$(detect_active_slot)"
    if [[ "${active}" == "none" ]]; then
        error "No active slot detected."
        return 1
    fi

    info "Restarting the ${active} slot..."
    slot_compose "${active}" restart "frontend-${active}" "backend-${active}" || return 1
    success "Restarted."
    cmd_status
}

show_logs() {
    local choice
    check_sudo
    echo
    echo "  1) Active slot"
    echo "  2) Blue slot"
    echo "  3) Green slot"
    echo "  4) Database"
    echo "  0) Back"
    read -r -p "Select logs to follow: " choice || return 0
    case "${choice}" in
        1)
            local active
            active="$(detect_active_slot)"
            [[ "${active}" == "none" ]] && active="blue"
            slot_compose "${active}" logs -f --tail=200 || true
            ;;
        2) slot_compose blue logs -f --tail=200 || true ;;
        3) slot_compose green logs -f --tail=200 || true ;;
        4) compose logs -f --tail=200 db || true ;;
        0) return 0 ;;
        *) warn "Invalid option." ;;
    esac
}

# ------------------------------------------------------- backup / restore ---

# Owner that should receive files written as root via sudo.
real_user_name() {
    if [[ ${EUID} -eq 0 && -n "${SUDO_USER:-}" ]]; then
        printf '%s' "${SUDO_USER}"
    fi
}

give_to_real_user() {
    local path="$1" owner
    owner="$(real_user_name)"
    [[ -n "${owner}" ]] || return 0
    run_privileged chown -R "${owner}:" "${path}" 2>/dev/null || true
}

human_size() {
    local target="$1"
    [[ -e "${target}" ]] || return 0
    du -h "${target}" 2>/dev/null | awk 'NR==1 {print $1}'
}

backup_dir() {
    local dir="${BACKUP_OUT_DIR:-${SCRIPT_DIR}}"
    (cd "${dir}" 2>/dev/null && pwd)
}

backup_file_name() {
    local dir="$1" stamp name n=1
    stamp="$(date +%Y-%m-%d_%H-%M)"
    name="${BACKUP_PREFIX}_${stamp}.tar.gz"
    while [[ -e "${dir}/${name}" ]]; do
        n=$((n + 1))
        name="${BACKUP_PREFIX}_${stamp}_${n}.tar.gz"
    done
    printf '%s' "${name}"
}

latest_backup() {
    local dir
    dir="$(backup_dir)" || return 0
    ls -1t "${dir}"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null | head -n1 || true
}

cmd_list_backups() {
    local dir file found=0
    dir="$(backup_dir)" || return 1

    shopt -s nullglob
    local -a files=("${dir}"/${BACKUP_PREFIX}_*.tar.gz)
    shopt -u nullglob

    echo
    printf "${BOLD}=== Backups in %s ===${NC}\n" "${dir}"
    for file in "${files[@]}"; do
        printf "  %-48s %s\n" "$(basename "${file}")" "$(human_size "${file}")"
        found=1
    done
    (( found )) || plain "  (none yet — run: ./deploy.sh backup)"
}

# Creates archschool_backup_YYYY-MM-DD_HH-MM.tar.gz containing:
#   database.sql     -- pg_dump --clean --if-exists --no-owner
#   uploads.tar.gz   -- contents of the archschool_uploads volume
#   .env             -- backend/.env (secrets included: keep it private)
#   metadata.txt     -- revision, host, timestamp, postgres version
cmd_backup() {
    local dir work name archive rev

    check_sudo
    ensure_env

    # Recorded in metadata.txt so an archive can be traced to a release.
    rev="$(run_git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    rev="${rev:-unknown}"

    if ! dir="$(backup_dir)"; then
        error "Backup directory does not exist: ${BACKUP_OUT_DIR:-${SCRIPT_DIR}}"
        return 1
    fi

    if ! ensure_database; then
        error "The database container is not available; cannot create a backup."
        return 1
    fi

    work="$(mktemp -d)" || return 1

    info "Dumping PostgreSQL database '${DB_NAME}'..."
    if ! run_privileged docker exec "${DB_CONTAINER}" \
        pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
        --clean --if-exists --no-owner --no-privileges \
        >"${work}/database.sql"; then
        error "pg_dump failed."
        rm -rf "${work}"
        return 1
    fi
    if [[ ! -s "${work}/database.sql" ]]; then
        error "pg_dump produced an empty file; aborting."
        rm -rf "${work}"
        return 1
    fi
    success "  database.sql ($(human_size "${work}/database.sql"))"

    info "Archiving the uploads volume '${UPLOADS_VOLUME}'..."
    if run_privileged docker volume inspect "${UPLOADS_VOLUME}" >/dev/null 2>&1; then
        if ! run_privileged docker run --rm \
            -v "${UPLOADS_VOLUME}:/data:ro" \
            -v "${work}:/backup" \
            "${HELPER_IMAGE}" \
            tar czf /backup/uploads.tar.gz -C /data .; then
            error "Could not archive the uploads volume."
            rm -rf "${work}"
            return 1
        fi
    else
        warn "Volume ${UPLOADS_VOLUME} does not exist; storing an empty archive."
        run_privileged tar -czf "${work}/uploads.tar.gz" --files-from /dev/null
    fi
    success "  uploads.tar.gz ($(human_size "${work}/uploads.tar.gz"))"

    if [[ -f "${ENV_FILE}" ]]; then
        run_privileged cp -p "${ENV_FILE}" "${work}/.env"
        success "  .env"
    else
        warn "backend/.env is missing; the archive will not contain configuration."
    fi

    {
        printf 'app=archschool\n'
        printf 'format=1\n'
        printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'revision=%s\n' "${rev}"
        printf 'hostname=%s\n' "$(hostname 2>/dev/null || echo unknown)"
        printf 'database=%s\n' "${DB_NAME}"
        printf 'postgres=%s\n' "$(
            run_privileged docker exec "${DB_CONTAINER}" postgres --version 2>/dev/null \
                | tr -d '\r' | tr '\n' ' ' || true
        )"
    } >"${work}/metadata.txt"

    name="$(backup_file_name "${dir}")"
    archive="${dir}/${name}"

    info "Compressing into ${name}..."
    if ! run_privileged tar -czf "${archive}" -C "${work}" .; then
        error "Could not create the archive."
        rm -rf "${work}"
        rm -f "${archive}"
        return 1
    fi

    # The archive holds SECRET_KEY and ADMIN_CODE: private, and never committed.
    run_privileged chmod 600 "${archive}" 2>/dev/null || true
    give_to_real_user "${archive}"

    if ! run_privileged tar -tzf "${archive}" >/dev/null 2>&1; then
        error "The archive failed its integrity check."
        rm -rf "${work}"
        return 1
    fi

    rm -rf "${work}"

    echo
    success "Backup complete: ${archive}"
    plain "  Size     : $(human_size "${archive}")"
    plain "  Contents : database.sql, uploads.tar.gz, .env, metadata.txt"
    plain "  Restore  : sudo ./deploy.sh restore $(basename "${archive}")"
    warn "The archive contains secrets (mode 600). Do not commit or share it publicly."
}

# Restores a backup created above. Intended for a fresh server, but also
# usable in place: the current data WILL be replaced.
cmd_restore() {
    local archive="$1" work members answer
    local keep

    check_sudo

    if [[ -z "${archive}" ]]; then
        error "Usage: sudo ./deploy.sh restore <archschool_backup_YYYY-MM-DD_HH-MM.tar.gz>"
        return 1
    fi
    if [[ ! -f "${archive}" ]]; then
        error "Backup file not found: ${archive}"
        return 1
    fi
    archive="$(cd "$(dirname "${archive}")" && pwd)/$(basename "${archive}")"

    if ! run_privileged tar -tzf "${archive}" >/dev/null 2>&1; then
        error "${archive} is not a readable .tar.gz archive."
        return 1
    fi
    members="$(run_privileged tar -tzf "${archive}")"
    if ! grep -qE '(^\./)?database\.sql$' <<<"${members}"; then
        error "The archive has no database.sql — this is not an ArchSchool backup."
        return 1
    fi

    echo
    printf "${BOLD}=== Restore preview ===${NC}\n"
    plain "  Archive : ${archive}"
    plain "  Size    : $(human_size "${archive}")"
    plain "  Contains: $(tr '\n' ' ' <<<"${members}" | sed 's|\./||g' | tr -s ' ')"
    echo

    if (( ! ASSUME_YES )); then
        warn "This will OVERWRITE the database, the uploads volume and backend/.env."
        warn "The running app slots will be stopped while the data is restored."
        read -r -p "Type RESTORE to continue (anything else aborts): " answer || true
        if [[ "${answer}" != "RESTORE" ]]; then
            warn "Restore cancelled. Nothing was changed."
            return 1
        fi
    fi

    work="$(mktemp -d)" || return 1

    if ! command -v docker >/dev/null 2>&1; then
        info "Docker is not installed yet; installing it before the restore..."
        install_docker || { rm -rf "${work}"; return 1; }
    fi

    info "Extracting the archive..."
    if ! run_privileged tar -xzf "${archive}" -C "${work}" --no-same-owner; then
        error "Extraction failed."
        rm -rf "${work}"
        return 1
    fi
    give_to_real_user "${work}"

    # .env first: Compose cannot parse the stack without backend/.env.
    if [[ -f "${work}/.env" ]]; then
        if [[ -f "${ENV_FILE}" ]]; then
            keep="${ENV_FILE}.pre-restore.$(date +%Y%m%d%H%M%S)"
            run_privileged cp -p "${ENV_FILE}" "${keep}" || true
            info "Previous backend/.env saved as $(basename "${keep}")."
        fi
        mkdir -p "$(dirname "${ENV_FILE}")"
        run_privileged cp -f "${work}/.env" "${ENV_FILE}"
        give_to_real_user "${ENV_FILE}"
        success "backend/.env restored."
    else
        warn "The archive has no .env; keeping the existing configuration."
    fi
    ensure_env

    info "Stopping the application slots so nothing holds the database..."
    stop_slot blue
    stop_slot green

    if ! ensure_database; then
        error "Could not start the database container."
        rm -rf "${work}"
        return 1
    fi

    info "Restoring the database (this can take a while)..."
    if ! run_privileged docker exec -i "${DB_CONTAINER}" \
        psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}" \
        <"${work}/database.sql" >"${work}/psql.log" 2>&1; then
        error "psql restore failed. Last lines:"
        tail -n 25 "${work}/psql.log" 2>/dev/null | sed 's/^/    /' >&2 || true
        error "The database may be in a partially restored state."
        error "Extracted files are kept in ${work} for inspection."
        return 1
    fi
    success "Database restored."

    if [[ -f "${work}/uploads.tar.gz" ]]; then
        info "Restoring uploads into volume '${UPLOADS_VOLUME}'..."
        if ! run_privileged docker volume inspect "${UPLOADS_VOLUME}" >/dev/null 2>&1; then
            run_privileged docker volume create "${UPLOADS_VOLUME}" >/dev/null || {
                error "Could not create the uploads volume."
                rm -rf "${work}"
                return 1
            }
        fi
        if ! run_privileged docker run --rm \
            -v "${UPLOADS_VOLUME}:/data" \
            -v "${work}:/backup:ro" \
            "${HELPER_IMAGE}" \
            sh -c 'find /data -mindepth 1 -delete 2>/dev/null; tar xzf /backup/uploads.tar.gz -C /data'; then
            error "Could not restore the uploads volume."
            rm -rf "${work}"
            return 1
        fi
        success "Uploads restored."
    else
        warn "The archive has no uploads.tar.gz; uploads were not restored."
    fi

    rm -rf "${work}"

    success "Data restore finished."
    info "Deploying the application on top of the restored data..."

    if ! cmd_deploy; then
        error "The data was restored, but the deploy failed."
        error "Fix the error above, then run: sudo ./deploy.sh deploy"
        plain ""
        plain "  On a brand-new server, 'sudo ./deploy.sh setup' installs Docker and"
        plain "  prepares the host; the restored database and uploads are kept."
        return 1
    fi

    echo
    success "Migration complete. ArchSchool is live with the restored data."
}

# ------------------------------------------------------------------ setup ---

cmd_setup() {
    echo
    printf "${BOLD}=== ArchSchool initial setup (blue-green) ===${NC}\n"
    check_sudo
    install_docker || return 1
    pull_code || return 1
    ensure_env
    configure_domain
    cmd_deploy
}

# ------------------------------------------------------------------- menu ---

usage() {
    cat <<'EOF'
ArchSchool deployment manager (blue-green)

Usage:
  ./deploy.sh [command] [flags]

Commands:
  deploy      Pull, build, start the inactive slot, verify, switch, soak
  rollback    Switch traffic back to the previous slot
  cleanup     Remove the inactive slot's containers and images
  status      Show both slots and the active traffic target
  fix-nginx   Repair host Nginx (upstream + WebSocket headers) and reload
  setup       First-time setup (docker, code, env, domain, deploy)
  backup      Database + uploads + .env into one .tar.gz in the project root
  restore     Restore a backup archive, then deploy (fresh-server migration)
  list-backups  List the archives found in the backup directory
  start       Start the active slot
  stop        Stop every container (data is preserved)
  restart     Restart the active slot
  logs        Follow logs
  (no command) interactive menu

Flags:
  --yes, -y     Non-interactive (accept defaults, no prompts)
  --skip-pull   Do not run git pull
  --soak=N      Soak window in seconds (default 60)
  --no-soak     Skip the soak window
  --keep-old    Leave the previous slot running after the switch
  --timeout=N   Health-check timeout in seconds (default 180)
  --backup      Take a backup before deploying
  --out=DIR     Directory for `backup` / `list-backups` (default: project root)

Environment:
  PRODUCTION_DOMAIN   Public hostname (default archschool.vidxsepehr.ir)
  NGINX_SITE_CONF     Host Nginx site file (default: auto-detect)
  NGINX_UPSTREAM_CONF Upstream file (default /etc/nginx/conf.d/00-archschool-upstream.conf)
EOF
}

show_menu() {
    local active
    clear 2>/dev/null || true
    printf "${CYAN}${BOLD}"
    cat <<'EOF'
  ___              _     _____ _                 _
 / _ \            | |   /  ___| |               | |
/ /_\ \_ __ ___  __| |_  \ `--.| |__   ___   ___| |
|  _  | '__/ __|/ _` | |  `--. \ '_ \ / _ \ / _ \ |
| | | | | | (__| (_| | | /\__/ / | | | (_) | (_) | |
\_| |_/_|  \___|\__,_|_| \____/|_| |_|\___/ \___/|_|
EOF
    printf "${NC}\n"
    echo "  ArchSchool deployment manager — blue-green"
    echo "  ------------------------------------------------"
    active="$(detect_active_slot 2>/dev/null || echo unknown)"
    echo "  Active slot: ${active}   Traffic: $(read_upstream_port 2>/dev/null || true)"
    echo "  ------------------------------------------------"
    echo "  1) Initial setup (Docker, code, domain, first deploy)"
    echo "  2) Deploy / update (zero downtime)"
    echo "  3) Rollback to the previous slot"
    echo "  4) Clean up the inactive slot"
    echo "  5) Start the active slot"
    echo "  6) Stop all containers"
    echo "  7) Restart the active slot"
    echo "  8) Status (slots + traffic)"
    echo "  9) View live logs"
    echo " 10) Backup now (database + uploads + .env)"
    echo " 11) Restore from a backup (overwrites data!)"
    echo " 12) List backups"
    echo " 13) Fix host Nginx (upstream + WebSocket headers)"
    echo "  0) Exit"
    echo
}

interactive_menu() {
    local choice file answer
    check_sudo
    while true; do
        show_menu
        if ! read -r -p "Select an option [0-9, 10-13]: " choice; then
            echo
            exit 0
        fi
        case "${choice}" in
            1) cmd_setup || warn "Initial setup failed. Check the output above." ;;
            2) cmd_deploy || warn "Deployment failed. The previous slot is still serving." ;;
            3) cmd_rollback || warn "Rollback failed. Check the output above." ;;
            4) cmd_cleanup || warn "Cleanup failed. Check the output above." ;;
            5) cmd_start || warn "Could not start ArchSchool." ;;
            6) cmd_stop || warn "Could not stop ArchSchool." ;;
            7) cmd_restart || warn "Could not restart ArchSchool." ;;
            8) cmd_status || warn "Could not read the status." ;;
            9) show_logs || true ;;
            10) cmd_backup || warn "Backup failed. Check the output above." ;;
            11)
                file="$(latest_backup)"
                read -r -p "Backup file [${file:-path/to/archschool_backup_*.tar.gz}]: " answer || true
                [[ -n "${answer}" ]] && file="${answer}"
                if [[ -n "${file}" ]]; then
                    cmd_restore "${file}" || warn "Restore failed. Check the output above."
                else
                    warn "No backup selected."
                fi
                ;;
            12) cmd_list_backups || warn "Could not list the backups." ;;
            13) cmd_fix_nginx || warn "Could not repair the host Nginx configuration." ;;
            0) printf "${GREEN}Bye.${NC}\n"; exit 0 ;;
            *) warn "Invalid option: ${choice}" ;;
        esac
        echo
        read -r -p "Press Enter to return to the menu..." _ || true
    done
}

# ------------------------------------------------------------------- main ---

parse_args() {
    while (( $# )); do
        case "$1" in
            --yes|-y)     ASSUME_YES=1 ;;
            --skip-pull)  SKIP_PULL=1 ;;
            --soak=*)     SOAK_SECONDS="${1#*=}" ;;
            --no-soak)    SOAK_SECONDS=0 ;;
            --keep-old)   KEEP_OLD=1 ;;
            --timeout=*)  HEALTH_TIMEOUT="${1#*=}" ;;
            --backup)     BACKUP_BEFORE_DEPLOY=1 ;;
            --out=*)      BACKUP_OUT_DIR="${1#*=}" ;;
            -h|--help)    usage; exit 0 ;;
            deploy|update)   COMMAND="deploy" ;;
            rollback)        COMMAND="rollback" ;;
            cleanup|prune)   COMMAND="cleanup" ;;
            status)          COMMAND="status" ;;
            setup|install)   COMMAND="setup" ;;
            fix-nginx|repair-nginx|fix-ws) COMMAND="fix-nginx" ;;
            backup)          COMMAND="backup" ;;
            restore)         COMMAND="restore" ;;
            list-backups|backups) COMMAND="list-backups" ;;
            start)           COMMAND="start" ;;
            stop)            COMMAND="stop" ;;
            restart)         COMMAND="restart" ;;
            logs)            COMMAND="logs" ;;
            -*)  error "Unknown option: $1"; usage; exit 2 ;;
            *)
                if [[ "${COMMAND}" == "restore" && -z "${RESTORE_FILE}" ]]; then
                    RESTORE_FILE="$1"
                else
                    error "Unknown command: $1"
                    usage
                    exit 2
                fi
                ;;
        esac
        shift
    done
}

main() {
    parse_args "$@"

    if [[ -z "${COMMAND}" ]]; then
        interactive_menu
        exit 0
    fi

    case "${COMMAND}" in
        deploy)   cmd_deploy ;;
        rollback) cmd_rollback ;;
        cleanup)  cmd_cleanup ;;
        status)   cmd_status ;;
        setup)    cmd_setup ;;
        fix-nginx) cmd_fix_nginx ;;
        backup)      cmd_backup ;;
        restore)     cmd_restore "${RESTORE_FILE}" ;;
        list-backups) cmd_list_backups ;;
        start)    cmd_start ;;
        stop)     cmd_stop ;;
        restart)  cmd_restart ;;
        logs)     show_logs ;;
        *)        usage; exit 2 ;;
    esac
}

main "$@"
