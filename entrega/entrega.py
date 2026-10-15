"""Executor de entregas Minha Lenda (09/10/2026).
Pega os pedidos pagos no Worker, escreve a história com o motor do Worker (plano -> texto -> crítica),
ilustra com a foto (ficha, capa e até 5 ilustrações), monta o PDF A5 (Chromium), narra com Gemini TTS
(voz por coleção), monta o audiolivro com vinhetas e trilha, sobe tudo no R2 e marca como entregue.

Uso: python3 entrega.py                # todos os pedidos pagos
     python3 entrega.py ML-ABC123      # um pedido (qualquer status)
Precisa: ffmpeg com rubberband, playwright (chromium), as chaves em Adm\\ (Tokens_APIs_IA.txt e Token Admin Minha Lenda.txt).
Variáveis opcionais: ML_ADM_DIR (pasta Adm), ML_SITE (padrão https://minhalenda.com.br).
"""
import base64, concurrent.futures as cf, hashlib, html, io, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.request, wave
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import livro as livro_mod

HERE = pathlib.Path(__file__).parent
ADM = pathlib.Path(os.environ.get('ML_ADM_DIR', '/mnt/user-data/uploads/Minha Lenda/Adm'))
SITE = os.environ.get('ML_SITE', 'https://minhalenda.com.br')
CACHE = pathlib.Path(os.environ.get('ML_CACHE', '/home/claude/ml/cache_entrega')); CACHE.mkdir(parents=True, exist_ok=True)
FONTS = pathlib.Path(os.environ.get('ML_FONTS', str(HERE / 'fonts') if (HERE / 'fonts').exists() else '/root/.fonts'))
OUT = pathlib.Path(os.environ.get('ML_OUT', '/home/claude/ml/entregas'))
PUBLICO = bool(os.environ.get('CI'))  # no GitHub Actions o log é público: nada de nome de criança, título ou link
MUSICA = HERE / 'trilha_fecho.wav'
VOZ = {'0': ('Sulafat', 1.0), '1': ('Puck', 0.93), '2': ('Charon', 0.95)}  # voz Gemini e andamento por coleção (decisões 39 e 41)
ESTILO_TTS = "Read aloud in Brazilian Portuguese as a warm, expressive children's storyteller, at a calm, unhurried pace:"

def gemini_key():
    if os.environ.get('GEMINI_KEY'): return os.environ['GEMINI_KEY']
    t = (ADM / 'Tokens_APIs_IA.txt').read_text(encoding='utf-8', errors='ignore').splitlines()
    for i, l in enumerate(t):
        if l.lower().startswith('gemini'):
            rest = l.split(':', 1)[1].strip() if ':' in l else ''
            if rest: return rest
            return next(x.strip() for x in t[i + 1:] if x.strip())
    raise SystemExit('chave Gemini não encontrada')

_OIDC = {'t': 0, 'v': None}
def oidc():
    """No GitHub Actions: token OIDC do workflow (vale minutos), renovado a cada 4 min. Nenhum segredo fica no repositório."""
    if time.time() - _OIDC['t'] > 240:
        u = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=minhalenda'
        r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}), timeout=30))
        print('::add-mask::' + r['value'], flush=True)
        _OIDC.update(t=time.time(), v='Bearer ' + r['value'])
    return _OIDC['v']
CI_OIDC = bool(os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL'))

def admin_auth():
    if CI_OIDC: return 'oidc'
    if os.environ.get('ML_ADMIN'): return os.environ['ML_ADMIN']
    t = (ADM / 'Token Admin Minha Lenda.txt').read_text(encoding='utf-8', errors='ignore')
    for cand in sorted(set(re.findall(r'[^\s:;,"\']{10,}', t)), key=len, reverse=True):
        h = 'Basic ' + base64.b64encode(f'admin:{cand}'.encode()).decode()
        try:
            urllib.request.urlopen(urllib.request.Request(SITE + '/admin/api/pedidos?status=pago', headers={'authorization': h, 'user-agent': 'MinhaLenda-Executor/1.0'}), timeout=30)
            return h
        except urllib.error.HTTPError as e:
            if e.code != 401: return h
    raise SystemExit('senha do admin não encontrada')

AUTH = None
# custo por livro (14/10): tokens por modelo, imagens e áudio; o admin converte em R$ com a tabela de preços
USO = {}
def uso(model, tin=0, tout=0, n=1, img=0):
    u = USO.setdefault(model, {'in': 0, 'out': 0, 'n': 0, 'img': 0})
    u['in'] += int(tin or 0); u['out'] += int(tout or 0); u['n'] += n; u['img'] += img
def uso_resp(r):
    for x in (r or {}).get('usage') or []: uso(x.get('model', '?'), x.get('in'), x.get('out'), img=int(x.get('img') or 0))
    return r
def api(path, body=None, method=None, raw=None, ctype=None, tries=3, timeout=300):
    for k in range(tries):
        try:
            data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
            h = {'authorization': oidc() if AUTH == 'oidc' else AUTH, 'user-agent': 'MinhaLenda-Executor/1.0'}
            if data is not None: h['content-type'] = ctype or 'application/json'
            r = urllib.request.urlopen(urllib.request.Request(SITE + path, data=data, headers=h, method=method or ('POST' if data is not None else 'GET')), timeout=timeout)
            return json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            msg = e.read()[:400].decode(errors='ignore')
            if k == tries - 1 or e.code in (400, 401, 403, 404): raise RuntimeError(f'{path} {e.code} {msg}')
        except Exception as e:
            if k == tries - 1: raise
        time.sleep(4 * (k + 1))

def log(*a, privado=False):
    if PUBLICO and privado: a = a[:1] + ('[detalhes omitidos no log público]',)
    print(time.strftime('%H:%M:%S'), *a, flush=True)

# ---------------- história ----------------
def escrever(dna):
    pl = uso_resp(api('/admin/api/plano', dna))
    if 'plan' not in pl: raise RuntimeError('motor/plano: ' + str(pl.get('erro') or pl)[:300])
    plan = pl['plan']
    tx = uso_resp(api('/admin/api/texto', {'dna': dna, 'plan': plan}))
    if 'txt' not in tx: raise RuntimeError('motor/texto: ' + str(tx.get('erro') or tx)[:300])
    montar = lambda: {**plan, 'paginas': tx['txt'].get('paginas') or [], 'gancho_proximo': tx['txt'].get('gancho_proximo') or ''}
    cr = uso_resp(api('/admin/api/critica', {'dna': dna, 'h': montar()})); rev = 0
    longo = lambda: any('Texto longo' in str(x) for x in (cr.get('probs') or []))
    # tamanho travado por faixa (09/10): texto longo ganha uma revisão a mais só para cortar
    while not cr.get('aprovada') and rev < (2 if dna.get('enredo_livre') or longo() else 1):
        tx = uso_resp(api('/admin/api/texto', {'dna': dna, 'plan': plan, 'rev': {'probs': cr.get('probs'), 'anterior': tx['txt'].get('paginas')}}))
        cr = uso_resp(api('/admin/api/critica', {'dna': dna, 'h': montar()})); rev += 1
    h = montar()
    reais = [e['nome'].lower() for e in dna.get('elenco') or []]
    for e in h.get('elenco_visual') or []:
        if any(n.split(' ')[-1] in str(e.get('nome', '')).lower() for n in reais): e['real'] = True
    if dna.get('dedicatoria'): h['dedicatoria'] = dna['dedicatoria']
    media = (cr.get('crit') or {}).get('media')
    log('texto ok:', h.get('titulo'), '| páginas', len(h['paginas']), '| revisões', rev, '| nota', media, privado=True)
    return h, cr.get('crit') or {}

# ---------------- imagens ----------------
def jpeg_b64(b64, maxw=768, q=86):
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB'); im.thumbnail((maxw, maxw))
    o = io.BytesIO(); im.save(o, 'JPEG', quality=q); return base64.b64encode(o.getvalue()).decode()

def ilustrar(h, dna, foto, estilo, od):
    f = uso_resp(api('/admin/api/imagem', {'tipo': 'ficha', 'foto': foto, 'estilo': estilo, 'figurino': h.get('figurino_heroi_en'), 'nome': dna['nome']}))
    ficha = jpeg_b64(f['img'])
    ev = h.get('elenco_visual') or []
    def quem_de(nomes): return [e for e in ev if any(n and e.get('nome') and (e['nome'] in n or n in e['nome']) for n in (nomes or []))][:2]
    jobs = [('capa', {'tipo': 'capa', 'cena': h.get('capa_cena_en'), 'elenco': [e for e in ev if not e.get('real')][:1]})]
    for i, il in enumerate((h.get('ilustracoes') or [])[:5]):
        jobs.append((f'il_{i + 1}', {'tipo': 'pagina', 'cena': il.get('cena_en'), 'elenco': quem_de(il.get('quem')), 'pagina': il.get('pagina')}))
    def run(j):
        nome, extra = j; pagina = extra.pop('pagina', None)
        for tent in range(3):
            try:
                r = uso_resp(api('/admin/api/imagem', {**extra, 'foto': foto, 'ficha': ficha, 'estilo': estilo, 'figurino': h.get('figurino_heroi_en'), 'mundo': h.get('mundo_visual_en') or '', 'nome': dna['nome']}, tries=1))
                im = Image.open(io.BytesIO(base64.b64decode(r['img']))).convert('RGB'); im.thumbnail((1600, 1600))
                im.save(od / f'{nome}.jpg', 'JPEG', quality=87, optimize=True, progressive=True)
                return nome, pagina
            except Exception as e:
                log('imagem falhou', nome, tent, str(e)[:160]); time.sleep(5)
        return None, pagina
    with cf.ThreadPoolExecutor(3) as ex: res = list(ex.map(run, jobs))
    if not (od / 'capa.jpg').exists(): raise RuntimeError('capa não foi gerada')
    ilus = [{'pagina': int(p), 'arquivo': f'{n}.jpg'} for n, p in res if n and n != 'capa' and p]
    log('imagens ok:', 1 + len(ilus))
    return ilus

# PDF, páginas, impressão e gráfica: ver livro.py (diagramação única, 14/10/2026)

# ---------------- áudio ----------------
KEY = None
def tts(text, voice):
    h = hashlib.sha1(f'gemini-3.1-flash-tts-preview|{voice}|{ESTILO_TTS}|{text}'.encode()).hexdigest()[:16]; c = CACHE / f'{h}.wav'
    if not c.exists():
        body = {"contents": [{"parts": [{"text": f"{ESTILO_TTS} {text}"}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
        for k in range(4):
            try:
                if KEY:
                    r = json.load(urllib.request.urlopen(urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent', data=json.dumps(body).encode(), headers={'content-type': 'application/json', 'x-goog-api-key': KEY}), timeout=240))
                else:
                    r = api('/admin/api/tts', {'model': 'gemini-3.1-flash-tts-preview', 'body': body}, tries=1, timeout=240)
                p = r['candidates'][0]['content']['parts'][0]['inlineData']; pcm = base64.b64decode(p['data'])
                um = r.get('usageMetadata') or {}; uso('gemini-3.1-flash-tts-preview', um.get('promptTokenCount'), um.get('candidatesTokenCount'))
                if len(pcm) < 24000: raise RuntimeError('áudio vazio')
                rate = int(p.get('mimeType', '').split('rate=')[1].split(';')[0]) if 'rate=' in p.get('mimeType', '') else 24000
                with wave.open(str(c), 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
                break
            except Exception as e:
                if k == 3: raise
                log('tts tenta de novo', str(e)[:120]); time.sleep(6 * (k + 1))
    return c

def dur(f): return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout)

def narrar(h, dna, od):
    voice, tempo = VOZ[str(dna.get('fase', '1'))]
    nome = dna['nome']
    abre = f"Minha Lenda apresenta: {h.get('titulo','')}. Uma história criada especialmente para {nome}."
    fecha = (f"Esta lenda foi criada especialmente para {nome}. E a aventura continua: a próxima história já está esperando. "
             "Para criar outra, é só visitar minha lenda ponto com ponto bê érre. Até a próxima lenda!")
    partes = []
    for i, p in enumerate(h['paginas']):
        t = (f"{p['capitulo']}. " if p.get('capitulo') else '') + str(p.get('texto', ''))
        if i == 0 and not p.get('capitulo'): t = f"{h.get('titulo','')}. {t}"
        partes.append(t)
    g = str(h.get('gancho_proximo') or '').strip()
    if g and '?' not in g[-3:]: g += ' O que será que vem por aí?'
    teaser = f"Ei… ainda está aí? Então escute só, bem baixinho: {g}" if g else ''
    with cf.ThreadPoolExecutor(4) as ex:
        wavs = list(ex.map(lambda t: tts(t, voice), [abre] + partes + [fecha] + ([teaser] if teaser else [])))
    wt = wavs.pop() if teaser else None
    tmp = pathlib.Path(tempfile.mkdtemp(dir=od))
    std = ['-ar', '44100', '-ac', '2']
    af = (f'rubberband=tempo={tempo}:pitchq=quality,' if tempo != 1 else '') + 'aresample=44100'
    segs = []
    for i, w in enumerate(wavs[1:-1]):
        o = tmp / f'p{i:03d}.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(w), '-af', af + ',apad=pad_dur=0.9', *std, str(o)], check=True); segs.append(o)
    ab = tmp / 'abre.wav'; fe = tmp / 'fecha.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wavs[0]), '-af', 'aresample=44100', *std, str(ab)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wavs[-1]), '-af', 'aresample=44100', *std, str(fe)], check=True)
    li = dur(ab) + 2.4
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-stream_loop', '4', '-i', str(MUSICA), '-t', str(li + 2.2), '-af', f"volume=0.14,afade=t=in:d=0.8,afade=t=out:st={li}:d=2", *std, str(tmp / 'bed.wav')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(tmp / 'bed.wav'), '-i', str(ab), '-filter_complex', '[1]adelay=700|700[v];[0][v]amix=inputs=2:duration=first:normalize=0[o]', '-map', '[o]', *std, str(tmp / 'intro.wav')], check=True)
    lo = dur(fe)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-stream_loop', '2', '-i', str(MUSICA), '-t', str(lo + 10), '-af', f"volume='if(lt(t,{lo + 0.8}),0.12,1)':eval=frame,afade=t=in:d=0.6,afade=t=out:st={lo + 6.5}:d=3.5", *std, str(tmp / 'bed2.wav')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(tmp / 'bed2.wav'), '-i', str(fe), '-filter_complex', '[1]adelay=400|400[v];[0][v]amix=inputs=2:duration=first:normalize=0[o]', '-map', '[o]', *std, str(tmp / 'outro.wav')], check=True)
    ordem = [tmp / 'intro.wav'] + segs + [tmp / 'outro.wav']
    if wt:  # depois da propaganda, a narração volta para o teaser da próxima aventura, com a trilha baixinha
        tv = tmp / 'teaser_v.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wt), '-af', (f'rubberband=tempo={tempo}:pitchq=quality,' if tempo != 1 else '') + 'aresample=44100', *std, str(tv)], check=True)
        lt = dur(tv)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-stream_loop', '3', '-i', str(MUSICA), '-t', str(lt + 4.5), '-af', f"volume=0.09,afade=t=in:d=1.2,afade=t=out:st={lt + 1.6}:d=2.8", *std, str(tmp / 'bed3.wav')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(tmp / 'bed3.wav'), '-i', str(tv), '-filter_complex', '[1]adelay=900|900[v];[0][v]amix=inputs=2:duration=first:normalize=0[o]', '-map', '[o]', *std, str(tmp / 'teaser.wav')], check=True)
        ordem.append(tmp / 'teaser.wav')
    marcas, t = [], dur(tmp / 'intro.wav')
    for s in segs: marcas.append(round(t, 2)); t += dur(s)
    extra = {'fim': round(t, 2)}
    if wt: extra['teaser'] = round(t + dur(tmp / 'outro.wav'), 2)
    lst = tmp / 'lista.txt'; lst.write_text(''.join(f"file '{p}'\n" for p in ordem))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9', '-ar', '44100', '-b:a', '128k', str(od / 'audiolivro.mp3')], check=True)
    # loudnorm de duas passadas não muda o tempo: as marcas continuam válidas
    log('áudio ok:', round(dur(od / 'audiolivro.mp3') / 60, 1), 'min')
    return marcas, extra

def subir(pid, od, nomes):
    for n in nomes:
        ct = 'application/pdf' if n.endswith('.pdf') else 'audio/mpeg' if n.endswith('.mp3') else 'text/plain; charset=utf-8' if n.endswith('.txt') else 'application/json' if n.endswith('.json') else 'image/jpeg'
        api(f'/admin/api/pedido/{pid}/arquivo/{n}', raw=(od / n).read_bytes(), method='PUT', ctype=ct, timeout=600)

def baixar(pid, nome, dst):
    for k in range(3):
        try:
            h = {'authorization': oidc() if AUTH == 'oidc' else AUTH, 'user-agent': 'MinhaLenda-Executor/1.0'}
            dst.write_bytes(urllib.request.urlopen(urllib.request.Request(f'{SITE}/admin/api/pedido/{pid}/arquivo/{nome}', headers=h), timeout=120).read()); return
        except Exception:
            if k == 2: raise
            time.sleep(4)

def rediagramar(pid):
    """Refaz só a diagramação (livro, PDFs, páginas e kit da gráfica) de um pedido entregue, com o texto e as ilustrações que já existem."""
    p = api(f'/admin/api/pedido/{pid}')
    r = json.loads(p.get('resultado_json') or '{}'); lv = r.get('livro') or {}
    if not lv.get('paginas'): raise RuntimeError('pedido sem livro para rediagramar')
    dados = json.loads(p['dados_json']); dna = dados['dna']
    if dados.get('dedicatoria'): dna['dedicatoria'] = dados['dedicatoria']
    od = OUT / pid; od.mkdir(parents=True, exist_ok=True)
    ilus = lv.get('ilustracoes') or []
    for n in ['capa.jpg'] + [x['arquivo'] for x in ilus]: baixar(pid, n, od / n)
    h = {'titulo': lv.get('titulo'), 'dedicatoria': lv.get('dedicatoria'), 'gancho_proximo': lv.get('gancho_proximo'), 'paginas': lv['paginas']}
    d = livro_mod.montar(h, ilus, dna, od, pid=pid, pedido=p, log=log)
    subir(pid, od, ['livro.pdf', 'imprimir-livreto-a4.pdf', 'imprimir-a4.pdf'] + d['folhas'] + d['kit'])
    api(f'/admin/api/pedido/{pid}', {'resultado_merge': {'folhas': len(d['folhas']), 'folha_de': d['folha_de'], 'grafica': d['kit'], 'diagramacao': 2}})
    log(pid, 'REDIAGRAMADO', len(d['folhas']), 'páginas')

def produzir(pid, refazer=False):
    p = api(f'/admin/api/pedido/{pid}')
    if p['status'] in ('entregue',) and not refazer: log(pid, 'já entregue'); return
    api(f'/admin/api/pedido/{pid}', {'status': 'produzindo'})
    try:
        dados = json.loads(p['dados_json']); dna = dados['dna']; estilo = dados.get('estilo') or 'pintura'
        if dados.get('competencia'): dna['competencia'] = dados['competencia']
        if dados.get('dedicatoria'): dna['dedicatoria'] = dados['dedicatoria']
        if not p.get('foto_b64'): raise RuntimeError('pedido sem foto')
        od = OUT / pid; od.mkdir(parents=True, exist_ok=True)
        log(pid, dna['nome'], 'idade', dna.get('idade'), 'história', dna.get('familia'), dna.get('historia'), privado=True)
        USO.clear()
        h, crit = escrever(dna)
        (od / 'historia.json').write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding='utf-8')
        ilus = ilustrar(h, dna, p['foto_b64'], estilo, od)
        d = livro_mod.montar(h, ilus, dna, od, pid=pid, pedido=p, log=log)
        folhas, mapa, kit = d['folhas'], d['folha_de'], d['kit']
        marcas, marcas_extra = narrar(h, dna, od)
        nomes = ['capa.jpg', 'livro.pdf', 'audiolivro.mp3', 'imprimir-livreto-a4.pdf', 'imprimir-a4.pdf', 'historia.json'] + [x['arquivo'] for x in ilus] + folhas + kit
        subir(pid, od, nomes)
        livro = {'titulo': h.get('titulo'), 'dedicatoria': h.get('dedicatoria'), 'gancho_proximo': h.get('gancho_proximo'),
                 'paginas': [{'n': x.get('n'), 'capitulo': x.get('capitulo'), 'texto': x.get('texto')} for x in h['paginas']], 'ilustracoes': ilus}
        api(f'/admin/api/pedido/{pid}', {'status': 'entregue', 'resultado': {'capa': 'capa.jpg', 'livro': livro, 'marcas': marcas, 'nota': crit.get('media'), 'folhas': len(folhas), 'folha_de': mapa, 'imprimir': True, 'grafica': kit, 'diagramacao': 2, 'marcas_extra': marcas_extra, 'uso': USO}})
        log(pid, 'ENTREGUE', f'{SITE}/l/{p["token"]}', privado=True)
    except Exception as e:
        api(f'/admin/api/pedido/{pid}', {'status': 'falhou', 'erro': str(e)[:700]}); raise

if __name__ == '__main__':
    AUTH = admin_auth(); KEY = None if CI_OIDC else gemini_key()
    args = [a for a in sys.argv[1:] if a]
    modo = 'produzir'
    if args and args[0].startswith('--'): modo = args.pop(0)[2:]
    modo = os.environ.get('MODO') or modo
    ids = args or [x['id'] for x in api('/admin/api/pedidos?status=fila')['pedidos']]
    log('pedidos:', ids or 'nenhum', '| modo:', modo)
    for pid in ids:
        try:
            if modo == 'rediagramar': rediagramar(pid)
            else: produzir(pid, refazer=(modo == 'refazer'))
        except Exception as e:
            # tipo do erro no log público; a mensagem completa vai para o painel e para o e-mail de aviso
            log(pid, 'FALHOU', type(e).__name__, str(e)[:160] if str(e).startswith('motor/') else '')
            log(pid, str(e)[:400], privado=True)
