"""Diagramação Minha Lenda (14/10/2026).
Um único miolo, desenhado uma vez, vira tudo:
  - livro.pdf (A5, para ler na tela)          - fl-XX.jpg (páginas do livro folheável e da leitura contínua)
  - imprimir-livreto-a4.pdf (casa: A4 frente e verso, com marcas de corte e dobra)
  - imprimir-a4.pdf (uma página por folha)    - kit da gráfica (miolo com sangria, livreto A3 imposto, capa com sangria, ficha)
Regras de página: 1 página da história = 1 página do livro (a narração vira a página certa); texto do mesmo
tamanho no livro todo; página ilustrada = ilustração sangrada no alto + texto; página só de texto ganha vinheta
em silhueta no pé (nada de buraco branco); capitular e título na fonte da marca (Unifraktur + Alegreya);
rodapé com título e número; contracapa com a marca, a leitura, as redes e o site.
"""
import html, json, pathlib, re

HERE = pathlib.Path(__file__).parent
FONTS = HERE / 'fonts'
SIL = HERE / 'sil'
MM = 72 / 25.4
TW, TH, B = 148, 210, 3            # A5 refilado e sangria (mm)
PW, PH = TW + 2 * B, TH + 2 * B     # página com sangria
COL = {'0': 'Coleção Ouvir', '1': 'Coleção Ler Junto', '2': 'Coleção Aventura'}
# corpo do texto (pt): base e mínimo por coleção; o livro todo usa o mesmo corpo
CORPO = {'0': (17.0, 14.6), '1': (13.8, 12.2), '2': (12.6, 11.0)}
VINHETAS = {'reinos': ['castelo', 'heroi', 'dragao', 'mata'], 'lendas': ['saci', 'mata', 'raposa', 'heroi'],
            'bichos': ['raposa', 'mata', 'unicornio', 'heroi'], 'natal': ['treno', 'mata', 'heroi'],
            'games': ['heroi', 'tapete', 'mata'], 'primeiras': ['heroi', 'mata', 'raposa'], 'classicos': ['mago', 'castelo', 'mata'],
            'detetives': ['heroi', 'mata', 'navio']}
ATIVIDADES = ['certificado', 'desenho', 'quem', 'recado', 'desenho2', 'recado2']
# Capitular gótica só nas letras que uma criança lê como a letra certa (o "O" gótico parece "D", o "A" parece "U").
# As demais usam a Alegreya 800, a outra fonte da marca, no mesmo dourado e tamanho.
GOTICA_OK = set('BCDEGLMNPQRSU')

esc = lambda t: html.escape(str(t or ''))
uri = lambda p: pathlib.Path(p).as_uri()


def gtitulo(t):
    """Título com a inicial gótica da marca (Unifraktur) em dourado."""
    t = str(t or '')
    m = re.search(r'[A-Za-zÀ-ÿ]', t)
    if not m: return esc(t)
    i = m.start()
    c = t[i]; cls = 'gi' if c.upper() in GOTICA_OK and c.isupper() else 'gi r'
    return esc(t[:i]) + f'<span class="{cls}">{esc(c)}</span>' + esc(t[i + 1:])


def paragrafos(txt, capitular):
    """Quebra o texto em parágrafos; a capitular gótica entra na primeira letra (não em travessão de fala)."""
    ps = [p.strip() for p in re.split(r'\n+', str(txt or '')) if p.strip()]
    out = []
    for k, p in enumerate(ps):
        if k == 0 and capitular:
            m = re.match(r'^([«"“]?)([A-Za-zÀ-ÿ])', p)
            if m:
                c = m.group(2); cls = 'cap' if c.upper() in GOTICA_OK else 'cap r'
                p = esc(m.group(1)) + f'<span class="{cls}">{esc(c.upper())}</span>' + esc(p[m.end():])
                out.append(f'<p class="p1">{p}</p>'); continue
        out.append(f'<p>{esc(p)}</p>')
    return ''.join(out)


def qr_svg(od, url):
    import segno
    q = od / 'qr.svg'
    segno.make(url, error='m').save(str(q), scale=4, border=1, dark='#1C1236', light='#F3EDE2')
    return q


CSS = """
@font-face{font-family:Alegreya;src:url(%(f)s/Alegreya[wght].ttf);font-weight:400 900}
@font-face{font-family:Alegreya;font-style:italic;src:url(%(f)s/Alegreya-Italic[wght].ttf);font-weight:400 900}
@font-face{font-family:Gotica;src:url(%(f)s/UnifrakturMaguntia-Book.ttf)}
@font-face{font-family:Sans;src:url(%(f)s/AlegreyaSans-400.woff2);font-weight:400}
@font-face{font-family:Sans;src:url(%(f)s/AlegreyaSans-700.woff2);font-weight:700}
@font-face{font-family:Sans;src:url(%(f)s/AlegreyaSans-800.woff2);font-weight:800}
@page{size:%(pw)smm %(ph)smm;margin:0}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
html,body{margin:0;padding:0}
body{font-family:Alegreya;color:#1C1236;font-kerning:normal;text-rendering:geometricPrecision}
:root{--ink:#1C1236;--ink2:#5A5070;--gold:#DDA53C;--goldd:#A8710F;--paper:#FFFCF5;--paper2:#F3EBDB;--night:#121D42;--night2:#1C1236;--hair:#E4D6B8}
.pg{position:relative;width:%(pw)smm;height:%(ph)smm;overflow:hidden;break-after:page;background:var(--paper)}
.pg:last-child{break-after:auto}
.gi{font-family:Gotica;font-weight:400;color:var(--gold);font-size:1.18em;line-height:.8;margin-right:.02em}.gi.r{font-family:Alegreya;font-weight:800;font-size:1.06em}
/* caixa de texto: margem interna (lombada) maior; sangria de 3 mm somada */
.box{position:absolute;top:21mm;bottom:28mm;display:flex;flex-direction:column}
.odd .box{left:19mm;right:16mm}.even .box{left:16mm;right:19mm}
.txt{font-weight:500;line-height:1.5;color:var(--ink);hyphens:manual;text-wrap:pretty}
.txt p{margin:0 0 .5em}.txt p:last-child{margin-bottom:0}
.cap{float:left;font-family:Gotica;font-weight:400;color:var(--goldd);font-size:3.55em;line-height:.8;margin:.06em .1em 0 0;padding-top:.02em}
.cap.r{font-family:Alegreya;font-weight:800;font-size:3.25em;line-height:.78;margin:.05em .08em 0 0}
.vig{flex:1 1 0;min-height:0;overflow:hidden;display:flex;align-items:flex-end;justify-content:center}
.vig.g i{max-height:88mm}
.vig i{display:block;width:100%%;height:calc(100%% - 7mm);max-height:52mm;background:#E9DEC6;-webkit-mask:var(--m) center bottom/contain no-repeat;mask:var(--m) center bottom/contain no-repeat}
/* capítulo */
.chap{text-align:center;margin:0 0 6.5mm}
.chap .k{font:800 7.4pt Sans;letter-spacing:.24em;text-transform:uppercase;color:var(--goldd)}
.chap h2{font:800 19pt/1.12 Alegreya;margin:2.4mm 0 0;color:var(--ink);text-wrap:balance}
.orn{display:flex;align-items:center;justify-content:center;gap:2.2mm;margin-top:3.4mm}
.orn i{width:14mm;height:.3mm;background:var(--hair)}.orn b{width:1.7mm;height:1.7mm;background:var(--gold);transform:rotate(45deg)}
.ill .chap{margin-bottom:3.5mm}.ill .chap h2{font-size:15.5pt}.ill .chap .orn{display:none}
/* página ilustrada */
.fig{position:absolute;left:0;right:0;top:0;height:var(--ih,115mm);background:#2a2550}
.fig img{width:100%%;height:100%%;object-fit:cover;object-position:50%% 40%%;display:block}
.fig svg{position:absolute;left:0;right:0;bottom:-.4mm;width:100%%;height:9mm;display:block}
.ill .box{top:calc(var(--ih,115mm) + 4mm)}
/* página só de ilustração (quando o texto não cabe junto) */
.so{background:var(--night)}
.so .fig{top:50%%;transform:translateY(-55%%);height:auto}.so .fig img{height:auto;aspect-ratio:4/3}.so .fig svg{display:none}
.so .leg{position:absolute;left:0;right:0;bottom:30mm;text-align:center}.so .orn i{background:#ffffff33}
/* rodapé */
.ft{position:absolute;bottom:13mm;display:flex;align-items:center;gap:3mm;font:700 6.4pt Sans;letter-spacing:.16em;text-transform:uppercase;color:#958BA3;white-space:nowrap}
.odd .ft{left:19mm;right:16mm}.even .ft{left:16mm;right:19mm;flex-direction:row-reverse}
.ft .r{flex:1;height:.25mm;background:var(--hair)}.ft .n{font:800 10.5pt Alegreya;letter-spacing:0;color:var(--goldd)}
.ft .t{overflow:hidden;text-overflow:ellipsis;max-width:78mm}
.so .ft{color:#8E86B5}.so .ft .r{background:#ffffff26}.so .ft .n{color:var(--gold)}
/* capa */
.capa{background:var(--night)}
.capa .bg{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover;object-position:50%% 34%%}
.capa .sh{position:absolute;inset:0;background:linear-gradient(180deg,#0B0820f0 0%%,#0B0820b8 19%%,#0B082000 40%%,#0B082000 74%%,#0B0820cc 100%%)}
.capa .top{position:absolute;left:14mm;right:14mm;top:14mm;text-align:center}
.capa .logo{height:9.5mm;display:block;margin:0 auto 5mm}
.capa h1{margin:0;font:800 27pt/1.06 Alegreya;color:#FFF8EA;letter-spacing:-.005em;text-wrap:balance;text-shadow:0 .6mm 2.4mm #0008}
.capa h1 .gi{font-size:1.24em}
.capa .bot{position:absolute;left:0;right:0;bottom:14mm;text-align:center}
.capa .bot span{display:inline-block;font:800 7.4pt Sans;letter-spacing:.24em;text-transform:uppercase;color:#FFE7A3;padding:2.2mm 5mm;border:.3mm solid #DDA53C99;border-radius:20mm;background:#0B082066}
/* folha de rosto */
.rosto{text-align:center}
.rosto .in{position:absolute;left:22mm;right:22mm;top:30mm;bottom:28mm;display:flex;flex-direction:column;align-items:center}
.rosto .hat{width:15mm;height:15mm}
.rosto .k{font:800 7.4pt Sans;letter-spacing:.24em;text-transform:uppercase;color:var(--goldd);margin-top:7mm}
.rosto h1{font:800 25pt/1.1 Alegreya;margin:6mm 0 0;color:var(--ink);text-wrap:balance}
.rosto .para{font:italic 500 12.5pt/1.4 Alegreya;color:var(--ink2);margin:6mm 0 0}
.rosto .ded{margin-top:auto;margin-bottom:auto;font:italic 500 13.5pt/1.6 Alegreya;color:var(--ink);white-space:pre-line;max-width:92mm;padding:9mm 0 0;position:relative}
.rosto .ded::before{content:"";position:absolute;left:50%%;top:0;width:24mm;margin-left:-12mm;height:.3mm;background:var(--gold)}
.rosto .site{position:absolute;left:0;right:0;bottom:16mm;font:700 7pt Sans;letter-spacing:.2em;text-transform:uppercase;color:#958BA3}
/* fim */
.fim .in{position:absolute;left:20mm;right:20mm;top:26mm;bottom:28mm;display:flex;flex-direction:column;align-items:center;text-align:center}
.fim .f{font:400 64pt/1 Gotica;color:var(--goldd)}
.fim .para{font:italic 500 12pt/1.5 Alegreya;color:var(--ink2);margin:5mm 0 0;max-width:92mm}
.fim .porta{margin-top:auto;background:var(--paper2);border-radius:5mm;padding:8mm 8mm 7mm;width:100%%;position:relative}
.fim .porta .k{font:800 7.2pt Sans;letter-spacing:.22em;text-transform:uppercase;color:var(--goldd)}
.fim .porta p{font:italic 500 13pt/1.5 Alegreya;color:var(--ink);margin:3.4mm 0 0}
.fim .porta small{display:block;margin-top:4.5mm;font:700 8.2pt Sans;letter-spacing:.04em;color:var(--ink2)}
/* atividades */
.atv .in{position:absolute;top:21mm;bottom:28mm;display:flex;flex-direction:column}
.odd.atv .in{left:19mm;right:16mm}.even.atv .in{left:16mm;right:19mm}
.atv .k{font:800 7.4pt Sans;letter-spacing:.24em;text-transform:uppercase;color:var(--goldd);text-align:center}
.atv h2{font:800 18pt/1.15 Alegreya;margin:2.4mm 0 6mm;text-align:center;color:var(--ink)}
.atv .mold{flex:1;border:.6mm dashed #DDA53C;border-radius:5mm}
.atv .lin{flex:1;display:flex;flex-direction:column;justify-content:space-evenly}.atv .lin i{display:block;border-bottom:.35mm solid #D9CDB4;height:0}
.atv .ass{font:italic 500 11pt Alegreya;color:var(--ink2);text-align:center;margin-top:4mm}
.atv ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:3.2mm 6mm}
.atv li{display:flex;align-items:center;gap:3mm;font:500 12pt Alegreya}.atv li b{width:5.5mm;height:5.5mm;border:.45mm solid var(--goldd);border-radius:1.2mm;flex:none}
.atv h3{font:800 14.5pt/1.15 Alegreya;margin:2mm 0 4mm;text-align:center;color:var(--ink)}
.meia .meia1{flex:0 0 auto;padding-bottom:5mm;border-bottom:.35mm solid var(--hair);margin-bottom:5mm}.meia .meia1 ul{gap:2.4mm 6mm}.meia .meia1 li{font-size:11pt}
.meia .meia2{flex:1;display:flex;flex-direction:column;min-height:0}.meia .meia2 h3{margin-top:0}.meia .ass{margin-top:3mm}
.cert{position:absolute;inset:14mm 13mm 24mm;border:.5mm solid var(--gold);border-radius:4mm;padding:3mm}
.cert .in2{border:.25mm solid var(--hair);border-radius:2.6mm;height:100%%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:8mm}
.cert .k{font:800 7.4pt Sans;letter-spacing:.24em;text-transform:uppercase;color:var(--goldd)}
.cert h2{font:800 21pt/1.15 Alegreya;margin:4mm 0 0}.cert .nm{font:800 26pt/1.1 Alegreya;color:var(--goldd);margin:8mm 0 2mm}
.cert p{font:500 12pt/1.55 Alegreya;color:var(--ink);margin:3mm 0 0;max-width:90mm}
.cert .data{margin-top:12mm;width:70mm;border-top:.3mm solid #CBBE9F;padding-top:2mm;font:700 7.2pt Sans;letter-spacing:.16em;text-transform:uppercase;color:#958BA3}
/* contracapa */
.costas{background:radial-gradient(circle at 78%% 10%%,#2B2264 0,#121D42 58%%);color:#F3EDE2}
.costas .in{position:absolute;left:19mm;right:19mm;top:20mm;bottom:20mm;display:flex;flex-direction:column;gap:6.5mm}
.costas .logo{height:12mm;align-self:flex-start}
.costas .mid{margin:auto 0;display:flex;flex-direction:column;gap:5.5mm}
.costas h2{font:800 20pt/1.12 Alegreya;margin:0;color:#F3EDE2}.costas h2 b{color:var(--gold);font-weight:800}
.costas p{font:500 11.2pt/1.52 Alegreya;margin:0;color:#D9D2E6}.costas p b{color:#F3EDE2}
.costas .cta{display:flex;gap:5.5mm;align-items:center;border-top:.35mm solid #DDA53C80;padding-top:6mm}
.costas .cta img{width:24mm;height:24mm;border-radius:2mm;flex:none}
.costas .cta .k{font:800 7.2pt Sans;letter-spacing:.2em;text-transform:uppercase;color:var(--gold);margin-bottom:1.6mm}
.costas .cta .h{font:800 15pt Alegreya;color:#F3EDE2;margin:0}.costas .cta .u{font:700 10pt Sans;color:#F3EDE2;margin-top:1.4mm;line-height:1.35}
.costas .para{font:italic 500 9.2pt Alegreya;color:#A79FBD;text-align:center}
"""

FIT_JS = """() => {
  const pt = v => v + 'pt';
  const base = +document.body.dataset.base, min = +document.body.dataset.min;
  const pages = [...document.querySelectorAll('.pg.hist')];
  const ill = pg => pg.classList.contains('ill');
  const fits = (pg, fs, ih) => { if (ill(pg)) pg.style.setProperty('--ih', ih + 'mm'); const b = pg.querySelector('.box');
    b.querySelector('.txt').style.fontSize = pt(fs); return b.scrollHeight <= b.clientHeight + 0.5; };
  // ilustração: 115 mm (inteira) até 91 mm (corta no máximo ~20% da altura) para o texto caber
  const IH = [115, 112, 109, 106, 103, 100, 97, 94, 91];
  const ok = (pg, fs) => ill(pg) ? IH.some(h => fits(pg, fs, h)) : fits(pg, fs, 0);
  // o mesmo corpo no livro todo: o maior que serve em todas as páginas
  let uni = min;
  for (let fs = base; fs >= min - 1e-6; fs = Math.round((fs - 0.2) * 10) / 10) { if (pages.every(pg => ok(pg, fs))) { uni = fs; break; } }
  const estoura = [];
  pages.forEach(pg => { if (ill(pg)) { const h = IH.find(h => fits(pg, uni, h)); if (h === undefined) { fits(pg, uni, 115); estoura.push(+pg.dataset.h); } }
    else if (!fits(pg, uni, 0)) estoura.push(+pg.dataset.h); });
  document.querySelectorAll('.vig').forEach(v => { if (v.clientHeight < 95) v.style.display = 'none'; });
  const h = document.querySelector('.capa h1');
  if (h) { let s = 27; const lh = () => h.getBoundingClientRect().height / (parseFloat(getComputedStyle(h).fontSize) * 1.06);
    while (lh() > 3.2 && s > 18) { s -= 1; h.style.fontSize = pt(s); } }
  return { uni, estoura };
}"""


def _paginas(h, ilus, dna, od, cfg, so_ilustra=frozenset(), grafica=False):
    """Monta a lista de páginas (HTML). Retorna (html_paginas, mapa_historia->índice da página)."""
    nome = esc(dna['nome']); tit = esc(h.get('titulo', ''))
    fase = str(dna.get('fase', '1'))
    col = COL.get(fase, COL['1'])
    at = {int(x['pagina']): x['arquivo'] for x in ilus}
    vigs = VINHETAS.get(dna.get('familia'), VINHETAS['primeiras'])
    if dna.get('sexo') == 'f': vigs = [('heroina' if v == 'heroi' else v) for v in vigs]
    ded = (dna.get('dedicatoria') or '').strip()
    wave = ('<svg viewBox="0 0 154 9" preserveAspectRatio="none" aria-hidden="true"><path d="M0 5.2C18 1.2 33 1 51 3.6S86 8.6 104 6.4 135 1.4 154 3.8V9H0Z" fill="#FFFCF5"/>'
            '<path d="M0 5.2C18 1.2 33 1 51 3.6S86 8.6 104 6.4 135 1.4 154 3.8" fill="none" stroke="#DDA53C" stroke-width=".35"/></svg>')
    P = []  # (tipo, html_interno, extra_classes, story_index)

    if not grafica:
        P.append(('capa', f'<img class="bg" src="{uri(od / "capa.jpg")}" alt=""><div class="sh"></div>'
                          f'<div class="top"><img class="logo" src="{uri(HERE / "logo.svg")}" alt="Minha Lenda"><h1>{gtitulo(h.get("titulo", ""))}</h1></div>'
                          f'<div class="bot"><span>{esc(col)}</span></div>', '', None))
    P.append(('rosto', f'<div class="in"><img class="hat" src="{uri(SIL / "simbolo.svg")}" alt=""><div class="k">Minha Lenda · {esc(col)}</div>'
                       f'<h1>{gtitulo(h.get("titulo", ""))}</h1><p class="para">Uma lenda criada especialmente para {nome}</p>'
                       + (f'<p class="ded">{esc(ded)}</p>' if ded else '') + '</div><div class="site">minhalenda.com.br</div>', '', None))
    # Miolo fechado em múltiplo de 4 (Ler Junto, 6 a 8 anos: 20 páginas = 5 folhas): rosto + história + Fim + certificado + "quem apareceu/desenho".
    # Se faltar página, as páginas só de texto mais longas se dividem em duas (cada metade ganha vinheta em marca d'água);
    # só se não houver o que dividir entram atividades extras.
    n_ilus = sum(1 for i, p in enumerate(h['paginas']) if at.get(int(p.get('n') or i + 1)))
    miolo = 1 + len(h['paginas']) + len([i for i in so_ilustra if i < len(h['paginas'])]) + 1 + 2
    falta = (-miolo) % 4
    def _pal(t): return len(re.findall(r'[\wÀ-ÿ]+', str(t or '')))
    cands = sorted([i for i, p in enumerate(h['paginas']) if not at.get(int(p.get('n') or i + 1)) and _pal(p.get('texto')) >= 60],
                   key=lambda i: -_pal(h['paginas'][i].get('texto')))
    dividir = set(cands[:falta]); falta -= len(dividir)

    def _metades(txt):
        ps = [x.strip() for x in re.split(r'\n+', str(txt or '')) if x.strip()]
        if len(ps) < 2:
            ps = [x.strip() for x in re.split(r'(?<=[.!?…])\s+', ps[0] if ps else '') if x.strip()]
            sep = ' '
        else: sep = '\n'
        tot = sum(_pal(x) for x in ps); acc = 0; k = 1
        for j, x in enumerate(ps[:-1]):
            acc += _pal(x)
            if acc >= tot / 2: k = j + 1; break
        return sep.join(ps[:k]), sep.join(ps[k:])

    nc = 0
    for i, p in enumerate(h['paginas']):
        n = int(p.get('n') or i + 1)
        capitulo = (p.get('capitulo') or '').strip()
        if capitulo: nc += 1
        chap = (f'<div class="chap"><div class="k">Capítulo {nc}</div><h2>{esc(capitulo)}</h2><div class="orn"><i></i><b></b><i></i></div></div>' if capitulo else '')
        texto = p.get("texto")
        img = at.get(n)
        if img and i in so_ilustra:
            P.append(('so', f'<div class="fig"><img src="{uri(od / img)}" alt=""></div><div class="leg"><div class="orn"><i></i><b></b><i></i></div></div>', '', None))
            img = None
        if img:
            txt = f'<div class="txt">{paragrafos(texto, capitular=bool(capitulo) or i == 0)}</div>'
            P.append(('hist ill', f'<div class="fig"><img src="{uri(od / img)}" alt="">{wave}</div><div class="box" >{chap}{txt}</div>', '', i))
        elif i in dividir:
            t1, t2 = _metades(texto)
            for k2, tt in enumerate((t1, t2)):
                v = vigs[(i + k2) % len(vigs)]
                txt = f'<div class="txt">{paragrafos(tt, capitular=k2 == 0 and (bool(capitulo) or i == 0))}</div>'
                P.append(('hist', f'<div class="box">{chap if k2 == 0 else ""}{txt}<div class="vig g"><i class="v-{v}"></i></div></div>', '', i))
        else:
            v = vigs[i % len(vigs)]
            txt = f'<div class="txt">{paragrafos(texto, capitular=bool(capitulo) or i == 0)}</div>'
            P.append(('hist', f'<div class="box">{chap}{txt}<div class="vig"><i class="v-{v}"></i></div></div>', '', i))
    gancho = (h.get('gancho_proximo') or '').strip()
    P.append(('fim', '<div class="in"><div class="f">Fim</div><div class="orn"><i></i><b></b><i></i></div>'
                     f'<p class="para">Esta lenda foi escrita e ilustrada especialmente para {nome}.</p>'
                     + (f'<div class="porta"><div class="k">Uma portinha ficou aberta…</div><p>{esc(gancho)}</p>'
                        f'<small>No Clube da Lenda, a próxima aventura de {nome} começa daqui · minhalenda.com.br/clube</small></div>' if gancho else '')
                     + '</div>', '', None))
    # atividades fixas: certificado + página dividida (quem apareceu em cima, desenho embaixo); extras só se faltar página
    elenco = [e.get('nome') for e in (dna.get('elenco') or []) if e.get('nome')][:8]
    P.append(('atv', f'<div class="cert"><div class="in2"><div class="k">Minha Lenda</div><h2>Certificado de leitor de lendas</h2>'
                     f'<div class="nm">{nome}</div><p>leu (ou ouviu) a aventura <b>{tit}</b> do começo ao fim.</p>'
                     '<div class="data">Data e assinatura</div></div></div>', '', None))
    if elenco:
        topo = ('<div class="k">Sua vez</div><h3>Quem apareceu nesta aventura? Marque!</h3><ul>' + ''.join(f'<li><b></b>{esc(x)}</li>' for x in elenco) + '</ul>')
    else:
        topo = '<div class="k">Sua vez</div><h3>Quem você levaria na próxima aventura?</h3><div class="lin" style="flex:0 0 26mm"><i></i><i></i><i></i></div>'
    P.append(('atv meia', f'<div class="in"><div class="meia1">{topo}</div><div class="meia2"><h3>Desenhe aqui a sua cena favorita</h3><div class="mold"></div>'
                          f'<div class="ass">Desenhado por {nome}</div></div></div>', '', None))
    for k in range(falta):
        a = ['desenho2', 'recado', 'recado2'][k % 3]
        if a == 'desenho2':
            P.append(('atv', f'<div class="in"><div class="k">Sua vez</div><h2>Invente o que acontece depois</h2><div class="mold"></div><div class="ass">Desenhado por {nome}</div></div>', '', None))
        else:
            t = 'Escreva um recado para o herói' if a == 'recado' else 'Conte a aventura para alguém'
            P.append(('atv', f'<div class="in"><div class="k">Sua vez</div><h2>{t}</h2><div class="lin">' + '<i></i>' * 11 + '</div></div>', '', None))
    if not grafica:
        qr = qr_svg(od, 'https://minhalenda.com.br/clube?o=livro')
        P.append(('costas', f'<div class="in"><img class="logo" src="{uri(HERE / "logo.svg")}" alt="Minha Lenda"><div class="mid">'
                            '<h2>Toda criança tem histórias.<br><b>Aqui, elas viram lendas.</b></h2>'
                            '<p>Cada livro da Minha Lenda é escrito do zero para uma criança só: com o nome dela, as pessoas que ela ama, o bichinho de casa e os desafios que ela está vivendo. Nenhuma história se repete.</p>'
                            '<p><b>Ler junto todos os dias</b> amplia o vocabulário, acalma a hora de dormir e aproxima a família. E, quando a história fala sobre ela, ler deixa de ser tarefa e vira vontade.</p>'
                            f'<p>No <b>Clube da Lenda</b>, {nome} recebe uma aventura nova a cada 15 dias, sempre como herói: para ler junto, ouvir narrada e guardar na estante.</p></div>'
                            f'<div class="cta"><img src="{uri(qr)}" alt=""><div><div class="k">Aponte a câmera e entre para o Clube</div><p class="h">minhalenda.com.br/clube</p>'
                            '<div class="u">Siga @minhalenda<br>Instagram · TikTok · YouTube</div></div></div>'
                            f'<p class="para">Uma lenda criada especialmente para {nome}.</p></div>', '', None))
    # numeração e lados (página 1 = capa, ímpar = direita)
    out, mapa, n0 = [], {}, 0 if not grafica else 1
    for k, (tipo, inner, extra, si) in enumerate(P):
        num = k + 1 + n0
        lado = 'odd' if num % 2 else 'even'
        ft = ''
        if tipo.startswith(('hist', 'so', 'atv', 'fim')):
            ft = f'<div class="ft"><span class="t">{tit}</span><span class="r"></span><span class="n">{num}</span></div>'
        attr = f' data-h="{si}"' if si is not None else ''
        out.append(f'<section class="pg {tipo} {lado}"{attr}>{inner}{ft}</section>')
        if si is not None: mapa.setdefault(si, k)
    return out, mapa


def _vinhetas_css():
    import base64
    out = []
    for f in sorted(SIL.glob('*.svg')):
        b = base64.b64encode(re.sub(rb'<metadata>.*?</metadata>', b'', f.read_bytes(), flags=re.S)).decode()
        out.append(f'.v-{f.stem}{{--m:url("data:image/svg+xml;base64,{b}")}}')
    return '\n'.join(out)


def _render(paginas, od, nome_pdf, cfg):
    from playwright.sync_api import sync_playwright
    base, mn = cfg
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{CSS % {"f": uri(FONTS), "pw": PW, "ph": PH}}{_vinhetas_css()}</style></head>'
           f'<body data-base="{base}" data-min="{mn}">{"".join(paginas)}</body></html>')
    hp = od / (nome_pdf.replace('.pdf', '.html')); hp.write_text(doc, encoding='utf-8')
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(viewport={'width': 900, 'height': 1200})
        pg.goto(hp.as_uri()); pg.wait_for_load_state('networkidle'); pg.evaluate('document.fonts.ready'); pg.wait_for_timeout(300)
        r = pg.evaluate(FIT_JS)
        pg.pdf(path=str(od / nome_pdf), prefer_css_page_size=True, print_background=True)
        br.close()
    return r


def _marca(pg, x0, y0, x1, y1, sang, dobra=True):
    """Marcas de corte nos 4 cantos do retângulo refilado (fora da sangria) e de dobra no meio."""
    G, L = 1.2 * MM, 6 * MM
    s = sang + G
    for x in (x0, x1):
        pg.draw_line((x, y0 - s - L), (x, y0 - s), width=.35); pg.draw_line((x, y1 + s), (x, y1 + s + L), width=.35)
    for y in (y0, y1):
        pg.draw_line((x0 - s - L, y), (x0 - s, y), width=.35); pg.draw_line((x1 + s, y), (x1 + s + L, y), width=.35)
    if dobra:
        xm = (x0 + x1) / 2
        pg.draw_line((xm, y0 - s - L), (xm, y0 - s), width=.35, dashes='[1.5 1.5] 0'); pg.draw_line((xm, y1 + s), (xm, y1 + s + L), width=.35, dashes='[1.5 1.5] 0')


def _livreto(src, dst, folha_w, folha_h, escala, legenda, autocapa=True):
    """Imposição em canoa: cada folha leva 2 páginas por lado; marcas de corte e dobra; sangria externa preservada."""
    import pymupdf
    n = len(src); assert n % 4 == 0, n
    out = pymupdf.open()
    tw, th, bl = TW * escala, TH * escala, B * escala
    cx = folha_w / 2; y0 = (folha_h - th) / 2
    for f in range(n // 4):
        for lado, (esq, dir_) in (('frente', (n - 1 - 2 * f, 2 * f)), ('verso', (2 * f + 1, n - 2 - 2 * f))):
            pg = out.new_page(width=folha_w * MM, height=folha_h * MM)
            # página da esquerda: sangria por fora, corta a da lombada; idem a da direita, espelhada
            pg.show_pdf_page(pymupdf.Rect((cx - tw - bl) * MM, (y0 - bl) * MM, cx * MM, (y0 + th + bl) * MM), src, esq,
                             clip=pymupdf.Rect(0, 0, (B + TW) * MM, PH * MM))
            pg.show_pdf_page(pymupdf.Rect(cx * MM, (y0 - bl) * MM, (cx + tw + bl) * MM, (y0 + th + bl) * MM), src, dir_,
                             clip=pymupdf.Rect(B * MM, 0, PW * MM, PH * MM))
            _marca(pg, (cx - tw) * MM, y0 * MM, (cx + tw) * MM, (y0 + th) * MM, bl * MM)
            pg.insert_text(((cx - tw + 4) * MM, (y0 - bl - 2.4) * MM), f'{legenda} · folha {f + 1} de {n // 4} · {lado}', fontsize=5.6, color=(.45, .42, .5))
    out.save(dst, garbage=3, deflate=True)


def montar(h, ilus, dna, od, pid='', pedido=None, log=print):
    """Gera tudo a partir da história e das ilustrações. Retorna dict com folhas, mapa e kit da gráfica."""
    import pymupdf
    od = pathlib.Path(od)
    fase = str(dna.get('fase', '1'))
    cfg = CORPO.get(fase, CORPO['1'])
    so = set()
    for _ in range(3):
        pags, mapa = _paginas(h, ilus, dna, od, cfg, frozenset(so))
        r = _render(pags, od, 'livro-sangria.pdf', cfg)
        novos = {int(x) for x in r['estoura'] if x is not None} - so
        if not novos: break
        so |= novos  # texto não coube junto da ilustração: a ilustração ganha página própria antes do texto
        log('diagramação: ilustração em página própria nas páginas', sorted(novos))
    src = pymupdf.open(od / 'livro-sangria.pdf'); n = len(src)
    log('diagramação ok:', n, 'páginas, corpo', r['uni'], 'pt')
    # 1) livro.pdf refilado (A5)
    trim = pymupdf.Rect(B * MM, B * MM, (B + TW) * MM, (B + TH) * MM)
    liv = pymupdf.open()
    for i in range(n):
        p = liv.new_page(width=TW * MM, height=TH * MM); p.show_pdf_page(p.rect, src, i, clip=trim)
    liv.set_metadata({'title': h.get('titulo', ''), 'author': 'Minha Lenda', 'subject': f'Uma lenda criada especialmente para {dna["nome"]}', 'creator': 'Minha Lenda'})
    liv.save(od / 'livro.pdf', garbage=3, deflate=True)
    # 2) páginas em imagem para o livro folheável e a leitura contínua
    from PIL import Image
    folhas = []
    for i, p in enumerate(liv):
        pix = p.get_pixmap(dpi=165)
        im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        nome = f'fl-{i + 1:02d}.jpg'; im.save(od / nome, 'JPEG', quality=82, optimize=True, progressive=True); folhas.append(nome)
    # 3) casa: livreto A4 (90%, marcas de corte e dobra) e uma página por folha A4
    # casa: capa e contracapa sem nada no verso (como na gráfica): entra uma página em branco depois da capa e antes da contracapa
    casa = pymupdf.open(); casa.insert_pdf(src)
    while len(casa) % 4:
        casa.new_page(pno=1 if len(casa) % 2 == 0 else len(casa) - 1, width=PW * MM, height=PH * MM)
    _livreto(casa, str(od / 'imprimir-livreto-a4.pdf'), 297, 210, 0.9,
             'Minha Lenda · imprima em tamanho real (100%), frente e verso virando na borda curta · corte nas marcas · dobre e grampeie')
    a4 = pymupdf.open(); esc_a4 = min(200 / TW, 287 / TH)
    for i in range(n):
        p = a4.new_page(width=210 * MM, height=297 * MM)
        w, hh = TW * esc_a4, TH * esc_a4
        p.show_pdf_page(pymupdf.Rect((210 - w) / 2 * MM, (297 - hh) / 2 * MM, (210 + w) / 2 * MM, (297 + hh) / 2 * MM), src, i, clip=trim)
    a4.save(od / 'imprimir-a4.pdf', garbage=3, deflate=True)
    # mapa: página da história -> página do livro (índice das imagens fl-XX)
    folha_de = [mapa.get(i, 0) for i in range(len(h['paginas']))]
    kit = grafica(h, ilus, dna, od, pid, pedido, cfg, so, src, log) if (pedido or {}).get('produto') == 'impresso' else []
    return {'folhas': folhas, 'folha_de': folha_de, 'kit': kit, 'paginas': n, 'corpo': r['uni']}


FICHA = """MINHA LENDA · FICHA PARA A GRÁFICA · pedido {pid}

QUANTIDADE: {qtd} livro(s) iguais · formato final A5 (148 x 210 mm), grampo canoa

MIOLO ({paginas} páginas = {folhas} folhas frente e verso)
- grafica-miolo-livreto-a3.pdf: já imposto, 1 lâmina A3 (ou SRA3) por folha, frente e verso virando na
  borda curta, com sangria de 3 mm e marcas de corte e dobra. Refilar em 296 x 210 mm e dobrar ao meio.
- grafica-miolo-a5-sangria.pdf: as mesmas páginas em ordem (154 x 216 mm, 3 mm de sangria), se a gráfica
  preferir fazer a imposição.
- Papel: offset 90 g/m² (120 g/m² se quiser mais encorpado), 4x4 cores.

CAPA (1 lâmina por livro, só de um lado: 4x0)
- grafica-capa-a3.pdf: contracapa à esquerda, capa à direita, sangria de 3 mm, marcas de corte e de dobra.
- Papel: couché brilho 250 a 300 g/m² ou cartão; laminação brilho opcional.

ACABAMENTO
- Miolo dentro da capa, dobra ao meio, 2 grampos na dobra (canoa). Refile frontal opcional.
- Conferir: a folha de rosto (título e dedicatória) vem logo depois da capa.

ENTREGA
{endereco}
Frete: {frete}
"""


def grafica(h, ilus, dna, od, pid, pedido, cfg, so, livro_src, log=print):
    """Kit da gráfica: miolo sem capa (rosto ao fim, completado com atividades até múltiplo de 4) com sangria,
    livreto A3 imposto com marcas, capa A3 (contracapa + capa) com sangria e marcas, e a ficha."""
    import pymupdf
    od = pathlib.Path(od)
    pags, _ = _paginas(h, ilus, dna, od, cfg, frozenset(so), grafica=True)
    _render(pags, od, 'grafica-miolo-a5-sangria.pdf', cfg)
    mi = pymupdf.open(od / 'grafica-miolo-a5-sangria.pdf')
    for p in mi:
        try: p.set_trimbox(pymupdf.Rect(B * MM, B * MM, (B + TW) * MM, (B + TH) * MM))
        except Exception: pass
    mi.save(od / 'grafica-miolo-a5-sangria.tmp.pdf', garbage=3, deflate=True)
    (od / 'grafica-miolo-a5-sangria.tmp.pdf').replace(od / 'grafica-miolo-a5-sangria.pdf')
    mi = pymupdf.open(od / 'grafica-miolo-a5-sangria.pdf'); n = len(mi)
    _livreto(mi, str(od / 'grafica-miolo-livreto-a3.pdf'), 420, 297, 1.0, f'Minha Lenda {pid} · miolo 4x4 offset 90 g · sangria 3 mm · refilar nas marcas · tracejado = dobra')
    # capa: contracapa (última página do livro) + capa (primeira), lado a lado, só sangria externa
    capa = pymupdf.open(); folha_w, folha_h = 420, 297
    pg = capa.new_page(width=folha_w * MM, height=folha_h * MM)
    cx, y0 = folha_w / 2, (folha_h - TH) / 2
    nl = len(livro_src)
    pg.show_pdf_page(pymupdf.Rect((cx - TW - B) * MM, (y0 - B) * MM, cx * MM, (y0 + TH + B) * MM), livro_src, nl - 1, clip=pymupdf.Rect(0, 0, (B + TW) * MM, PH * MM))
    pg.show_pdf_page(pymupdf.Rect(cx * MM, (y0 - B) * MM, (cx + TW + B) * MM, (y0 + TH + B) * MM), livro_src, 0, clip=pymupdf.Rect(B * MM, 0, PW * MM, PH * MM))
    _marca(pg, (cx - TW) * MM, y0 * MM, (cx + TW) * MM, (y0 + TH) * MM, B * MM)
    pg.insert_text(((cx - TW) * MM, (y0 + TH + B + 7) * MM), f'Minha Lenda {pid} · capa 4x0 couché 250-300 g · sangria 3 mm · refilar nas marcas · tracejado = dobra', fontsize=6, color=(.45, .42, .5))
    capa.save(od / 'grafica-capa-a3.pdf', garbage=3, deflate=True)
    e = json.loads((pedido or {}).get('endereco_json') or '{}')
    endereco = f"{e.get('destinatario') or ''}\n{e.get('rua', '')}, {e.get('numero', '')} {e.get('compl') or ''}\n{e.get('bairro', '')} · {e.get('cidade', '')}/{e.get('uf', '')} · CEP {e.get('cep', '')}"
    (od / 'grafica-ficha.txt').write_text(FICHA.format(pid=pid, qtd=1 + int((pedido or {}).get('copias') or 0), paginas=n, folhas=n // 4, endereco=endereco,
                                                       frete=(pedido or {}).get('frete_info') or '-'), encoding='utf-8')
    log('gráfica ok:', n, 'páginas de miolo,', n // 4, 'folhas + capa')
    return ['grafica-miolo-livreto-a3.pdf', 'grafica-miolo-a5-sangria.pdf', 'grafica-capa-a3.pdf', 'grafica-ficha.txt']
