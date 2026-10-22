"""Marcador de página do Clube da Lenda (22/10/2026).
Um marcador por livro do Clube: frente com a logo, a tirinha de 3 quadros da criança e a nossa propaganda;
verso (dobrado) com uma moldura fixa e uma citação sobre leitura. Fundo branco para gastar pouca tinta.
A moldura e as citações são fixas (4 variações, em código); a cada livro só a tirinha muda (1 imagem).

Saídas: marcador.pdf (A4 com o marcador aberto, marcas de corte e dobra, instruções) e marcador.jpg (prévia).
Uso isolado (teste): python3 marcador.py <pasta> <nome> <livro_n> <tirinha.jpg> "fala 1" "fala 2" "fala 3"
"""
import html, pathlib, sys

HERE = pathlib.Path(__file__).parent
FONTS = HERE / 'fonts'
SIL = HERE / 'sil'
esc = lambda t: html.escape(str(t or ''))
uri = lambda p: pathlib.Path(p).as_uri()

# Só domínio público, com fonte conferida (22/10/2026).
CITACOES = [
    ('Ainda acabo fazendo livros onde as nossas crianças possam morar.', 'Monteiro Lobato', 'carta a Godofredo Rangel, 1916', ('castelo', 'chapeu')),
    ('Ler é sonhar pela mão de outrem.', 'Fernando Pessoa', 'Livro do Desassossego', ('navio', 'mata')),
    ('Um país se faz com homens e livros.', 'Monteiro Lobato', '', ('dragao', 'heroi')),
    ('Não há fragata como um livro para nos levar a terras distantes.', 'Emily Dickinson', 'poema de 1873, tradução livre', ('tapete', 'unicornio')),
]

FW, FH = 50, 190          # uma face do marcador (mm)
OW = FW * 2               # aberto: frente + verso


def paineis(img_path, od):
    """Corta a tirinha nos 3 quadros procurando as faixas brancas entre eles; se não achar, divide em terços."""
    from PIL import Image, ImageOps
    im = Image.open(img_path).convert('RGB')
    g = ImageOps.grayscale(im); w, h = g.size
    px = g.load()
    def branca(y):
        xs = range(int(w * .08), int(w * .92), max(1, w // 120))
        v = [px[x, y] for x in xs]
        return min(v) > 205 and sum(v) / len(v) > 232
    def faixa(a, b):
        ys = [y for y in range(int(h * a), int(h * b)) if branca(y)]
        if not ys: return None
        # maior sequência contínua de linhas brancas
        best, cur = [], [ys[0]]
        for y in ys[1:]:
            if y == cur[-1] + 1: cur.append(y)
            else: best = max(best, cur, key=len); cur = [y]
        best = max(best, cur, key=len)
        return (best[0], best[-1]) if len(best) >= 3 else None
    f1, f2 = faixa(.22, .45), faixa(.55, .78)
    cortes = [(0, f1[0]), (f1[1], f2[0]), (f2[1], h)] if f1 and f2 else [(0, h // 3), (h // 3, 2 * h // 3), (2 * h // 3, h)]
    out = []
    for i, (a, b) in enumerate(cortes):
        p = im.crop((0, a, w, b))
        # tira a margem branca externa de cada quadro
        bb = ImageOps.invert(ImageOps.grayscale(p)).point(lambda v: 255 if v > 30 else 0).getbbox()
        if bb and (bb[2] - bb[0]) > w * .6 and (bb[3] - bb[1]) > (b - a) * .6: p = p.crop(bb)
        f = od / f'marcador_q{i + 1}.jpg'; p.save(f, 'JPEG', quality=90); out.append(f)
    return out


def _sil(n):
    import base64, re
    b = base64.b64encode(re.sub(rb'<metadata>.*?</metadata>', b'', (SIL / f'{n}.svg').read_bytes(), flags=re.S)).decode()
    return f"url('data:image/svg+xml;base64,{b}')"


CSS = """
@font-face{font-family:Alegreya;src:url('%(f)s/Alegreya[wght].ttf');font-weight:400 900}
@font-face{font-family:Alegreya;font-style:italic;src:url('%(f)s/Alegreya-Italic[wght].ttf');font-weight:400 900}
@font-face{font-family:'Alegreya Sans';src:url('%(f)s/AlegreyaSans-Medium.ttf');font-weight:500}
@font-face{font-family:'Alegreya Sans';src:url('%(f)s/AlegreyaSans-800.woff2');font-weight:800}
@font-face{font-family:'Alegreya Sans';src:url('%(f)s/AlegreyaSans-700.woff2');font-weight:700}
@font-face{font-family:Gotica;src:url('%(f)s/UnifrakturMaguntia-Book.ttf')}
@page{size:210mm 297mm;margin:0}
*{box-sizing:border-box}
html,body{margin:0;background:#fff;color:#1C1236;font-family:'Alegreya Sans',sans-serif}
.folha{position:relative;width:210mm;height:297mm;overflow:hidden}
.m{position:absolute;left:55mm;top:22mm;width:100mm;height:190mm;display:flex}
.face{width:50mm;height:190mm;position:relative;overflow:hidden}
.frente{padding:4mm 3.6mm 3.4mm;display:flex;flex-direction:column;align-items:center}
.logo{height:8.6mm;max-width:100%%;display:block}
.de{margin:1.6mm 0 0;font:700 7.4pt/1.15 'Alegreya Sans';letter-spacing:.06em;text-transform:uppercase;color:#A8710F;text-align:center}
.de b{display:block;font:800 12.5pt/1.05 Alegreya;letter-spacing:0;text-transform:none;color:#1C1236;margin-top:.6mm}
.tira{margin-top:2.6mm;width:100%%;display:flex;flex-direction:column;gap:1.8mm}
.q{width:100%%}
.q img{width:100%%;height:33mm;object-fit:cover;border:.35mm solid #1C1236;border-radius:1.6mm;display:block}
.q p{margin:.9mm 0 0;font:500 7.3pt/1.18 'Alegreya Sans';color:#1C1236;min-height:5.4mm}
.q p b{font-weight:800}
.tt{font:italic 700 7.6pt Alegreya;color:#A8710F;text-align:center;margin:0}
.ad{margin-top:auto;width:100%%;border-top:.3mm dashed #DDA53C;padding-top:2mm;display:flex;gap:2mm;align-items:center}
.ad img{width:12.5mm;height:12.5mm;flex:none}
.ad p{margin:0;font:500 6.6pt/1.22 'Alegreya Sans';color:#5A5070}
.ad p b{display:block;font:800 7.6pt/1.15 'Alegreya Sans';color:#1C1236}
.verso{display:flex;align-items:center;justify-content:center}
.moldura{position:absolute;inset:3.2mm;border:.45mm solid #DDA53C;border-radius:2.4mm}
.moldura::after{content:"";position:absolute;inset:1.2mm;border:.2mm solid #DDA53C;border-radius:1.6mm}
.orn{position:absolute;left:50%%;width:30mm;height:22mm;transform:translateX(-50%%);background:#DDA53C;-webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat;opacity:.9}
.orn.t{top:9mm}.orn.b{bottom:17mm}
.cit{position:relative;padding:0 6.5mm;text-align:center}
.cit .aspa{display:block;font:800 40pt/.6 Alegreya;color:#DDA53C;height:9mm}
.cit q{display:block;font:italic 600 12pt/1.32 Alegreya;color:#1C1236;quotes:none}
.cit .au{display:block;margin-top:4mm;font:800 7.6pt 'Alegreya Sans';letter-spacing:.12em;text-transform:uppercase;color:#A8710F}
.cit .fo{display:block;margin-top:.8mm;font:500 6.4pt 'Alegreya Sans';color:#5A5070}
.vm{position:absolute;bottom:9mm;left:0;right:0;text-align:center;font:500 6.2pt 'Alegreya Sans';letter-spacing:.08em;color:#A8710F}
.dobra{position:absolute;left:105mm;top:22mm;height:190mm;border-left:.25mm dashed #9A93A8}
.cm{position:absolute;background:#555}
.inst{position:absolute;left:30mm;right:30mm;top:224mm;font:500 9.6pt/1.42 'Alegreya Sans';color:#1C1236}
.inst h2{margin:0 0 2mm;font:800 14pt Alegreya}
.inst ol{margin:0;padding-left:5mm}
.inst li{margin:.6mm 0}
.inst .pe{margin-top:3mm;font-size:8.2pt;color:#5A5070}
"""


def montar(od, nome, livro_n, tirinha_img, falas, titulo='', qr_url='https://minhalenda.com.br/clube?o=marcador', log=print):
    """Gera marcador.pdf e marcador.jpg na pasta od. falas: 3 strings ("Nome: fala")."""
    od = pathlib.Path(od)
    import segno
    qr = od / 'qr_marcador.svg'
    segno.make(qr_url, error='m').save(str(qr), scale=4, border=1, dark='#1C1236', light='#FFFFFF')
    qs = paineis(tirinha_img, od)
    logo = od / 'logo_claro.svg'  # logo da marca com o texto escuro, para o papel branco
    logo.write_text((HERE / 'logo.svg').read_text(encoding='utf-8').replace('#F3EDE2', '#1C1236'), encoding='utf-8')
    cit, autor, fonte, (o1, o2) = CITACOES[(int(livro_n or 1) - 1) % len(CITACOES)]

    def fala(t):
        t = str(t or '')
        if ':' in t[:24]:
            a, b = t.split(':', 1); return f'<b>{esc(a.strip())}:</b> {esc(b.strip())}'
        return esc(t)
    quadros = ''.join(f'<div class="q"><img src="{uri(q)}" alt=""><p>{fala(f)}</p></div>' for q, f in zip(qs, falas))
    frente = (f'<div class="face frente"><img class="logo" src="{uri(logo)}" alt="Minha Lenda">'
              f'<p class="de">O marcador de<b>{esc(nome)}</b></p>'
              f'<div class="tira">{f"<p class=tt>{esc(titulo)}</p>" if titulo else ""}{quadros}</div>'
              f'<div class="ad"><img src="{uri(qr)}" alt=""><p><b>Toda criança tem histórias.</b>Aqui, elas viram lendas. minhalenda.com.br · @minhalenda</p></div></div>')
    verso = (f'<div class="face verso"><div class="moldura"></div>'
             f'<div class="orn t" style="--m:{_sil(o1)}"></div><div class="orn b" style="--m:{_sil(o2)}"></div>'
             f'<div class="cit"><span class="aspa" aria-hidden="true">&ldquo;</span><q>{esc(cit)}</q><span class="au">{esc(autor)}</span>{f"<span class=fo>{esc(fonte)}</span>" if fonte else ""}</div>'
             f'<div class="vm">Clube da Lenda · aventura {int(livro_n or 1)}</div></div>')
    # marcas de corte (fora do marcador) nos 4 cantos e de dobra no meio
    L, G = 6, 1.5; x0, y0, x1, y1, xm = 55, 22, 155, 212, 105
    cm = []
    for x in (x0, x1):
        cm += [f'<i class="cm" style="left:{x - .1}mm;top:{y0 - G - L}mm;width:.2mm;height:{L}mm"></i>', f'<i class="cm" style="left:{x - .1}mm;top:{y1 + G}mm;width:.2mm;height:{L}mm"></i>']
    for y in (y0, y1):
        cm += [f'<i class="cm" style="top:{y - .1}mm;left:{x0 - G - L}mm;height:.2mm;width:{L}mm"></i>', f'<i class="cm" style="top:{y - .1}mm;left:{x1 + G}mm;height:.2mm;width:{L}mm"></i>']
    inst = ('<div class="inst"><h2>Seu marcador de página</h2><ol>'
            '<li>Imprima em tamanho real (100%), de preferência em papel mais grosso.</li>'
            '<li>Recorte nas marcas dos cantos, em volta do marcador.</li>'
            '<li>Dobre ao meio na linha tracejada e cole as duas metades com cola bastão.</li></ol>'
            '<p class="pe">Um marcador novo chega com cada aventura do Clube da Lenda. Guarde todos: a coleção conta a história dela.</p></div>')
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{CSS % {"f": uri(FONTS)}}</style></head><body>'
           f'<div class="folha"><div class="m">{frente}{verso}</div><div class="dobra"></div>{"".join(cm)}{inst}</div></body></html>')
    hp = od / 'marcador.html'; hp.write_text(doc, encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(viewport={'width': 794, 'height': 1123}, device_scale_factor=2)
        pg.goto(hp.as_uri()); pg.wait_for_load_state('networkidle'); pg.evaluate('document.fonts.ready'); pg.wait_for_timeout(300)
        pg.pdf(path=str(od / 'marcador.pdf'), prefer_css_page_size=True, print_background=True)
        el = pg.query_selector('.m'); el.screenshot(path=str(od / 'marcador.png'))
        br.close()
    from PIL import Image
    Image.open(od / 'marcador.png').convert('RGB').save(od / 'marcador.jpg', 'JPEG', quality=86, optimize=True)
    log('marcador ok')
    return ['marcador.pdf', 'marcador.jpg']


if __name__ == '__main__':
    d, nome, n, img, *falas = sys.argv[1:]
    print(montar(d, nome, int(n), img, falas))
