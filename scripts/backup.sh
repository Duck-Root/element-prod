#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
umask 077
[[ $EUID -eq 0 ]] || { echo 'Root requis pour lire les volumes.' >&2; exit 1; }
# Ne pas copier le TLS ou arrêter JWT pendant une installation de certificat.
exec 9>data/tls-install.lock
flock -n 9 || { echo 'Une installation TLS ou une sauvegarde est déjà en cours.' >&2; exit 1; }
mkdir -p backups
out="$(mktemp -d "backups/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
for service in postgres synapse jwt; do
  [[ -n $(dc ps --status running -q "$service") ]] || { echo "$service arrêté : abandon" >&2; exit 1; }
done
# Nginx est sur l’hôte : ne pas arrêter ses autres vhosts.
# Synapse arrêté coupe les écritures Matrix pendant le dump et l’archive médias.
resume() { dc up -d postgres synapse jwt; }
trap resume EXIT
dc stop jwt synapse
dc exec -T postgres pg_dump -U synapse -d synapse --format=custom > "$out/synapse.dump"
tar --numeric-owner -czf "$out/files.tar.gz" .env compose.yaml configs scripts data/synapse data/tls
(cd "$out" && sha256sum synapse.dump files.tar.gz > SHA256SUMS)
echo "Sauvegarde cohérente : $out (secrets inclus). Nginx hôte n’a pas été arrêté."
echo 'Sauvegarder aussi /etc/nginx et la configuration de votre gestionnaire de certificats externe.'
