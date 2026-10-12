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
    longo = lambda: any('Texto longo' in str(x) for x in (cr.get('probs') or []))
    # tamanho travado por faixa (09/10): texto longo ganha uma revisão a mais só para cortar
    while not cr.get('aprovada') and rev < (2 if dna.get('enredo_livre') or longo() else 1):
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
    body += f'<section class="fim"><p>Esta lenda foi criada especialmente para {html.escape(dna["nome"])}.</p><p class="s">minhalenda.com.br</p></section>'
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

# ---------------- folhear e imprimir em casa ----------------
def folhear(h, od):
    """Páginas do PDF viram imagens para o leitor de folhear; mapa história->folha para virar junto com a narração;
    e dois PDFs para imprimir em casa: livreto A4 (frente e verso, dobra e grampeia) e A4 uma página por folha."""
    import pymupdf
    src = pymupdf.open(od / 'livro.pdf'); n = len(src); folhas = []
    for i, pg in enumerate(src):
        nome = f'fl-{i + 1:02d}.jpg'
        pix = pg.get_pixmap(dpi=120); im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        im.save(od / nome, 'JPEG', quality=80, optimize=True, progressive=True); folhas.append(nome)
    limpa = lambda t: re.sub(r'\W+', '', str(t)).lower()
    textos = [limpa(pg.get_text()) for pg in src]; mapa, j = [], 0
    for p in h['paginas']:
        chave = limpa(p.get('texto', ''))[2:42]  # pula a capitular
        k = next((x for x in range(j, n) if chave and chave in textos[x]), j); mapa.append(k); j = k
    # livreto: total múltiplo de 4, folhas A4 deitadas com 2 páginas A5; imprimir frente e verso virando na borda curta
    tot = (n + 3) // 4 * 4; W, H = 842, 595; liv = pymupdf.open()
    for f in range(tot // 4):
        for esq, dir_ in ((tot - 1 - 2 * f, 2 * f), (2 * f + 1, tot - 2 - 2 * f)):
            pg = liv.new_page(width=W, height=H)
            for idx, r in ((esq, pymupdf.Rect(0, 0, W / 2, H)), (dir_, pymupdf.Rect(W / 2, 0, W, H))):
                if idx < n: pg.show_pdf_page(r, src, idx)
    liv.save(od / 'imprimir-livreto-a4.pdf', garbage=3, deflate=True)
    a4 = pymupdf.open()
    for i in range(n):
        pg = a4.new_page(width=595, height=842); pg.show_pdf_page(pg.rect, src, i)
    a4.save(od / 'imprimir-a4.pdf', garbage=3, deflate=True)
    log('folhear ok:', n, 'folhas | pdf para imprimir ok')
    return folhas, mapa

# ---------------- gráfica: livro impresso A5 grampeado (11/10) ----------------
FICHA = """MINHA LENDA · FICHA PARA A GRÁFICA · pedido {pid}

QUANTIDADE: {qtd} livro(s) iguais

MIOLO ({paginas} páginas A5 = {folhas} folhas A4 frente e verso)
- Arquivo para gráfica: grafica-miolo-a5.pdf (páginas em ordem, 148 x 210 mm). A gráfica faz a imposição.
- Ou imprima direto: grafica-miolo-livreto-a4.pdf (já imposto: A4 deitado, 2 páginas por lado,
  frente e verso virando na BORDA CURTA). Dobre as folhas juntas ao meio.
- Papel: sulfite/offset 90 g/m² (120 g/m² se quiser mais encorpado), impressão colorida.

CAPA (1 folha por livro, só de um lado: 4x0)
- grafica-capa-sangria.pdf: A4 deitado com 3 mm de sangria e marcas de corte (303 x 216 mm úteis).
  Imprimir em A3/SRA3 e refilar nas marcas. Lado esquerdo = contracapa, lado direito = capa.
- grafica-capa-a4.pdf: a mesma capa no A4 exato, sem sangria (para impressora comum; fica um filete branco).
- Papel: couché brilho 250 a 300 g/m² ou cartão; plastificação (laminação brilho) opcional.

ACABAMENTO
- Capa por fora do miolo, dobra ao meio e 2 grampos na dobra (canoa). Refile frontal opcional.
- Conferir: a página 1 do miolo (título) fica logo depois da capa.

ENTREGA
{endereco}
Frete: {frete}
"""

def _upscale(src, dst, w_px, h_px):
    """Corta para a proporção e amplia com Lanczos + nitidez leve, para imprimir perto de 300 dpi."""
    from PIL import ImageFilter, ImageOps
    im = Image.open(src).convert('RGB')
    im = ImageOps.fit(im, (w_px, h_px), Image.LANCZOS, centering=(0.5, 0.4))
    im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))
    im.save(dst, 'JPEG', quality=93, subsampling=0)

def grafica(h, ilus, dna, od, pid, pedido):
    """Kit da gráfica: miolo A5 (múltiplo de 4, completado com páginas de atividade), livreto A4 imposto,
    capa com sangria e marcas de corte, capa A4 sem sangria e a ficha com papel, quantidade e endereço."""
    import pymupdf
    ff = lambda n: (FONTS / n).as_uri()
    at = {x['pagina']: x['arquivo'] for x in ilus}
    for x in ilus:  # ilustrações de página em 300 dpi (120 x 170 mm úteis)
        _upscale(od / x['arquivo'], od / ('p_' + x['arquivo']), 1417, 2008)
    nome = html.escape(dna['nome']); tit = html.escape(h.get('titulo', ''))
    col = {'0': 'Coleção Ouvir', '1': 'Coleção Ler Junto', '2': 'Coleção Aventura'}[str(dna.get('fase', '1'))]
    ded_cli = (dna.get('dedicatoria') or '').strip()  # opcional: só entra se o cliente escreveu
    body = (f'<section class="rosto"><p class="col">Minha Lenda · {col}</p><h1>{tit}</h1><p class="para">Uma lenda criada especialmente para {nome}</p>'
            + (f'<p class="ded">{html.escape(ded_cli)}</p>' if ded_cli else '') + '</section>')
    first = True
    for i, p in enumerate(h['paginas']):
        n = int(p.get('n') or i + 1)
        body += '<section class="pg">' + (f'<h2>{html.escape(p["capitulo"])}</h2>' if p.get('capitulo') else '') + f'<p>{capT(p.get("texto")) if (first or p.get("capitulo")) else html.escape(p.get("texto", ""))}</p></section>'
        first = False
        if n in at: body += f'<section class="il"><img src="{(od / ("p_" + at[n])).as_uri()}"></section>'
    if h.get('gancho_proximo'): body += f'<section class="gancho"><h2>Continua…</h2><p>{html.escape(h["gancho_proximo"])}</p></section>'
    body += f'<section class="fim"><p>Fim. Até a próxima lenda, {nome}!</p></section>'
    ATIV = [f'<section class="ativ"><h2>Desenhe aqui a sua cena favorita</h2><div class="moldura"></div><p>Desenhado por {nome}</p></section>',
            '<section class="ativ"><h2>Escreva um recado para o herói</h2><div class="linhas">' + '<i></i>' * 11 + '</div></section>',
            '<section class="ativ"><h2>Quem estava nesta aventura?</h2><div class="linhas">' + '<i></i>' * 11 + '</div></section>',
            '<section class="ativ"><h2>Invente o que acontece depois</h2><div class="moldura"></div></section>']
    css = f'''@font-face{{font-family:Alegreya;src:url({ff("Alegreya[wght].ttf")});font-weight:400 900}}
@font-face{{font-family:Alegreya;font-style:italic;src:url({ff("Alegreya-Italic[wght].ttf")});font-weight:400 900}}
@font-face{{font-family:Unifraktur;src:url({ff("UnifrakturMaguntia-Book.ttf")})}}
@font-face{{font-family:AlegreyaSans;src:url({ff("AlegreyaSans-Medium.ttf")})}}
@page{{size:148mm 210mm;margin:16mm 14mm 18mm;@bottom-center{{content:counter(page);font:9pt Alegreya;color:#7a6d8a}}}}
@page rosto{{@bottom-center{{content:none}}}}
*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;box-sizing:border-box}}body{{margin:0;font-family:Alegreya;color:#1C1236}}
section{{break-after:page}}.rosto{{page:rosto;padding-top:46mm;text-align:center}}.rosto .col{{font:700 8.5pt AlegreyaSans;letter-spacing:.14em;text-transform:uppercase;color:#A8710F}}
.rosto h1{{font:800 24pt/1.12 Alegreya;margin:8mm 0}}.rosto .para{{font:italic 500 13pt Alegreya;color:#5A5070}}
.rosto .ded{{font:italic 500 13.5pt/1.55 Alegreya;margin:16mm auto 0;max-width:96mm;padding-top:9mm;border-top:.4mm solid #DDA53C;white-space:pre-line}}
.pg p{{font:500 12.5pt/1.6 Alegreya;margin:0;white-space:pre-line}}.pg h2{{font:800 19pt/1.2 Alegreya;color:#A8710F;text-align:center;margin:0 0 8mm}}
.cap{{float:left;font-size:3.1em;line-height:.82;margin:5px 7px 0 0;color:#A8710F}}.cap.goth{{font-family:Unifraktur}}.cap.roman{{font-weight:800}}
.il{{display:flex;align-items:center;justify-content:center;height:170mm}}.il img{{max-width:100%;max-height:170mm;border-radius:3mm}}
.gancho{{padding-top:50mm;text-align:center}}.gancho h2{{color:#A8710F;font:800 18pt Alegreya}}.gancho p{{font:italic 500 13pt/1.5 Alegreya}}
.fim{{padding-top:80mm;text-align:center;font:italic 500 14pt Alegreya}}
.ativ h2{{font:800 16pt Alegreya;color:#A8710F;text-align:center;margin:0 0 6mm}}.ativ .moldura{{height:140mm;border:1.2mm dashed #DDA53C;border-radius:5mm}}
.ativ p{{text-align:center;font:italic 500 11pt Alegreya;margin-top:4mm}}.ativ .linhas i{{display:block;height:12mm;border-bottom:.4mm solid #c9bfd8}}
.branco{{}}'''
    def render(b, out):
        hp = od / 'grafica-miolo.html'; hp.write_text(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{css}</style></head><body>{b}</body></html>', encoding='utf-8')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(); pg = br.new_page(); pg.goto(hp.as_uri()); pg.wait_for_timeout(600)
            pg.pdf(path=str(out), prefer_css_page_size=True, print_background=True); br.close()
        return len(pymupdf.open(out))
    n = render(body, od / 'grafica-miolo-a5.pdf')
    falta = (-n) % 4
    if falta:  # completa até múltiplo de 4 com atividades (a última pode ficar em branco no verso)
        extra = ''.join(ATIV[k % len(ATIV)] for k in range(falta))
        n = render(body.replace('<section class="fim">', extra + '<section class="fim">'), od / 'grafica-miolo-a5.pdf')
        if n % 4: n = render(body.replace('<section class="fim">', extra + '<section class="fim">') + '<section class="branco"></section>' * ((-n) % 4), od / 'grafica-miolo-a5.pdf')
    src = pymupdf.open(od / 'grafica-miolo-a5.pdf'); n = len(src)
    W, H = 842, 595; liv = pymupdf.open()
    for f in range(n // 4):
        for esq, dir_ in ((n - 1 - 2 * f, 2 * f), (2 * f + 1, n - 2 - 2 * f)):
            pg = liv.new_page(width=W, height=H)
            for idx, r in ((esq, pymupdf.Rect(0, 0, W / 2, H)), (dir_, pymupdf.Rect(W / 2, 0, W, H))):
                pg.show_pdf_page(r, src, idx)
    liv.save(od / 'grafica-miolo-livreto-a4.pdf', garbage=3, deflate=True)
    # capa: A4 deitado (297 x 210) + 3 mm de sangria + 8 mm de margem para as marcas de corte
    mm = 72 / 25.4; S, M = 3, 8; CW, CH = 297 + 2 * S, 210 + 2 * S; PW, PH = CW + 2 * M, CH + 2 * M
    _upscale(od / 'capa.jpg', od / 'capa_print.jpg', round((148.5 + S) / 25.4 * 300), round(CH / 25.4 * 300))
    import segno
    qr = od / 'qr.svg'; segno.make('https://minhalenda.com.br/?o=livro', error='m').save(str(qr), scale=4, border=2, dark='#1C1236', light='#F3EDE2')
    logo = (pathlib.Path(__file__).parent / 'logo.svg').as_uri()
    capa_html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Alegreya;src:url({ff("Alegreya[wght].ttf")});font-weight:400 900}}@font-face{{font-family:Alegreya;font-style:italic;src:url({ff("Alegreya-Italic[wght].ttf")});font-weight:400 900}}
@font-face{{font-family:AlegreyaSans;src:url({ff("AlegreyaSans-Medium.ttf")})}}
@page{{size:{CW}mm {CH}mm;margin:0}}*{{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}}body{{margin:0}}
.w{{position:relative;width:{CW}mm;height:{CH}mm;overflow:hidden;display:flex}}
.back{{position:relative;width:{148.5 + S}mm;height:100%;background:radial-gradient(circle at 78% 12%,#2a2160 0,#121D42 55%);color:#F3EDE2;padding:{S + 16}mm 16mm {S + 14}mm {S + 16}mm;display:flex;flex-direction:column;gap:7mm;text-align:left}}
.back .logo{{height:14mm;align-self:flex-start}}.back .mid{{margin:auto 0;display:flex;flex-direction:column;gap:6mm}}
.back h2{{font:800 22pt/1.12 Alegreya;margin:0;color:#F3EDE2}}.back h2 b{{color:#DDA53C;font-weight:800}}
.back p{{font:500 12.2pt/1.5 Alegreya;margin:0;color:#D9D2E6}}.back p b{{color:#F3EDE2}}
.back .cta{{display:flex;gap:6mm;align-items:center;border-top:.35mm solid #DDA53C80;padding-top:6mm}}
.back .cta img{{width:25mm;height:25mm;border-radius:2mm}}
.back .cta .k{{font:700 7.6pt AlegreyaSans;letter-spacing:.16em;text-transform:uppercase;color:#DDA53C;margin-bottom:1.5mm}}
.back .cta .h{{font:800 15pt Alegreya;color:#F3EDE2;margin:0}}.back .cta .u{{font:700 10.5pt AlegreyaSans;color:#F3EDE2;margin-top:1.5mm}}
.back .para{{font:italic 500 9.5pt Alegreya;color:#A79FBD;text-align:center;margin-top:-2mm}}
.front{{position:relative;width:{148.5 + S}mm;height:100%;background:#121D42 url({(od / "capa_print.jpg").as_uri()}) center 40%/cover}}
.front h1{{position:absolute;left:0;right:0;top:0;margin:0;padding:{S + 12}mm {S + 12}mm 30mm 12mm;text-align:center;font:800 24pt/1.1 Alegreya;color:#fff;background:linear-gradient(#0b0820d9,transparent)}}
.front .c{{position:absolute;left:0;right:0;bottom:{S + 8}mm;text-align:center;font:700 8pt AlegreyaSans;letter-spacing:.16em;text-transform:uppercase;color:#FFE7A3;text-shadow:0 1px 3px #000a}}
</style></head><body><div class="w"><div class="back">
<img class="logo" src="{logo}" alt="Minha Lenda">
<div class="mid"><h2>Toda criança tem histórias.<br><b>Aqui, elas viram lendas.</b></h2>
<p>Cada livro da Minha Lenda é escrito do zero para uma criança só: com o nome dela, as pessoas que ela ama, o bichinho de casa e os desafios que ela está vivendo. Nenhuma história se repete.</p>
<p><b>Ler junto todos os dias</b> amplia o vocabulário, acalma a hora de dormir e aproxima a família. E quando a história fala sobre ela, ler deixa de ser tarefa e vira vontade.</p></div>
<div class="cta"><img src="{qr.as_uri()}" alt=""><div><div class="k">Siga e conheça as próximas aventuras</div><p class="h">@minhalenda</p><div class="u">Instagram · TikTok · YouTube<br>minhalenda.com.br</div></div></div>
<p class="para">Uma lenda criada especialmente para {nome}.</p></div>
<div class="front"><h1>{tit}</h1><div class="c">Minha Lenda · {col}</div></div></div></body></html>'''
    hp = od / 'grafica-capa.html'; hp.write_text(capa_html, encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(); pg.goto(hp.as_uri()); pg.wait_for_timeout(600)
        pg.pdf(path=str(od / 'capa_arte.pdf'), prefer_css_page_size=True, print_background=True); br.close()
    arte = pymupdf.open(od / 'capa_arte.pdf')
    doc = pymupdf.open(); pg = doc.new_page(width=PW * mm, height=PH * mm)
    pg.show_pdf_page(pymupdf.Rect(M * mm, M * mm, (M + CW) * mm, (M + CH) * mm), arte, 0)
    x0, y0, x1, y1 = (M + S) * mm, (M + S) * mm, (M + S + 297) * mm, (M + S + 210) * mm; L, G = 6 * mm, 1 * mm
    for x in (x0, x1):
        pg.draw_line((x, 0), (x, y0 - S * mm - G), width=.3); pg.draw_line((x, y1 + S * mm + G), (x, PH * mm), width=.3)
    for y in (y0, y1):
        pg.draw_line((0, y), (x0 - S * mm - G, y), width=.3); pg.draw_line((x1 + S * mm + G, y), (PW * mm, y), width=.3)
    xm = (x0 + x1) / 2  # marca da dobra
    pg.draw_line((xm, 0), (xm, y0 - S * mm - G), width=.3, dashes='[2 2] 0'); pg.draw_line((xm, y1 + S * mm + G), (xm, PH * mm), width=.3, dashes='[2 2] 0')
    pg.insert_text((x0, 5.5 * mm), f'Minha Lenda {pid} · capa 4x0 couché 250-300 g · sangria 3 mm · refilar nas marcas · tracejado = dobra', fontsize=6)
    doc.save(od / 'grafica-capa-sangria.pdf', garbage=3, deflate=True)
    a4 = pymupdf.open(); pg = a4.new_page(width=297 * mm, height=210 * mm)
    pg.show_pdf_page(pg.rect, arte, 0, clip=pymupdf.Rect(S * mm, S * mm, (S + 297) * mm, (S + 210) * mm))
    a4.save(od / 'grafica-capa-a4.pdf', garbage=3, deflate=True)
    e = json.loads(pedido.get('endereco_json') or '{}')
    endereco = f"{e.get('destinatario') or ''}\n{e.get('rua', '')}, {e.get('numero', '')} {e.get('compl') or ''}\n{e.get('bairro', '')} · {e.get('cidade', '')}/{e.get('uf', '')} · CEP {e.get('cep', '')}"
    (od / 'grafica-ficha.txt').write_text(FICHA.format(pid=pid, qtd=1 + int(pedido.get('copias') or 0), paginas=n, folhas=n // 4, endereco=endereco,
        frete=pedido.get('frete_info') or '-'), encoding='utf-8')
    log('gráfica ok:', n, 'páginas,', n // 4, 'folhas A4 + capa')
    return ['grafica-miolo-a5.pdf', 'grafica-miolo-livreto-a4.pdf', 'grafica-capa-sangria.pdf', 'grafica-capa-a4.pdf', 'grafica-ficha.txt']

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
        ct = 'application/pdf' if n.endswith('.pdf') else 'audio/mpeg' if n.endswith('.mp3') else 'text/plain; charset=utf-8' if n.endswith('.txt') else 'image/jpeg'
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
        folhas, mapa = folhear(h, od)
        kit = grafica(h, ilus, dna, od, pid, p) if p.get('produto') == 'impresso' else []
        marcas = narrar(h, dna, od)
        nomes = ['capa.jpg', 'livro.pdf', 'audiolivro.mp3', 'imprimir-livreto-a4.pdf', 'imprimir-a4.pdf'] + [x['arquivo'] for x in ilus] + folhas + kit
        subir(pid, od, nomes)
        livro = {'titulo': h.get('titulo'), 'dedicatoria': h.get('dedicatoria'), 'gancho_proximo': h.get('gancho_proximo'),
                 'paginas': [{'n': x.get('n'), 'capitulo': x.get('capitulo'), 'texto': x.get('texto')} for x in h['paginas']], 'ilustracoes': ilus}
        api(f'/admin/api/pedido/{pid}', {'status': 'entregue', 'resultado': {'capa': 'capa.jpg', 'livro': livro, 'marcas': marcas, 'nota': crit.get('media'), 'folhas': len(folhas), 'folha_de': mapa, 'imprimir': True, 'grafica': kit}})
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
