#!/usr/bin/env python3
import json, socket, ssl, urllib.request, urllib.error
from urllib.parse import urlsplit
from pathlib import Path
e = dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#'))
hosts = {e['MATRIX_DOMAIN'], e['TURN_HOST']}
hosts.update(urlsplit(e[k]).hostname for k in ('SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL'))
missing = []
for host in sorted(hosts):
    try: socket.getaddrinfo(host, None)
    except socket.gaierror: missing.append(host)
if missing:
    raise SystemExit('DNS introuvable : ' + ', '.join(missing) + '\nConfigurer le DNS interne ou /etc/hosts sur le serveur et les clients. '
                     'TURN doit aussi être résolu depuis les conteneurs ; voir README.')
ctx = ssl.create_default_context(cafile='data/tls/ca.crt')
def get(url):
    with urllib.request.urlopen(url,context=ctx,timeout=15) as r:
        body=r.read(); print('OK',r.status,url); return body
well=json.loads(get('https://'+e['MATRIX_DOMAIN']+'/.well-known/matrix/client'))
assert well['m.homeserver']['base_url']==e['SYNAPSE_URL']
assert well['org.matrix.msc4143.rtc_foci'][0]['livekit_service_url']==e['RTC_URL']+'/livekit/jwt'
versions=json.loads(get(e['SYNAPSE_URL']+'/_matrix/client/versions'))
assert 'versions' in versions
assert b'<html' in get(e['ELEMENT_URL']).lower()
get(e['RTC_URL']+'/livekit/jwt/healthz')
for path in ('/_matrix/federation/v1/version','/_synapse/admin/v1/server_version'):
    try: get(e['SYNAPSE_URL']+path)
    except urllib.error.HTTPError as err: assert err.code==404
    else: raise SystemExit('Endpoint interdit exposé : '+path)
