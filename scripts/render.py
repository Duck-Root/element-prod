#!/usr/bin/env python3
"""Rendu sans dépendance Python externe ; JSON est également du YAML valide."""
import hashlib, ipaddress, json, os, pathlib, re, secrets, subprocess
from urllib.parse import urlsplit
import argparse, shutil, datetime
os.chdir(pathlib.Path(__file__).resolve().parent.parent)
parser = argparse.ArgumentParser()
parser.add_argument("--update", action="store_true", help="Sauvegarder puis régénérer sans changer l’identité Matrix")
args = parser.parse_args()
P = pathlib.Path
os.umask(0o077)
p = P('.env')
s = p.read_text()
e = {}
for line in s.splitlines():
    if line.strip() and not line.lstrip().startswith('#'):
        k, v = line.split('=', 1)
        e[k.strip()] = v.strip()

if not re.fullmatch(r'[a-z0-9.-]+', e['MATRIX_DOMAIN']):
    raise SystemExit('MATRIX_DOMAIN invalide')
hosts = [e['MATRIX_DOMAIN'], e['TURN_HOST']]
for k in ('SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL'):
    u = urlsplit(e[k])
    if u.scheme != 'https' or not u.hostname or u.path not in ('', '/') or u.query or u.fragment or u.username:
        raise SystemExit(f'{k}: origine HTTPS requise, sans chemin')
    if u.port not in (None, 443):
        raise SystemExit(f'{k}: HTTPS public attendu sur le port 443')
    hosts.append(u.hostname)
if any(urlsplit(e[k]).hostname != e['MATRIX_DOMAIN'] for k in ('SYNAPSE_URL','ELEMENT_URL','RTC_URL')) or e['TURN_HOST'] != e['MATRIX_DOMAIN']:
    raise SystemExit('Profil domaine unique : SYNAPSE_URL, ELEMENT_URL et RTC_URL=https://MATRIX_DOMAIN ; TURN_HOST=MATRIX_DOMAIN')
if e['MATRIX_DOMAIN'] == 'exemple.fr' or e['MATRIX_DOMAIN'].endswith('.exemple.fr'):
    raise SystemExit('Remplacer le domaine exemple.fr avant le rendu')
if not all(re.fullmatch(r'[a-z0-9.-]+', h) for h in hosts):
    raise SystemExit('Noms DNS invalides')
ipaddress.IPv4Address(e['SERVER_IP']); ipaddress.IPv4Address(e['BIND_IP'])
if e['SERVER_IP'] == '192.0.2.10':
    raise SystemExit('Renseigner SERVER_IP dans .env avant de continuer')
for k in ('LIVEKIT_TCP_PORT LIVEKIT_UDP_START LIVEKIT_UDP_END TURN_PORT TURN_TLS_PORT TURN_UDP_START TURN_UDP_END').split():
    if not 1 <= int(e[k]) <= 65535: raise SystemExit(f'Port invalide : {k}')
a,b,c,d = [int(e[k]) for k in ('LIVEKIT_UDP_START','LIVEKIT_UDP_END','TURN_UDP_START','TURN_UDP_END')]
if a>b or c>d or max(a,c)<=min(b,d): raise SystemExit('Plages UDP invalides ou chevauchantes')
# Valider les ports locaux et l'identité avant toute écriture.
local_ports = {'SYNAPSE_HTTP_PORT':'18008','ELEMENT_HTTP_PORT':'18080','JWT_HTTP_PORT':'18081','LIVEKIT_HTTP_PORT':'17880','KETESA_HTTP_PORT':'18082'}
for key, default in local_ports.items():
    e.setdefault(key, default)
    if not e[key].isdigit() or not 1024 <= int(e[key]) <= 65535:
        raise SystemExit(f'{key}: port local invalide')
if len({int(e[key]) for key in local_ports}) != len(local_ports):
    raise SystemExit('Les cinq ports HTTP locaux doivent être distincts')
public_tcp = {int(e[key]) for key in ('LIVEKIT_TCP_PORT','TURN_PORT','TURN_TLS_PORT')}
if public_tcp & {int(e[key]) for key in local_ports}:
    raise SystemExit('Un port HTTP local chevauche un port TCP public')
# Ports TCP publiés par les autres applications du serveur : ne pas les réutiliser.
reserved_tcp = set()
for item in e.get('RESERVED_TCP_PORTS', '').split(','):
    item = item.strip()
    if not item:
        continue
    if not item.isdigit() or not 1 <= int(item) <= 65535:
        raise SystemExit('RESERVED_TCP_PORTS : liste de ports TCP de 1 à 65535, séparés par des virgules')
    reserved_tcp.add(int(item))
published_tcp = {int(e[key]) for key in local_ports} | {int(e[key]) for key in ('LIVEKIT_TCP_PORT','TURN_PORT','TURN_TLS_PORT')}
conflicts = reserved_tcp & published_tcp
if conflicts:
    raise SystemExit('Ports TCP déjà réservés sur le serveur : '+', '.join(map(str,sorted(conflicts)))+'. Choisir d’autres ports Matrix.')
old_config = P('configs/generated/synapse/homeserver.yaml')
if old_config.exists() and json.loads(old_config.read_text())['server_name'] != e['MATRIX_DOMAIN']:
    raise SystemExit('Refus de modifier server_name sur une installation initialisée')
if args.update:
    backup = P('backups') / ('configuration-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(p, backup/'environment')
    if P('configs/generated').exists():
        shutil.copytree('configs/generated', backup/'generated')
for k in ('POSTGRES_PASSWORD REGISTRATION_SHARED_SECRET MACAROON_SECRET FORM_SECRET '
          'LIVEKIT_KEY LIVEKIT_SECRET TURN_SECRET AS_TOKEN HS_TOKEN').split():
    if not e.get(k):
        e[k] = secrets.token_hex(32)
        s = re.sub(r'^' + k + r'=.*$', k + '=' + e[k], s, flags=re.M)
    if not re.fullmatch('[a-fA-F0-9]{32,128}', e[k]):
        raise SystemExit(f'{k}: utiliser 32 à 128 caractères hexadécimaux')
p.write_text(s); p.chmod(0o600)
root = P('configs/generated'); root.mkdir(parents=True, exist_ok=True)
fingerprint = hashlib.sha256(p.read_bytes()).hexdigest()
marker = root/'environment.sha256'
if not args.update and marker.exists() and marker.read_text().strip() != fingerprint:
    raise SystemExit('Configuration .env modifiée : aucun fichier généré écrasé. Voir README (reconfiguration).')
def write(name, value):
    path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent != root: path.parent.chmod(0o755)
    content = value if isinstance(value, str) else json.dumps(value, indent=2)+'\n'
    if not args.update and path.exists() and path.read_text() != content:
        raise SystemExit(f'{path} modifié : refus de l’écraser')
    if not path.exists() or args.update: path.write_text(content)
    # Répertoire parent protégé ; lecture nécessaire aux UID des conteneurs.
    path.chmod(0o644)
for data_dir in ('synapse','tls'):
    P('data/'+data_dir).mkdir(parents=True, exist_ok=True)
P('data/synapse').chmod(0o770)
if os.geteuid() == 0:
    try: os.chown('data/synapse',991,991)
    except OSError as exc: raise SystemExit(f'Attribution UID 991 impossible sur ce système de fichiers : {exc}')
elif P('data/synapse').stat().st_uid != 991:
    raise SystemExit('Exécuter init en root (chown du volume Synapse UID 991 requis).')
P('data').chmod(0o700)
tls = P('data/tls')
tls.chmod(0o755)
if e['TLS_MODE'] == 'local':
    if not (tls/'server.crt').exists():
        if any(tls.iterdir()): raise SystemExit('TLS incomplet : refus de remplacer les clés existantes')
        def openssl(*args): subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        openssl('req','-x509','-newkey','rsa:3072','-nodes','-days','3650','-subj','/CN=Matrix POC Local CA','-keyout',str(tls/'ca.key'),'-out',str(tls/'ca.crt'),'-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
        openssl('req','-newkey','rsa:3072','-nodes','-subj',f"/CN={hosts[0]}",'-keyout',str(tls/'server.key'),'-out',str(tls/'server.csr'))
        (tls/'extensions.cnf').write_text('subjectAltName='+','.join('DNS:'+h for h in sorted(set(hosts)))+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
        openssl('x509','-req','-in',str(tls/'server.csr'),'-CA',str(tls/'ca.crt'),'-CAkey',str(tls/'ca.key'),'-CAcreateserial','-days','365','-extfile',str(tls/'extensions.cnf'),'-out',str(tls/'server.crt'))
elif e['TLS_MODE'] != 'provided': raise SystemExit('TLS_MODE : local ou provided')
for f in ('ca.crt','server.crt','server.key'):
    if not (tls/f).is_file(): raise SystemExit(f'Fournir data/tls/{f}')
# coturn tourne sous un UID spécifique ; le répertoire hôte reste privé.
(tls/'server.key').chmod(0o644)
(tls/'server.crt').chmod(0o644); (tls/'ca.crt').chmod(0o644)
well = {'m.homeserver':{'base_url':e['SYNAPSE_URL']}, 'org.matrix.msc4143.rtc_foci':[{'type':'livekit','livekit_service_url':e['RTC_URL']+'/livekit/jwt'}]}
write('nginx/client.json',well)
write('nginx/server.json',{'m.server':e['MATRIX_DOMAIN']+':443'})
write('synapse/rtc-registration.yaml',{'id':'matrixrtc','as_token':e['AS_TOKEN'],'hs_token':e['HS_TOKEN'],'sender_localpart':'_lk_jwt_service','url':None,'namespaces':{'users':[{'exclusive':False,'regex':'.*'}]},'io.element.msc4502.scopes':['urn:matrix:client:io.element.msc4502:rooms:is_joined'],'io.element.msc4512.proxy_prefix':'rtc/livekit','io.element.msc4512.proxy_url':'http://jwt:8080'})
write('synapse/homeserver.yaml', {
 'server_name':e['MATRIX_DOMAIN'],'public_baseurl':e['SYNAPSE_URL']+'/', 'pid_file':'/data/homeserver.pid',
 'listeners':[{'port':8008,'type':'http','tls':False,'x_forwarded':True,'bind_addresses':['0.0.0.0'],'resources':[{'names':['client','openid'],'compress':False}]}],
 'database':{'name':'psycopg2','args':{'user':'synapse','password':e['POSTGRES_PASSWORD'],'database':'synapse','host':'postgres','cp_min':5,'cp_max':10}},
 'media_store_path':'/data/media_store','signing_key_path':'/data/signing.key','log_config':'/config/log.config',
 'registration_shared_secret':e['REGISTRATION_SHARED_SECRET'],'macaroon_secret_key':e['MACAROON_SECRET'],'form_secret':e['FORM_SECRET'],
 'enable_registration':False,'allow_guest_access':False,'report_stats':False,'trusted_key_servers':[],
 'federation_domain_whitelist':[],'send_federation':False,'allow_public_rooms_over_federation':False,'allow_profile_lookup_over_federation':False,
 'url_preview_enabled':False,'max_upload_size':'100M','suppress_key_server_warning':True,
 'experimental_features':{'msc3266_enabled':True,'msc4143_enabled':True,'msc4222_enabled':True,'msc4502_enabled':True,'msc4512_enabled':True},
 'max_event_delay_duration':'24h','rc_message':{'per_second':0.5,'burst_count':30},'rc_delayed_event_mgmt':{'per_second':1,'burst_count':20},
 'matrix_rtc':{'transports':[{'type':'livekit','livekit_service_url':e['RTC_URL']+'/livekit/jwt'}]},
 'app_service_config_files':['/config/rtc-registration.yaml'],
 'turn_uris':[f"turn:{e['TURN_HOST']}:{e['TURN_PORT']}?transport=udp",f"turns:{e['TURN_HOST']}:{e['TURN_TLS_PORT']}?transport=tcp"],
 'turn_shared_secret':e['TURN_SECRET'],'turn_user_lifetime':'1h','turn_allow_guests':False})
write('synapse/log.config',{'version':1,'formatters':{'simple':{'format':'%(asctime)s %(levelname)s %(name)s %(message)s'}},'handlers':{'console':{'class':'logging.StreamHandler','formatter':'simple'}},'root':{'level':'INFO','handlers':['console']},'disable_existing_loggers':False})
write('element/config.json',{'default_server_config':well,'disable_custom_urls':True,'disable_guests':True,'disable_3pid_login':True,'default_federate':False,'brand':'Element','element_call':{'use_exclusively':True},'integrations_ui_url':None,'integrations_rest_url':None,'integrations_widgets_urls':[],'room_directory':{'servers':[e['MATRIX_DOMAIN']]},'permalink_prefix':e['ELEMENT_URL'],'setting_defaults':{'UIFeature.registration':False,'UIFeature.identityServer':False}})
write('livekit/livekit.yaml',{'port':7880,'bind_addresses':['0.0.0.0'],'rtc':{'tcp_port':int(e['LIVEKIT_TCP_PORT']),'port_range_start':a,'port_range_end':b,'node_ip':e['SERVER_IP'],'use_external_ip':False,'stun_servers':[e['TURN_HOST']+':'+e['TURN_PORT']],'turn_servers':[{'host':e['TURN_HOST'],'port':int(e['TURN_PORT']),'protocol':'udp','secret':e['TURN_SECRET']},{'host':e['TURN_HOST'],'port':int(e['TURN_TLS_PORT']),'protocol':'tls','secret':e['TURN_SECRET']}]},'keys':{e['LIVEKIT_KEY']:e['LIVEKIT_SECRET']},'room':{'auto_create':False,'max_participants':10},'webhook':{'api_key':e['LIVEKIT_KEY'],'urls':['http://jwt:8080/sfu_webhook']},'logging':{'level':'info'}})
write('jwt.env','\n'.join(f'{k}={v}' for k,v in {'LIVEKIT_URL':e['RTC_URL'].replace('https://','wss://')+'/livekit/sfu','LIVEKIT_KEY':e['LIVEKIT_KEY'],'LIVEKIT_SECRET':e['LIVEKIT_SECRET'],'LIVEKIT_JWT_BIND':':8080','LIVEKIT_FULL_ACCESS_HOMESERVERS':e['MATRIX_DOMAIN'],'LIVEKIT_AS_REGISTRATION_FILE':'/registration.yaml','LIVEKIT_HS_SERVER_NAME':e['MATRIX_DOMAIN'],'LIVEKIT_CS_API_URL_OVERRIDES':e['MATRIX_DOMAIN']+'=http://synapse:8008','LIVEKIT_SANITY_CHECK_INTERVAL_SECONDS':'30'}.items())+'\n')
write('coturn/turnserver.conf',f'''listening-port={e['TURN_PORT']}
tls-listening-port={e['TURN_TLS_PORT']}
listening-ip=0.0.0.0
external-ip={e['SERVER_IP']}
min-port={c}
max-port={d}
realm={e['TURN_HOST']}
fingerprint
use-auth-secret
static-auth-secret={e['TURN_SECRET']}
cert=/tls/server.crt
pkey=/tls/server.key
no-multicast-peers
no-tcp-relay
user-quota=20
total-quota=100
stale-nonce=600
no-software-attribute
log-file=stdout
simple-log
''')
write('ketesa/config.json', {'restrictBaseUrl':e['SYNAPSE_URL'], 'wellKnownDiscovery':False, 'asManagedUsers':['^@_lk_jwt_service:']})
marker.write_text(fingerprint+'\n')
print('Configurations applicatives générées ; secrets conservés. Découverte : configs/generated/nginx/client.json et server.json.')
print('Le reverse proxy externe et ses listes d’accès restent gérés par l’exploitant.')
