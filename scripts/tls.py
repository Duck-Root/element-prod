#!/usr/bin/env python3
"""Certificats HTTP-01 pour une installation neuve à trois domaines."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

os.chdir(Path(__file__).resolve().parent.parent)
os.umask(0o077)
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['issue', 'renew'])
parser.add_argument('--email')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Exécuter avec sudo.')
env = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
           if line.strip() and not line.lstrip().startswith('#'))
# Vérifier le profil avant toute demande auprès de Let's Encrypt.
for key in ('MATRIX_DOMAIN', 'TURN_HOST', 'SERVER_IP', 'COMPOSE_PROJECT_NAME',
            'SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL'):
    if not env.get(key):
        raise SystemExit(f'{key} est absent ou vide dans .env.')
origins = {}
for key in ('SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL'):
    url = urlsplit(env[key])
    if (url.scheme != 'https' or not url.hostname or url.path not in ('', '/')
            or url.query or url.fragment or url.username or url.port not in (None, 443)):
        raise SystemExit(f'{key} doit être une origine HTTPS sans chemin, sur le port 443.')
    origins[key] = url.hostname
if origins['SYNAPSE_URL'] != env['MATRIX_DOMAIN']:
    raise SystemExit('Ce profil neuf attend SYNAPSE_URL=https://' + env['MATRIX_DOMAIN'])
if len(set(origins.values())) != 3:
    raise SystemExit('Ce profil neuf exige trois noms distincts pour Matrix, Element et RTC.')
if any(host == 'exemple.fr' or host.endswith('.exemple.fr')
       for host in [env['MATRIX_DOMAIN'], env['TURN_HOST'], *origins.values()]):
    raise SystemExit('Remplacer tous les domaines exemple.fr du modèle dans .env, y compris TURN_HOST.')
if env['SERVER_IP'] == '192.0.2.10':
    raise SystemExit('Remplacer SERVER_IP par votre IPv4 publique réelle.')
hosts = sorted({env['MATRIX_DOMAIN'], env['TURN_HOST']} |
               {urlsplit(env[key]).hostname for key in ('SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL')})
if any(not host or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in host) for host in hosts):
    raise SystemExit('Noms DNS invalides.')
acme = Path('data/acme')
acme.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (acme/'operation.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Une opération ACME est déjà en cours.')
email_path = acme/'email'
if args.email:
    email_path.write_text(args.email.strip()+'\n')
if not email_path.exists():
    raise SystemExit('Première émission : ajouter --email administrateur@votre-domaine.fr')
crt = Path('data/tls/server.crt')
if args.mode == 'issue' and crt.exists():
    raise SystemExit('Certificat existant : utiliser renew.')
if args.mode == 'renew':
    if not crt.exists():
        raise SystemExit('Certificat absent : utiliser issue.')
    if subprocess.run(['openssl', 'x509', '-in', str(crt), '-checkend', str(30*86400), '-noout'],
                      stdout=subprocess.DEVNULL).returncode == 0:
        print('Certificat valide plus de 30 jours : aucune interruption.')
        raise SystemExit(0)

def run(*cmd):
    return subprocess.run(cmd, check=True)

stopped = False
try:
    if args.mode == 'renew':
        run('docker', 'compose', 'stop', 'proxy')
        stopped = True
    cmd = ['docker', 'compose', '-p', env['COMPOSE_PROJECT_NAME']+'-acme',
           '-f', 'compose.acme.yaml', 'run', '--rm', '--service-ports', 'acme',
           '--path', '/acme', '--accept-tos', '--email', email_path.read_text().strip(),
           '--key-type', 'rsa3072', '--http', '--http.port', ':80']
    for host in hosts:
        cmd += ['--domains', host]
    cmd += ['run'] if args.mode == 'issue' else ['renew', '--days', '30']
    run(*cmd)
    source = acme/'certificates'/hosts[0]
    source_crt = Path(str(source)+'.crt')
    source_key = Path(str(source)+'.key')
    def openssl(*cmd):
        return subprocess.check_output(['openssl', *cmd])
    if openssl('x509', '-in', str(source_crt), '-pubkey', '-noout') != openssl('pkey', '-in', str(source_key), '-pubout'):
        raise SystemExit('Clé et certificat différents.')
    run('openssl', 'x509', '-in', str(source_crt), '-checkend', '86400', '-noout')
    roots = Path('/etc/ssl/certs/ca-certificates.crt')
    for host in hosts:
        run('openssl', 'verify', '-CAfile', str(roots), '-untrusted', str(source_crt),
            '-verify_hostname', host, str(source_crt))
    tls = Path('data/tls')
    tls.mkdir(parents=True, exist_ok=True, mode=0o755)
    if crt.exists():
        import datetime
        backup = acme/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup.mkdir(parents=True, mode=0o700)
        for name in ('server.crt', 'server.key', 'ca.crt'):
            shutil.copy2(tls/name, backup/name)
    for src, name in [(source_crt, 'server.crt'), (source_key, 'server.key')]:
        tmp = tls/(name+'.new')
        shutil.copyfile(src, tmp)
        tmp.chmod(0o644)
        os.replace(tmp, tls/name)
    # Ce bundle reste inchangé lors des renouvellements : JWT le monte comme fichier.
    if not (tls/'ca.crt').exists():
        shutil.copyfile(roots, tls/'ca.crt')
        (tls/'ca.crt').chmod(0o644)
    if args.mode == 'renew':
        run('docker', 'compose', 'restart', 'coturn')
    print('Certificat public vérifié et installé.')
except subprocess.CalledProcessError as exc:
    raise SystemExit(f'Échec de la commande (code {exc.returncode}). Corriger la cause indiquée ci-dessus avant de réessayer.') from None
finally:
    if stopped:
        run('docker', 'compose', 'start', 'proxy')
