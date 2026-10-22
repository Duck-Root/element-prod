#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
# Saisie interactive : aucun mot de passe dans argv, .env ou l'historique.
# L'utilitaire Synapse refuse un compte existant ; aucun compte n'est réinitialisé.
if [[ $# -gt 1 || ( $# -eq 1 && $1 != --admin ) ]]; then
  echo 'Usage : scripts/create-user.sh [--admin]' >&2; exit 2
fi
args=(--no-admin)
[[ ${1:-} != --admin ]] || args=(--admin)
dc exec synapse register_new_matrix_user -c /config/homeserver.yaml "${args[@]}" http://localhost:8008
