#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
umask 077
[[ $EUID -eq 0 ]] || { echo 'Root requis pour lire les volumes.' >&2; exit 1; }
mkdir -p backups
out="$(mktemp -d "backups/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
# Refuser une sauvegarde ambiguë d'une stack déjà partiellement arrêtée.
for service in postgres synapse proxy jwt; do
  [[ -n $(dc ps --status running -q "$service") ]] || { echo "$service arrêté : abandon" >&2; exit 1; }
done
resume() { dc up -d postgres synapse jwt proxy; }
trap resume EXIT
# Couper les écritures et appels entrants avant la base et les médias.
dc stop proxy jwt synapse
dc exec -T postgres pg_dump -U synapse -d synapse --format=custom > "$out/synapse.dump"
# Ne pas archiver le répertoire PostgreSQL vivant : le dump fait autorité.
tar --numeric-owner -czf "$out/files.tar.gz" .env compose.yaml compose.acme.yaml configs scripts data/synapse data/tls data/caddy data/caddy-config data/acme
(cd "$out" && sha256sum synapse.dump files.tar.gz > SHA256SUMS)
echo "Sauvegarde cohérente : $out (contient secrets et données privées)."
