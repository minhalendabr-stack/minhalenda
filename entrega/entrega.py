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
    pl = api('/admin/api/plano', dna)
    if 'plan' not in pl: raise RuntimeError('motor/plano: ' + str(pl.get('erro') or pl)[:300])
    plan = pl['plan']
    tx = api('/admin/api/texto', {'dna': dna, 'plan': plan})
    if 'txt' not in tx: raise RuntimeError('motor/texto: ' + str(tx.get('erro') or tx)[:300])
    montar = lambda: {**plan, 'paginas': tx['txt'].get('paginas') or [], 'gancho_proximo': tx['txt'].get('gancho_proximo') or ''}
    cr = api('/admin/api/critica', {'dna': dna, 'h': montar()}); rev = 0
    while not cr.get('aprovada') and rev < (2 if dna.get('enredo_livre') else 1):
        tx = api('/admin/api/texto', {'dna': dna, 'plan': plan, 'rev': {'probs': cr.get('probs'), 'anterior': tx['txt'].get('paginas')}})
        cr = api('/admin/api/critica', {'dna': dna, 'h': montar()}); rev += 1
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
    f = api('/admin/api/imagem', {'tipo': 'ficha', 'foto': foto, 'estilo': estilo, 'figurino': h.get('figurino_heroi_en'), 'nome': dna['nome']})
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
                r = api('/admin/api/imagem', {**extra, 'foto': foto, 'ficha': ficha, 'estilo': estilo, 'figurino': h.get('figurino_heroi_en'), 'mundo': h.get('mundo_visual_en') or '', 'nome': dna['nome']}, tries=1)
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

# ---------------- PDF ----------------
GOTH = set('ECTDMLNFH')
def capT(t):
    t = str(t or ''); m = re.search(r'[A-Za-zÀ-ÿ]', t)
    if not m: return html.escape(t)
    i = m.start(); ch = t[i]; cls = 'goth' if ch.upper() in GOTH and ch == ch.upper() else 'roman'
    return html.escape(t[:i]) + f'<span class="cap {cls}">{html.escape(ch)}</span>' + html.escape(t[i + 1:])

def pdf(h, ilus, dna, od):
    fonts = FONTS
    ff = lambda n: (fonts / n).as_uri()
    at = {x['pagina']: x['arquivo'] for x in ilus}
    col = {'0': 'Coleção Ouvir', '1': 'Coleção Ler Junto', '2': 'Coleção Aventura'}[str(dna.get('fase', '1'))]
    body = f'<section class="capa"><img src="{(od / "capa.jpg").as_uri()}"><h1>{html.escape(h.get("titulo", ""))}</h1></section>'
    body += f'<section class="ded"><p class="col">Minha Lenda · {col}</p><p class="d">{html.escape(h.get("dedicatoria", ""))}</p></section>'
    first = True
    for i, p in enumerate(h['paginas']):
        n = int(p.get('n') or i + 1)
        body += '<section class="pg">' + (f'<h2>{html.escape(p["capitulo"])}</h2>' if p.get('capitulo') else '') + f'<p>{capT(p.get("texto")) if (first or p.get("capitulo")) else html.escape(p.get("texto", ""))}</p></section>'
        first = False
        if n in at: body += f'<section class="il"><img src="{(od / at[n]).as_uri()}"></section>'
    if h.get('gancho_proximo'): body += f'<section class="gancho"><h2>Continua no mês que vem…</h2><p>{html.escape(h["gancho_proximo"])}</p></section>'
    body += f'<section class="fim"><p>Esta lenda foi criada especialmente para {html.escape(dna["nome"])}.</p><p class="s">minhalenda.com.br · Ilustrado com IA, revisado por pessoas.</p></section>'
    css = f'''@font-face{{font-family:Alegreya;src:url({ff("Alegreya[wght].ttf")});font-weight:400 900}}
@font-face{{font-family:Alegreya;font-style:italic;src:url({ff("Alegreya-Italic[wght].ttf")});font-weight:400 900}}
@font-face{{font-family:Unifraktur;src:url({ff("UnifrakturMaguntia-Book.ttf")})}}
@font-face{{font-family:AlegreyaSans;src:url({ff("AlegreyaSans-Medium.ttf")})}}
@page{{size:A5;margin:16mm 14mm 18mm;@bottom-center{{content:counter(page);font:10pt Alegreya;color:#7a6d8a}}}}
@page capa{{margin:0;@bottom-center{{content:none}}}}
*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;box-sizing:border-box}}body{{margin:0;font-family:Alegreya;color:#1C1236}}
section{{break-after:page}}.capa{{page:capa;position:relative;width:148mm;height:210mm;overflow:hidden;background:#121D42}}
.capa img{{width:100%;height:100%;object-fit:cover}}.capa h1{{position:absolute;left:0;right:0;top:0;margin:0;padding:12mm 10mm 30mm;text-align:center;font:800 24pt/1.1 Alegreya;color:#fff;background:linear-gradient(#0b0820d9,transparent)}}
.ded{{padding-top:50mm;text-align:center}}.ded .col{{font:700 9pt AlegreyaSans;letter-spacing:.14em;text-transform:uppercase;color:#A8710F}}.ded .d{{font:italic 500 14pt/1.5 Alegreya;margin-top:10mm}}
.pg p{{font:500 12.5pt/1.6 Alegreya;margin:0;white-space:pre-line;text-align:left}}.pg h2{{font:800 19pt/1.2 Alegreya;color:#A8710F;text-align:center;margin:0 0 8mm}}
.cap{{float:left;font-size:3.1em;line-height:.82;margin:5px 7px 0 0;color:#A8710F}}.cap.goth{{font-family:Unifraktur}}.cap.roman{{font-weight:800}}
.il{{display:flex;align-items:center;justify-content:center;height:170mm}}.il img{{max-width:100%;max-height:170mm;border-radius:3mm}}
.gancho{{padding-top:50mm;text-align:center}}.gancho h2{{color:#A8710F;font:800 18pt Alegreya}}.gancho p{{font:italic 500 13pt/1.5 Alegreya}}
.fim{{padding-top:80mm;text-align:center;font:500 12pt Alegreya}}.fim .s{{font:9pt AlegreyaSans;color:#7a6d8a}}'''
    doc = f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'
    hp = od / 'livro.html'; hp.write_text(doc, encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(hp.as_uri()); pg.wait_for_timeout(600)
        pg.pdf(path=str(od / 'livro.pdf'), prefer_css_page_size=True, print_background=True); b.close()
    log('pdf ok:', round((od / 'livro.pdf').stat().st_size / 1e6, 1), 'MB')

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
    with cf.ThreadPoolExecutor(4) as ex:
        wavs = list(ex.map(lambda t: tts(t, voice), [abre] + partes + [fecha]))
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
    marcas, t = [], dur(tmp / 'intro.wav')
    for s in segs: marcas.append(round(t, 2)); t += dur(s)
    lst = tmp / 'lista.txt'; lst.write_text(''.join(f"file '{p}'\n" for p in ordem))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9', '-ar', '44100', '-b:a', '128k', str(od / 'audiolivro.mp3')], check=True)
    # loudnorm de duas passadas não muda o tempo: as marcas continuam válidas
    log('áudio ok:', round(dur(od / 'audiolivro.mp3') / 60, 1), 'min')
    return marcas

def subir(pid, od, nomes):
    for n in nomes:
        ct = 'application/pdf' if n.endswith('.pdf') else 'audio/mpeg' if n.endswith('.mp3') else 'image/jpeg'
        api(f'/admin/api/pedido/{pid}/arquivo/{n}', raw=(od / n).read_bytes(), method='PUT', ctype=ct, timeout=600)

def produzir(pid):
    p = api(f'/admin/api/pedido/{pid}')
    if p['status'] in ('entregue',): log(pid, 'já entregue'); return
    api(f'/admin/api/pedido/{pid}', {'status': 'produzindo'})
    try:
        dados = json.loads(p['dados_json']); dna = dados['dna']; estilo = dados.get('estilo') or 'pintura'
        if dados.get('competencia'): dna['competencia'] = dados['competencia']
        if dados.get('dedicatoria'): dna['dedicatoria'] = dados['dedicatoria']
        if not p.get('foto_b64'): raise RuntimeError('pedido sem foto')
        od = OUT / pid; od.mkdir(parents=True, exist_ok=True)
        log(pid, dna['nome'], 'idade', dna.get('idade'), 'história', dna.get('familia'), dna.get('historia'), privado=True)
        h, crit = escrever(dna)
        (od / 'historia.json').write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding='utf-8')
        ilus = ilustrar(h, dna, p['foto_b64'], estilo, od)
        pdf(h, ilus, dna, od)
        marcas = narrar(h, dna, od)
        nomes = ['capa.jpg', 'livro.pdf', 'audiolivro.mp3'] + [x['arquivo'] for x in ilus]
        subir(pid, od, nomes)
        livro = {'titulo': h.get('titulo'), 'dedicatoria': h.get('dedicatoria'), 'gancho_proximo': h.get('gancho_proximo'),
                 'paginas': [{'n': x.get('n'), 'capitulo': x.get('capitulo'), 'texto': x.get('texto')} for x in h['paginas']], 'ilustracoes': ilus}
        api(f'/admin/api/pedido/{pid}', {'status': 'entregue', 'resultado': {'capa': 'capa.jpg', 'livro': livro, 'marcas': marcas, 'nota': crit.get('media')}})
        log(pid, 'ENTREGUE', f'{SITE}/l/{p["token"]}', privado=True)
    except Exception as e:
        api(f'/admin/api/pedido/{pid}', {'status': 'falhou', 'erro': str(e)[:700]}); raise

if __name__ == '__main__':
    AUTH = admin_auth(); KEY = None if CI_OIDC else gemini_key()
    ids = sys.argv[1:] or [x['id'] for x in api('/admin/api/pedidos?status=fila')['pedidos']]
    log('pedidos:', ids or 'nenhum')
    for pid in ids:
        try: produzir(pid)
        except Exception as e:
            # tipo do erro no log público; a mensagem completa vai para o painel e para o e-mail de aviso
            log(pid, 'FALHOU', type(e).__name__, str(e)[:160] if str(e).startswith('motor/') else '')
            log(pid, str(e)[:400], privado=True)
