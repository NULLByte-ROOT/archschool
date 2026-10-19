#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="archschool"
BRANCH="main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/backend/.env"
DB_URL="postgresql://postgres:postgres@archschool_db:5432/archschool_db"

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

compose() {
    run_privileged docker compose -p "${PROJECT_NAME}" "$@"
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
    if run_git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if ! run_git remote get-url origin >/dev/null 2>&1; then
            warn "No 'origin' remote is configured."
            local repo_url
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

    warn "No Git repository found in ${SCRIPT_DIR}."
    local repo_url
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
                printf 'ADMIN_CODE=change-me\n'
            } > "${ENV_FILE}"
            info "Created a new backend/.env."
        fi
    fi

    if grep -q '^DATABASE_URL=' "${ENV_FILE}"; then
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|" "${ENV_FILE}"
    else
        printf 'DATABASE_URL=%s\n' "${DB_URL}" >> "${ENV_FILE}"
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
}

configure_domain() {
    echo
    info "Domain setup (optional). ArchSchool listens only on port 6241."
    local domain
    read -r -p "Domain name (e.g. arch.example.com, leave blank to skip): " domain || true

    domain="${domain#http://}"
    domain="${domain#https://}"
    domain="${domain%/}"

    if [[ -z "${domain}" ]]; then
        warn "No domain configured. Use http://SERVER_IP:6241 to access the app."
        return 0
    fi

    if [[ ! "${domain}" =~ ^[A-Za-z0-9.-]+$ ]]; then
        warn "Invalid domain name. Skipping domain configuration."
        return 0
    fi

    local cors="[\"http://localhost:5173\",\"http://127.0.0.1:5173\",\"https://${domain}\",\"http://${domain}\"]"
    if grep -q '^CORS_ORIGINS=' "${ENV_FILE}"; then
        sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${cors}|" "${ENV_FILE}"
    else
        printf 'CORS_ORIGINS=%s\n' "${cors}" >> "${ENV_FILE}"
    fi

    success "CORS_ORIGINS updated for ${domain}."
    info "Point your existing Nginx/Apache virtual host for ${domain} to http://127.0.0.1:6241."
    info "Ports 80/443 are left untouched, so other projects remain isolated."
}

initial_setup() {
    echo
    printf "${BOLD}=== ArchSchool Initial Setup ===${NC}\n"
    check_sudo
    install_docker
    pull_code
    ensure_env
    configure_domain

    info "Building and starting ArchSchool containers..."
    compose up -d --build --remove-orphans

    success "Initial setup complete."
    info "Frontend: http://SERVER_IP:6241"
    info "Change ADMIN_CODE in backend/.env before creating admin users."
    echo
    compose ps
}

start_containers() {
    check_sudo
    ensure_env
    info "Starting ArchSchool..."
    compose up -d
    success "ArchSchool started."
    compose ps
}

stop_containers() {
    check_sudo
    info "Stopping ArchSchool (volumes and data are preserved)..."
    compose stop
    success "ArchSchool stopped."
}

restart_containers() {
    check_sudo
    info "Restarting ArchSchool..."
    compose restart
    success "ArchSchool restarted."
    compose ps
}

update_from_github() {
    check_sudo

    if ! run_git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        error "This directory is not a Git repository. Run the initial setup first."
        return 1
    fi

    if ! run_git remote get-url origin >/dev/null 2>&1; then
        error "No 'origin' remote is configured. Add it with: git remote add origin <url>"
        return 1
    fi

    info "Pulling latest code from GitHub (origin/${BRANCH})..."
    run_git pull origin "${BRANCH}"

    ensure_env

    info "Rebuilding and restarting containers..."
    compose up -d --build --remove-orphans

    info "Cleaning up unused Docker images..."
    run_privileged docker image prune -f

    success "Update complete. ArchSchool is running the latest code."
    echo
    compose ps
}

show_status() {
    check_sudo
    echo
    printf "${BOLD}=== ArchSchool container status ===${NC}\n"
    compose ps
    echo
    info "Port mapping: host 6241 -> frontend container 80"
    info "Database container archschool_db is internal-only (no host port)."
}

show_logs() {
    check_sudo
    echo
    echo "  1) All services"
    echo "  2) Frontend"
    echo "  3) Backend"
    echo "  4) Database"
    echo "  0) Back"
    local choice
    read -r -p "Select logs to follow: " choice || return 0
    case "${choice}" in
        1) compose logs -f --tail=200 || true ;;
        2) compose logs -f --tail=200 frontend || true ;;
        3) compose logs -f --tail=200 backend || true ;;
        4) compose logs -f --tail=200 db || true ;;
        0) return 0 ;;
        *) warn "Invalid option." ;;
    esac
}

show_menu() {
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
    echo "  ArchSchool deployment manager"
    echo "  ------------------------------------------------"
    echo "  1) Initial setup (Docker, code, domain, start)"
    echo "  2) Start containers"
    echo "  3) Stop containers"
    echo "  4) Restart containers"
    echo "  5) Update from GitHub (git pull + rebuild)"
    echo "  6) Show container status"
    echo "  7) View live logs"
    echo "  0) Exit"
    echo
}

main() {
    check_sudo
    while true; do
        show_menu
        local choice
        if ! read -r -p "Select an option [0-7]: " choice; then
            echo
            exit 0
        fi
        case "${choice}" in
            1) initial_setup || warn "Initial setup failed. Check the output above." ;;
            2) start_containers || warn "Could not start ArchSchool." ;;
            3) stop_containers || warn "Could not stop ArchSchool." ;;
            4) restart_containers || warn "Could not restart ArchSchool." ;;
            5) update_from_github || warn "Update failed. Check the output above." ;;
            6) show_status || warn "Could not read container status." ;;
            7) show_logs || true ;;
            0) printf "${GREEN}Bye.${NC}\n"; exit 0 ;;
            *) warn "Invalid option: ${choice}" ;;
        esac
        echo
        read -r -p "Press Enter to return to the menu..." _ || true
    done
}

main "$@"
