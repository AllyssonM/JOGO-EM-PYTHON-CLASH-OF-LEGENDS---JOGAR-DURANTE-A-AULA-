#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLASH OF LEGENDS  -  RPG de luta 2D em Python (pygame)

Recursos
  * Motor com Delta Time (sub-passos fixos): roda igual em 60 Hz, 144 Hz ou 240 Hz
  * Colisao por retangulos (AABB): Hurtbox (recebe dano) x Hitbox (causa dano)
  * Golpes em 3 fases: Startup -> Active -> Recovery (+ hitstun e hit-stop)
  * RPG: nivel, XP, atributos que crescem
  * Modo Historia: prologo + 5 atos com dialogos, chefe e final decidido pelo SEU jeito de lutar
  * Modos: Luta vs Maquina (1P, 3 dificuldades) e 1 vs 1 local (2P)
  * Uniformes: 4 roupas por heroi, desbloqueadas pelo nivel (Q/E na selecao)
  * 17 herois jogaveis, incluindo 11 originais inspirados no jeitao dos grandes shonens
  * Arte propria: coloque PNGs em personagens/<nome>/ (veja personagens/LEIA-ME.txt)
  * Estilo ninja/anime: carregar energia, substituicao, jutsu final cinematografico e Despertar
  * O Pouso: fazenda com estacoes, mercado, mina com lutas e Vila do Cla que sofre incursoes
  * Graficos 100% procedurais: personagens com esqueleto (IK), paralaxe,
    particulas, brilho aditivo, tremor de tela, numeros de dano, HUD animado
  * Audio sintetizado em codigo (sem arquivos externos)

Controles (tambem em "CONTROLES" no menu)
  Jogador 1:  A/D mover  W pular  S defender   J soco  K chute  L especial  U chakra  I jutsu final
              (no modo Historia tambem: setas + Z/X/C/V/B)
  Jogador 2:  Setas mover/pular/defender        N soco  M chute  , especial  . chakra  / jutsu final
              (ou teclado numerico 1-5)
  Enter confirma | Esc volta/pausa | F11 tela cheia

Requisitos:  pip install pygame-ce   |  Execute:  python clash_of_legends.py  (no Windows: py clash_of_legends.py)
"""
import array
import glob
import json
import math
import os
import random
import sys

import pygame

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------
W, H = 1280, 720
GROUND = 612            # y dos pes dos lutadores
HORIZON = 540           # onde o chao comeca visualmente
STAGE_L, STAGE_R = 60, W - 60
GRAV = 2600.0
MAX_SUBSTEP = 1.0 / 90.0
ROUND_TIME = 60
OUT = (14, 10, 24)
WHITE = (255, 255, 255)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_pt(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def shade(c, f):
    return tuple(clamp(int(v * f), 0, 255) for v in c)


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_io(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------
# Texto, brilho, barras
# ----------------------------------------------------------------------------
_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def text(surf, s, size, pos, col=WHITE, anchor="center", shadow=(0, 0, 0), sh=2):
    f = font(size)
    img = f.render(s, True, col)
    r = img.get_rect()
    setattr(r, anchor, (int(pos[0]), int(pos[1])))
    if shadow:
        surf.blit(f.render(s, True, shadow), r.move(sh, sh))
    surf.blit(img, r)
    return r


_glow_cache = {}


def glow_surface(radius, color):
    radius = max(8, int(radius) // 4 * 4)
    key = (radius, color)
    s = _glow_cache.get(key)
    if s is None:
        s = pygame.Surface((radius * 2, radius * 2))
        for r in range(radius, 0, -2):
            k = (1 - r / radius) ** 2
            pygame.draw.circle(s, tuple(int(v * k) for v in color), (radius, radius), r)
        _glow_cache[key] = s
    return s


def add_glow(dst, pos, radius, color):
    s = glow_surface(radius, color)
    rr = s.get_width() // 2
    dst.blit(s, (int(pos[0]) - rr, int(pos[1]) - rr), special_flags=pygame.BLEND_RGB_ADD)


def slant_bar(dst, x, y, w, h, frac, c_hi, c_lo, anchor_right=False,
              slant=16, back=(18, 14, 30), trail=None, trail_col=(255, 255, 255)):
    def poly(xa, xb, y0f, y1f):
        return [(xa + slant * (1 - y0f), y + h * y0f), (xb + slant * (1 - y0f), y + h * y0f),
                (xb + slant * (1 - y1f), y + h * y1f), (xa + slant * (1 - y1f), y + h * y1f)]

    pygame.draw.polygon(dst, OUT, poly(x - 4, x + w + 4, -0.18, 1.18))
    pygame.draw.polygon(dst, back, poly(x, x + w, 0, 1))

    def span(f):
        fw = w * clamp(f, 0, 1)
        return (x + w - fw, x + w) if anchor_right else (x, x + fw)

    if trail is not None and trail > frac:
        a, b = span(trail)
        pygame.draw.polygon(dst, trail_col, poly(a, b, 0, 1))
    if frac > 0:
        a, b = span(frac)
        pygame.draw.polygon(dst, c_lo, poly(a, b, 0, 1))
        pygame.draw.polygon(dst, c_hi, poly(a, b, 0, 0.5))
        pygame.draw.polygon(dst, mix(c_hi, WHITE, 0.45), poly(a, b, 0, 0.14))


# ----------------------------------------------------------------------------
# Audio sintetizado
# ----------------------------------------------------------------------------
RATE = 22050


def synth(f0, f1, dur, vol=0.35, noise=0.0, square=False):
    n = int(RATE * dur)
    buf = array.array("h")
    ph = 0.0
    for i in range(n):
        k = i / n
        ph += 2 * math.pi * (f0 + (f1 - f0) * k) / RATE
        s = math.sin(ph)
        if square:
            s = 1.0 if s > 0 else -1.0
        s = s * (1 - noise) + random.uniform(-1, 1) * noise
        buf.append(int(s * (1 - k) ** 2 * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Sfx:
    def __init__(self):
        self.ok = False
        self.s = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            self.s = {
                "punch": synth(220, 80, 0.12, 0.45, 0.6),
                "kick": synth(160, 50, 0.18, 0.55, 0.55),
                "block": synth(500, 300, 0.09, 0.3, 0.2, True),
                "special": synth(200, 900, 0.35, 0.3, 0.1, True),
                "swing": synth(700, 200, 0.08, 0.12, 0.8),
                "ko": synth(300, 30, 0.7, 0.6, 0.5),
                "jump": synth(260, 520, 0.1, 0.18),
                "move": synth(660, 760, 0.05, 0.15, 0.0, True),
                "ok": synth(500, 1000, 0.15, 0.25, 0.0, True),
                "land": synth(120, 50, 0.08, 0.3, 0.7),
                "level": synth(400, 1400, 0.5, 0.3, 0.0, True),
            }
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and name in self.s:
            try:
                self.s[name].play()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# Dados: personagens, golpes, fases
# ----------------------------------------------------------------------------
ROSTER = [
    dict(name="ZENO", title="O Guerreiro Solar", skin=(240, 192, 152), main=(228, 88, 38),
         accent=(255, 208, 72), hair=(46, 28, 22), style="spiky", cape=(190, 50, 30),
         hp=100, spd=1.0, pow=1.0, scale=1.0,
         special=dict(name="Bola Solar", type="proj", shape="orb", col=(255, 150, 40), dmg=12,
                      start=0.22, active=0.05, rec=0.34, speed=720, size=20, cost=50)),
    dict(name="LYRA", title="Arqueira do Trovao", skin=(236, 200, 184), main=(54, 140, 255),
         accent=(190, 236, 255), hair=(226, 238, 255), style="long", cape=None,
         hp=90, spd=1.12, pow=0.95, scale=0.97,
         special=dict(name="Flecha Trovao", type="proj", shape="arrow", col=(120, 200, 255), dmg=11,
                      start=0.16, active=0.05, rec=0.26, speed=1250, size=12, cost=45)),
    dict(name="PIXELION", title="Sentinela Digital", skin=(150, 205, 215), main=(112, 72, 224),
         accent=(80, 255, 200), hair=(60, 40, 120), style="visor", cape=None,
         hp=105, spd=0.95, pow=1.0, scale=1.03,
         special=dict(name="Pixel Burst", type="proj", shape="big", col=(80, 255, 200), dmg=15,
                      start=0.30, active=0.05, rec=0.42, speed=480, size=34, cost=55)),
    dict(name="SOMBRA", title="Ninja do Eclipse", skin=(206, 172, 150), main=(44, 42, 66),
         accent=(196, 72, 255), hair=(20, 18, 30), style="hood", cape=(150, 40, 220),
         hp=85, spd=1.22, pow=1.05, scale=0.98,
         special=dict(name="Investida Sombria", type="dash", col=(196, 72, 255), dmg=16,
                      start=0.14, active=0.30, rec=0.36, speed=1250, reach=96, h=90, yc=84, cost=50)),
    dict(name="BRASA", title="Gigante Vulcanico", skin=(196, 124, 92), main=(150, 40, 32),
         accent=(255, 128, 32), hair=(70, 30, 20), style="bulky", cape=None,
         hp=130, spd=0.80, pow=1.15, scale=1.18,
         special=dict(name="Terremoto", type="slam", col=(255, 140, 40), dmg=18,
                      start=0.36, active=0.10, rec=0.46, reach=240, h=46, cost=55)),
    # Arte: "Fighter Moustache Man" por nemezes (OpenGameArt.org, CC0) -> personagens/bigode/quadros/
    dict(name="BIGODE", title="Mestre do Punho de Rua", skin=(200, 140, 100), main=(214, 48, 48),
         accent=(255, 206, 80), hair=(30, 24, 24), style="spiky", cape=None,
         hp=110, spd=1.0, pow=1.08, scale=1.0,
         move_mods={"kick": dict(yc=104, reach=118, h=46)},
         special=dict(name="Investida do Bigode", type="dash", col=(255, 120, 60), dmg=15,
                      start=0.16, active=0.30, rec=0.36, speed=1150, reach=96, h=90, yc=100, cost=50)),
    # --- herois originais (inspirados no jeitao de grandes shonens, com visual e poderes proprios) ---
    dict(name="KAZE", title="Ninja do Vendaval", skin=(236, 196, 160), main=(70, 110, 90),
         accent=(180, 255, 220), hair=(60, 200, 170), style="wild", cape=(40, 160, 120),
         hp=95, spd=1.15, pow=1.00, scale=1.00,
         special=dict(name="Lamina de Vento", type="proj", shape="arrow", col=(170, 255, 220), dmg=11,
                      start=0.16, active=0.05, rec=0.26, speed=1150, size=12, cost=45)),
    dict(name="TORAN", title="Punho Estelar", skin=(232, 186, 150), main=(40, 50, 110),
         accent=(255, 240, 180), hair=(150, 30, 40), style="wild", cape=None,
         hp=105, spd=1.05, pow=1.08, scale=1.00,
         awake_hair=(225, 232, 245),
         special=dict(name="Cometa", type="proj", shape="orb", col=(255, 240, 150), dmg=13,
                      start=0.22, active=0.05, rec=0.34, speed=760, size=22, cost=50)),
    dict(name="VARN", title="Principe Rubro", skin=(224, 180, 146), main=(30, 30, 38),
         accent=(225, 40, 64), hair=(24, 20, 28), style="short", cape=(140, 20, 34),
         hp=100, spd=1.05, pow=1.12, scale=1.00,
         awake_hair=(255, 120, 140),
         special=dict(name="Investida Carmesim", type="dash", col=(230, 40, 70), dmg=16,
                      start=0.14, active=0.30, rec=0.36, speed=1250, reach=96, h=90, yc=84, cost=50)),
    dict(name="KAIRO", title="O Herdeiro", skin=(230, 190, 156), main=(92, 62, 142),
         accent=(255, 200, 120), hair=(96, 64, 40), style="short", cape=None,
         hp=100, spd=1.00, pow=1.05, scale=1.00,
         special=dict(name="Esfera do Herdeiro", type="proj", shape="big", col=(190, 140, 255), dmg=15,
                      start=0.28, active=0.05, rec=0.40, speed=520, size=30, cost=55)),
    dict(name="REI", title="Lamina do Eclipse", skin=(230, 198, 176), main=(30, 24, 50),
         accent=(150, 100, 255), hair=(222, 222, 232), style="long", cape=None,
         hp=90, spd=1.15, pow=1.08, scale=1.00,
         weapon="katana",
         special=dict(name="Corte Relampago", type="dash", col=(150, 100, 255), dmg=15,
                      start=0.12, active=0.28, rec=0.36, speed=1300, reach=110, h=90, yc=96, cost=50)),
    dict(name="ORIN", title="Irmao da Nevoa", skin=(220, 190, 170), main=(62, 72, 82),
         accent=(120, 255, 230), hair=(40, 70, 60), style="hood", cape=(90, 112, 122),
         hp=92, spd=1.05, pow=1.04, scale=1.00,
         special=dict(name="Nevoa Viva", type="proj", shape="big", col=(150, 255, 230), dmg=14,
                      start=0.26, active=0.05, rec=0.38, speed=460, size=34, cost=50)),
    dict(name="MORGRAN", title="O Primeiro Lorde", skin=(200, 170, 150), main=(40, 62, 40),
         accent=(200, 255, 90), hair=(40, 30, 24), style="horns", cape=(70, 36, 22),
         hp=135, spd=0.85, pow=1.15, scale=1.12,
         special=dict(name="Raizes Ancestrais", type="slam", col=(170, 230, 80), dmg=18,
                      start=0.36, active=0.10, rec=0.46, reach=240, h=46, cost=55)),
    dict(name="PIP", title="O Rastreador", skin=(236, 196, 160), main=(150, 105, 60),
         accent=(120, 210, 255), hair=(200, 110, 50), style="wild", cape=None,
         hp=95, spd=1.20, pow=1.00, scale=0.92,
         special=dict(name="Bote do Instinto", type="dash", col=(120, 210, 255), dmg=14,
                      start=0.14, active=0.28, rec=0.34, speed=1100, reach=92, h=86, yc=80, cost=45)),
    dict(name="NIX", title="Herdeiro das Sombras", skin=(226, 196, 176), main=(40, 60, 70),
         accent=(190, 120, 255), hair=(40, 30, 60), style="short", cape=None,
         hp=88, spd=1.25, pow=1.02, scale=0.95,
         special=dict(name="Garras de Trovao", type="dash", col=(190, 120, 255), dmg=15,
                      start=0.12, active=0.28, rec=0.34, speed=1350, reach=96, h=86, yc=84, cost=50)),
    dict(name="GRAM", title="O Sem-Grimorio", skin=(214, 160, 120), main=(120, 90, 60),
         accent=(184, 184, 196), hair=(110, 72, 44), style="short", cape=None,
         hp=125, spd=0.90, pow=1.15, scale=1.08,
         weapon="stone", muscle=True,
         special=dict(name="Golpe de Pedra", type="slam", col=(190, 190, 200), dmg=19,
                      start=0.38, active=0.10, rec=0.46, reach=230, h=46, cost=55)),
    dict(name="ELIAN", title="Rival do Vento", skin=(236, 204, 180), main=(232, 236, 242),
         accent=(120, 200, 255), hair=(240, 220, 170), style="long", cape=(120, 170, 220),
         hp=92, spd=1.12, pow=1.05, scale=1.00,
         special=dict(name="Rajada Cortante", type="proj", shape="arrow", col=(150, 210, 255), dmg=12,
                      start=0.16, active=0.05, rec=0.26, speed=1250, size=12, cost=45)),
]

BOSS = dict(name="MALAKAR", title="Imperador do Vazio", skin=(176, 152, 196), main=(52, 20, 74),
            accent=(255, 44, 100), hair=(24, 10, 34), style="horns", cape=(120, 16, 60),
            hp=150, spd=0.95, pow=1.2, scale=1.14, boss=True,
            special=dict(name="Chama do Vazio", type="proj", shape="big", col=(255, 44, 100), dmg=17,
                         start=0.26, active=0.05, rec=0.36, speed=620, size=38, cost=45))

QUOTES = {
    "ZENO": "Eu sou Zeno, o Guerreiro Solar! Prepare-se pra ficar de olho fechado de tanto brilho!",
    "LYRA": "Lyra, do Trovao. Se a flecha errar, o raio acerta por mim.",
    "PIXELION": "Iniciando protocolo de combate. Chance de vitoria: 99,7%. A minha, claro.",
    "SOMBRA": "Voce nao me viu chegar. Ninguem ve. E meio chato, na verdade.",
    "BRASA": "Tenho tres filhos, dois gatos e um vulcao pra cuidar. Vamos resolver isso rapido.",
    "MALAKAR": "Todo sol precisa de uma sombra. Todo ciclo, de um fim.",
    "BIGODE": "Esse bigode ja venceu mais lutas do que voce ja viu. E ele nem estava tentando.",
    "KAZE": "Se eu cair, levanto. Se cair de novo, levanto com tres clones!",
    "TORAN": "Voce parece forte! Isso vai ser divertido!",
    "VARN": "Ajoelhe-se. Hoje eu so luto contra quem merece o meu tempo.",
    "KAIRO": "Eu prefiro os livros... mas nao vou deixar voce machucar ninguem.",
    "REI": "Minha lamina nao hesita. E eu tambem nao.",
    "ORIN": "O que voce ve nem sempre e o que esta la.",
    "MORGRAN": "Eu ja estava aqui antes das Terras terem nome.",
    "PIP": "Senti seu cheiro la da floresta! Vamos brincar de luta?",
    "NIX": "Voce nem vai ver de onde veio o trovao.",
    "GRAM": "Nao tenho magia. Tenho esta pedra. E muita teimosia.",
    "ELIAN": "O vento nao discute. Ele apenas corta.",
}
for _c in ROSTER + [BOSS]:
    _c["quote"] = QUOTES[_c["name"]]

# Jutsu final de cada heroi: (nome, tipo de efeito)
ULTS = {
    "ZENO": ("Supernova Solar", "beam"),
    "LYRA": ("Chuva de Relampagos", "storm"),
    "PIXELION": ("Protocolo Omega", "beam"),
    "SOMBRA": ("Clones do Eclipse", "clones"),
    "BRASA": ("Erupcao Titanica", "quake"),
    "BIGODE": ("Mil Socos do Bigode", "flurry"),
    "MALAKAR": ("Vazio Absoluto", "beam"),
    "KAZE": ("Tempestade de Clones", "clones"),
    "TORAN": ("Cometa Estelar", "beam"),
    "VARN": ("Ruina Carmesim", "beam"),
    "KAIRO": ("Onda do Herdeiro", "beam"),
    "REI": ("Trovao do Eclipse", "storm"),
    "ORIN": ("Ilusao da Nevoa", "clones"),
    "MORGRAN": ("Floresta Ancestral", "quake"),
    "PIP": ("Furia Selvagem", "flurry"),
    "NIX": ("Danca das Garras", "flurry"),
    "GRAM": ("Rocha Devoradora", "quake"),
    "ELIAN": ("Furacao Celeste", "storm"),
}
ULT_GEOM = {"beam": dict(reach=760, h=120, yc=112), "storm": dict(reach=560, h=300, yc=150),
            "quake": dict(reach=420, h=130, yc=65), "clones": dict(reach=130, h=120, yc=92),
            "flurry": dict(reach=130, h=120, yc=92)}
ULT_RANGE = {"beam": 700, "storm": 560, "quake": 380, "clones": 450, "flurry": 420}
AWAKE_HAIR = (255, 228, 90)

# --- Uniformes (roupas) -------------------------------------------------------
OUTFIT_LEVELS = (1, 2, 4, 6)
OUTFITS = {
    "ZENO": [
        dict(name="Classico"),
        dict(name="Mar Azul", main=(40, 110, 220), accent=(240, 245, 255), cape=(20, 60, 150)),
        dict(name="Eclipse", main=(42, 38, 54), accent=(255, 84, 60), cape=(120, 20, 24), hair=(20, 16, 22)),
        dict(name="Sol Lendario", main=(250, 244, 232), accent=(255, 198, 40), cape=(255, 160, 30),
             hair=(255, 214, 80), extras=("ombreiras", "aura")),
    ],
    "LYRA": [
        dict(name="Classico"),
        dict(name="Tempestade", main=(124, 62, 206), accent=(255, 238, 120), hair=(46, 34, 66)),
        dict(name="Noite", main=(30, 40, 72), accent=(120, 222, 255), hair=(22, 22, 34), cape=(20, 28, 54)),
        dict(name="Rainha do Raio", main=(245, 245, 255), accent=(255, 214, 60), hair=(255, 248, 214),
             cape=(255, 214, 60), extras=("ombreiras", "aura")),
    ],
    "PIXELION": [
        dict(name="Classico"),
        dict(name="Glitch", main=(226, 58, 92), accent=(255, 240, 80)),
        dict(name="Carbono", main=(52, 56, 62), accent=(255, 124, 30), hair=(30, 30, 34)),
        dict(name="Codigo Dourado", main=(238, 196, 76), accent=(110, 255, 255), extras=("ombreiras", "aura")),
    ],
    "SOMBRA": [
        dict(name="Classico"),
        dict(name="Lua Rubra", main=(92, 20, 32), accent=(255, 64, 84), cape=(200, 30, 52)),
        dict(name="Neve", main=(226, 230, 240), accent=(90, 160, 255), cape=(150, 190, 255), hair=(200, 210, 230)),
        dict(name="Eclipse Total", main=(22, 12, 32), accent=(255, 198, 60), cape=(255, 186, 40),
             extras=("ombreiras", "aura")),
    ],
    "BRASA": [
        dict(name="Classico"),
        dict(name="Granito", main=(92, 92, 104), accent=(120, 220, 255)),
        dict(name="Magma Negro", main=(32, 24, 24), accent=(255, 64, 20), hair=(22, 10, 10)),
        dict(name="Tita Dourado", main=(220, 168, 58), accent=(255, 248, 200), extras=("ombreiras", "aura")),
    ],
    "BIGODE": [
        dict(name="Classico"),
        dict(name="Noite Azul", tint=(150, 172, 255), accent=(140, 200, 255)),
        dict(name="Brasa Viva", tint=(255, 168, 128), accent=(255, 120, 60)),
        dict(name="Bigode de Ouro", tint=(255, 226, 130), accent=(255, 230, 120), extras=("aura",)),
    ],
}


def default_outfits(ch):
    m, a = ch["main"], ch["accent"]
    cape = ch.get("cape")
    return [dict(name="Classico"),
            dict(name="Sombrio", main=shade(m, 0.45), cape=shade(cape, 0.5) if cape else None),
            dict(name="Inverso", main=shade(a, 0.62), accent=mix(m, WHITE, 0.55), cape=shade(a, 0.45) if cape else None),
            dict(name="Lendario", main=(245, 242, 232), accent=(255, 200, 50), cape=(255, 170, 40) if cape else None,
                 extras=("ombreiras", "aura"))]


for _c in ROSTER:
    if _c["name"] not in OUTFITS:
        OUTFITS[_c["name"]] = default_outfits(_c)


def outfit_ch(ch, idx):
    """Copia o personagem com as cores/acessorios do uniforme escolhido."""
    lst = OUTFITS.get(ch["name"])
    d = dict(ch)
    if not lst:
        d.update(extras=(), outfit_idx=0, outfit_name="Classico")
        return d
    idx = max(0, min(int(idx), len(lst) - 1))
    o = lst[idx]
    for k in ("main", "accent", "hair", "cape", "skin", "tint"):
        if k in o:
            d[k] = o[k]
    d["extras"] = tuple(o.get("extras", ()))
    d["outfit_idx"] = idx
    d["outfit_name"] = o["name"]
    return d


def outfits_unlocked_between(name, old_lv, new_lv):
    lst = OUTFITS.get(name, [])
    return [o["name"] for i, o in enumerate(lst) if old_lv < OUTFIT_LEVELS[i] <= new_lv]


THEMES = [
    dict(name="Templo do Crepusculo", top=(26, 16, 70), bot=(255, 130, 84), orb=(255, 214, 150),
         far="mount", near="forest", c1=(78, 44, 110), c2=(40, 22, 70), floor=(86, 48, 84), line=(255, 170, 120)),
    dict(name="Metropole Neon", top=(8, 8, 38), bot=(156, 40, 150), orb=(255, 206, 244),
         far="city", near="city", c1=(46, 22, 92), c2=(24, 12, 54), floor=(34, 22, 70), line=(255, 70, 224)),
    dict(name="Floresta Cristal", top=(4, 28, 50), bot=(34, 158, 156), orb=(206, 255, 240),
         far="mount", near="forest", c1=(14, 80, 96), c2=(6, 44, 60), floor=(14, 70, 82), line=(120, 255, 230)),
    dict(name="Vulcao Ardente", top=(30, 6, 8), bot=(255, 98, 26), orb=(255, 170, 70),
         far="mount", near="spike", c1=(84, 24, 22), c2=(40, 10, 12), floor=(70, 26, 22), line=(255, 130, 40)),
    dict(name="Abismo do Vazio", top=(4, 0, 16), bot=(110, 0, 84), orb=(255, 80, 144),
         far="float", near="spike", c1=(46, 8, 72), c2=(20, 4, 36), floor=(34, 8, 54), line=(255, 60, 130)),
]

BASE_MOVES = {
    "punch": dict(type="melee", start=0.07, active=0.07, rec=0.15, dmg=5, reach=88, h=38, yc=112,
                  stun=0.28, kb=210, pop=0, cost=0, sfx="punch", hs=0.05),
    "kick": dict(type="melee", start=0.13, active=0.09, rec=0.27, dmg=9, reach=116, h=42, yc=62,
                 stun=0.44, kb=400, pop=240, cost=0, sfx="kick", hs=0.085),
}


def build_moves(ch):
    mv = {k: dict(v) for k, v in BASE_MOVES.items()}
    sp = dict(ch["special"])
    sp.setdefault("stun", 0.55)
    sp.setdefault("kb", 520)
    sp.setdefault("pop", 420)
    sp["sfx"] = "special"
    sp["hs"] = 0.12
    if sp["type"] == "slam":
        sp["ground_only"] = True
        sp["pop"] = 380
    mv["special"] = sp
    nm, kind = ULTS.get(ch["name"], ("Golpe Final", "beam"))
    ult = dict(type="ult", kind=kind, name=nm, col=ch["special"]["col"], start=0.10, active=0.40, rec=0.50,
               dmg=30, hits=5, stun=0.9, kb=640, pop=560, hs=0.22, cost=100, sfx="special", speed=1350)
    ult.update(ULT_GEOM[kind])
    mv["ult"] = ult
    for k, v in ch.get("move_mods", {}).items():
        mv[k].update(v)
    return mv


# --- RPG -------------------------------------------------------------------
def xp_for_level(lv):
    return 40 * (lv - 1) * lv


def level_from_xp(xp):
    lv = 1
    while xp >= xp_for_level(lv + 1):
        lv += 1
    return lv


class Profile:
    PATH = os.path.join(os.path.expanduser("~"), ".clash_of_legends.json")

    def __init__(self):
        self.xp = {}
        self.cleared = 0
        self.endings = []
        self.outfits = {}
        self.farm = {}
        try:
            with open(self.PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            self.xp = {k: int(v) for k, v in d.get("xp", {}).items()}
            self.cleared = int(d.get("cleared", 0))
            self.endings = [str(k) for k in d.get("endings", [])]
            self.outfits = {str(k): int(v) for k, v in d.get("outfits", {}).items()}
            self.farm = d.get("farm", {}) if isinstance(d.get("farm", {}), dict) else {}
        except Exception:
            pass

    def save(self):
        try:
            with open(self.PATH, "w", encoding="utf-8") as fh:
                json.dump({"xp": self.xp, "cleared": self.cleared, "endings": self.endings,
                           "outfits": self.outfits, "farm": self.farm}, fh)
        except Exception:
            pass

    def level(self, name):
        return level_from_xp(self.xp.get(name, 0))

    def get_outfit(self, name):
        idx = self.outfits.get(name, 0)
        return idx if 0 <= idx < len(OUTFIT_LEVELS) and self.level(name) >= OUTFIT_LEVELS[idx] else 0

    def set_outfit(self, name, idx):
        self.outfits[name] = int(idx)
        self.save()

    def unlock_ending(self, key):
        if key not in self.endings:
            self.endings.append(key)
            self.save()

    def add_xp(self, name, amount):
        old = self.level(name)
        self.xp[name] = self.xp.get(name, 0) + amount
        self.save()
        return old, self.level(name)



# --- Historia ---------------------------------------------------------------
# {H} = heroi escolhido | {E} = adversario | {QUOTE} = fala de entrada do adversario
PROLOGUE = [
    ("N", "Em Ardhen, tudo vive do Eter: a luz que pinga do Sol de Vidro, uma estrela rachada no ceu."),
    ("N", "Mas o Sol esta secando. E o Conclave, la do alto, sempre teve uma resposta pronta: a Colheita."),
    ("N", "A cada seculo, uma Terra inteira e entregue ao Sol. Ninguem sabe o que acontece com ela. Ninguem pergunta."),
    ("N", "Esta e a historia de {H}, que resolveu perguntar. (E, de quebra, levar umas pancadas pelo caminho.)"),
]

STORY = [
    dict(title="ATO 1 - O POUSO DAS BRASAS", sub="Uma noite vermelha demais", theme=0,
         pre=[("N", "Pouso das Brasas: um vilarejo tao pequeno que o galo tem nome, sobrenome e fama de fofoqueiro."),
              ("N", "Naquela noite, porem, havia um selo do Conclave brilhando sobre o vulcao."),
              ("E", "{QUOTE}"),
              ("H", "{E}? Eu estava dormindo! Voce nao pode chegar assim e..."),
              ("E", "O selo diz que o Eter daqui acabou. Vim conferir se ainda da pra lutar, ou se ja posso levar o que sobrou."),
              ("H", "Conferir? Nem bateu na porta! ...Ta bom. Vamos conferir do meu jeito.")],
         post=[("E", "Hm. Voce bate forte, pra quem estava meio dormindo."),
               ("H", "Valeu. Vou colocar isso no curriculo."),
               ("E", "O Exame das Chaves comeca em tres dias. Se quer respostas sobre o selo, va ate la."),
               ("N", "Um selo dourado rachou no ceu. Alguem, la em cima, acabava de anotar o nome de {H}.")]),
    dict(title="ATO 2 - O EXAME DAS CHAVES", sub="Mata Cristalina", theme=2,
         pre=[("N", "Mil candidatos entraram na Mata Cristalina. So passam os que voltarem com uma Chave. Metade ja desistiu... por causa dos mosquitos."),
              ("H", "Entao esse e o Exame. Eu esperava mais dramaticidade."),
              ("E", "{QUOTE}"),
              ("E", "A ultima prova e simples, {H}: derrote o examinador. Eu."),
              ("H", "So isso? Nao tem pegadinha?"),
              ("E", "Sempre tem. Mas voce so descobre apanhando.")],
         post=[("E", "Passou. E ainda despenteou meu cabelo, o que e imperdoavel."),
               ("H", "Antes, na estrada, ouvi falarem da Colheita. Voce sabe de algo?"),
               ("E", "Sei que quem pergunta demais costuma desaparecer. Siga para Lumen. E cuidado com os sorrisos de la.")]),
    dict(title="ATO 3 - A CIDADE-VIDRO", sub="Lumen, onde cada janela e um tribunal", theme=1,
         pre=[("N", "Lumen: a cidade onde cada janela e um tribunal e cada sorriso, um contrato."),
              ("H", "Preciso de provas. Registros, cartas, qualquer coisa que mostre o que a Colheita faz de verdade."),
              ("E", "{QUOTE}"),
              ("E", "Provas? Aqui dentro tudo e questao de quem fala mais alto. E de quem bate mais forte quando a conversa acaba."),
              ("H", "Entao vamos encerrar a conversa.")],
         post=[("E", "Voce venceu... mas os Magistrados ja sabem que anda procurando arquivos."),
               ("H", "Otimo. Quanto mais olhos me vigiam, menos eles escondem."),
               ("N", "No bolso do derrotado, um mapa: o caminho de uma camara esquecida sob o vulcao, guardada por quem ainda lembrava.")]),
    dict(title="ATO 4 - A MEMORIA DO AUTOMATO", sub="Sob o vulcao", theme=3,
         pre=[("N", "Sob o vulcao, uma camara de bronze. Um nome gravado cem vezes: a primeira Colheita."),
              ("H", "Entao foi aqui. Aqui comecou tudo."),
              ("E", "{QUOTE}"),
              ("E", "Eu estava la. Eu vi. E agora me pedem para esquecer. Nao vou deixar voce levar isso adiante... mesmo que uma parte de mim queira."),
              ("H", "Voce esta tremendo. Voce quer que eu ganhe, nao quer?"),
              ("E", "...Prove que merece lembrar.")],
         post=[("E", "A Colheita nao leva so terras. Leva quem ficou. E o Eter... e feito deles."),
               ("H", "Entao o Sol de Vidro nao e uma luz. E um cemiterio."),
               ("N", "Era isso que o Conclave escondia. E so um nome sabia o resto: Malakar, no Abismo do Vazio.")]),
    dict(title="ATO 5 - O ABISMO DO VAZIO", sub="Onde o ceu perdeu todas as cores", theme=4,
         pre=[("N", "Ilhas flutuando num ceu sem cor. No centro, um trono vazio... e uma figura sentada ao lado dele."),
              ("E", "{QUOTE}"),
              ("H", "Voce e o vilao da historia, certo? Pelo menos e o que dizem em Lumen."),
              ("E", "Sou o que sobrou da Colheita do Abismo. Vi minha terra virar luz. Agora vou apagar a fonte."),
              ("H", "Se apagar o Sol, o Eter acaba. Todo mundo sofre!"),
              ("E", "E quem sofreu por eles? Responda com os punhos. E a unica lingua que o Conclave aprendeu.")],
         post=[("E", "..."),
               ("H", "...")]),
]

ENDINGS = {
    "ciclo": dict(
        title="FINAL - O CICLO QUEBRADO",
        hint="Defesa firme e lutas limpas: voce escolheu proteger.",
        lines=[("N", "{H} baixou a guarda justamente quando Malakar esperava o golpe final."),
               ("H", "Nao vim vingar ninguem. Vim impedir que o proximo passe por isso."),
               ("E", "...Voce acredita mesmo que da pra recomecar?"),
               ("H", "Nao sei. Mas prefiro tentar a repetir."),
               ("N", "Juntos, os dois fundiram o que restava do Eter e acenderam um novo Sol, que nao pedia sacrificios."),
               ("N", "O Conclave foi desfeito. O Pouso das Brasas virou ponto turistico. O galo, claro, deu entrevista."),
               ("N", "FIM  -  O Ciclo Quebrado")]),
    "conclave": dict(
        title="FINAL - O NOVO CONCLAVE",
        hint="Vitoria pela forca bruta: o ciclo encontrou um novo dono.",
        lines=[("N", "{H} venceu como sempre venceu: com forca. Malakar caiu. O Abismo silenciou."),
               ("H", "Acabou. Ninguem mais vai tentar apagar o Sol."),
               ("N", "Mas o Eter continuava secando. E alguem precisava decidir quem pagaria a conta."),
               ("N", "Sem perceber, {H} sentou no trono vazio. Os Magistrados se ajoelharam. A Colheita ia continuar, so que com outro nome na assinatura."),
               ("N", "FIM  -  O Novo Conclave (o ciclo continua)")]),
    "sacrificio": dict(
        title="FINAL - O ULTIMO AMANHECER",
        hint="Tantas quedas, tanta teimosia: voce pagou com tudo.",
        lines=[("N", "Foram tantas quedas, tantas noites sem dormir. {H} chegou ao Abismo com nada alem de vontade."),
               ("E", "Voce ja perdeu demais. Por que continua de pe?"),
               ("H", "Porque alguem tem que ser a luz quando o Sol apagar."),
               ("N", "{H} deu o golpe final, e o Eter da vitoria nao coube mais no corpo. Virou luz."),
               ("N", "No ceu de Ardhen nasceu uma nova estrela. Ninguem soube quem a acendeu, mas todo dia, ao amanhecer, alguem sorri sem saber por que."),
               ("N", "FIM  -  O Ultimo Amanhecer")]),
}


def decide_ending(saga):
    """O final depende de COMO voce jogou (nao de uma escolha em menu)."""
    defesa = saga["blocks"] + saga["hits_taken"]
    ratio = saga["blocks"] / defesa if defesa else 0.0
    if saga["defeats"] >= 3:
        return "sacrificio"
    if ratio >= 0.28 or saga["perfects"] >= 3:
        return "ciclo"
    return "conclave"


# ----------------------------------------------------------------------------
# Poses e desenho procedural dos lutadores
# ----------------------------------------------------------------------------
def P(**over):
    base = dict(fh=(34, -122), bh=(14, -116), ff=(24, 0), bf=(-20, 0), lean=0.0, hip=-78.0)
    base.update(over)
    return base


GUARD = P()
JUMP = P(ff=(28, -36), bf=(-4, -22), fh=(40, -128), bh=(8, -132), hip=-86)
ATK = {
    "punch": (P(fh=(0, -120), lean=-4, ff=(28, 0)), P(fh=(116, -127), bh=(8, -114), lean=9, ff=(32, 0))),
    "kick": (P(ff=(32, -54), lean=-6, hip=-80, bf=(-24, 0)),
             P(ff=(122, -84), lean=-12, fh=(18, -132), bh=(-6, -120), bf=(-22, 0))),
    "proj": (P(fh=(-6, -110), bh=(-14, -108), lean=-8),
             P(fh=(88, -118), bh=(72, -112), lean=8, ff=(32, 0))),
    "dash": (P(lean=-14, ff=(10, 0), bf=(-40, 0), hip=-66, fh=(-10, -100)),
             P(lean=26, hip=-68, ff=(52, -6), bf=(-48, -10), fh=(104, -96), bh=(-22, -90))),
    "slam": (P(fh=(10, -198), bh=(0, -192), lean=-6),
             P(fh=(78, -24), bh=(58, -30), lean=20, hip=-60, ff=(44, 0), bf=(-26, 0))),
}


def pose_lerp(a, b, t):
    r = {}
    for k, va in a.items():
        vb = b[k]
        r[k] = lerp_pt(va, vb, t) if isinstance(va, tuple) else lerp(va, vb, t)
    return r


def get_pose(f):
    st, t = f.state, f.anim
    bob = math.sin(t * 3.4)
    if st == "charge":
        tremor = math.sin(t * 40) * 1.2
        return P(fh=(20 + tremor, -94), bh=(-8 - tremor, -94), hip=-70, ff=(30, 0), bf=(-28, 0), lean=3 + tremor * 0.5)
    if st == "attack":
        mv = f.moves[f.move]
        key = f.move if f.move in ("punch", "kick") else mv["type"]
        if key == "ult":
            key = {"clones": "dash", "flurry": "dash", "quake": "slam"}.get(mv["kind"], "proj")
        w, e = ATK[key]
        a = f.t
        if a < mv["start"]:
            p = pose_lerp(GUARD, w, ease_out(a / mv["start"]))
        elif a < mv["start"] + mv["active"]:
            p = pose_lerp(w, e, ease_out((a - mv["start"]) / mv["active"]))
        else:
            p = pose_lerp(e, GUARD, ease_io((a - mv["start"] - mv["active"]) / mv["rec"]))
        if not f.on_ground and key != "kick":
            p["ff"], p["bf"] = JUMP["ff"], JUMP["bf"]
            p["hip"] = -86
        return p
    if st == "jump":
        return dict(JUMP)
    if st == "walk":
        ph = f.walk_phase
        return P(ff=(8 + 30 * math.sin(ph), -14 * max(0, math.cos(ph))),
                 bf=(8 - 30 * math.sin(ph), -14 * max(0, -math.cos(ph))),
                 fh=(32, -120 + bob * 2), bh=(14, -114 + bob * 2), hip=-76 + abs(math.sin(ph)) * 3)
    if st == "block":
        return P(fh=(36, -132), bh=(30, -112), lean=-3, hip=-70, ff=(32, 0), bf=(-30, 0))
    if st in ("hit", "ko"):
        return P(lean=-15, fh=(-8, -96), bh=(-22, -102), hip=-76, ff=(18, 0), bf=(-26, 0))
    if st == "win":
        return P(fh=(26, -196 + bob * 4), bh=(-10, -190 - bob * 4), hip=-78 + bob)
    return P(hip=-78 + bob * 1.6, fh=(34, -122 + bob * 2.2), bh=(14, -116 + bob * 2.2),
             lean=bob * 0.8)


def ik2(a, b, l1, l2, bend):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    d = max(1e-3, min(d, l1 + l2 - 0.5))
    ang = math.atan2(dy, dx)
    ca = clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1)
    A = math.acos(ca) * bend
    knee = (a[0] + math.cos(ang + A) * l1, a[1] + math.sin(ang + A) * l1)
    end = (a[0] + math.cos(ang) * d, a[1] + math.sin(ang) * d)
    return knee, end


def ip(p):
    return (int(p[0]), int(p[1]))


# --- Arte propria (pecas PNG) --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARTS_DIR = os.path.join(BASE_DIR, "personagens")
PART_NAMES = ("cabeca", "tronco", "braco", "antebraco", "coxa", "canela", "pe", "capa", "retrato")
_parts_cache = {}


def _remove_green(img):
    """Torna transparente o fundo verde (#00FF00 aproximado), para quem nao exporta PNG transparente."""
    try:
        m = pygame.mask.from_threshold(img, (0, 255, 0, 255), (110, 90, 110, 255))
        if m.count() == 0:
            return img
        m.invert()
        alpha = m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))
        out = img.copy()
        out.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return out
    except Exception:
        return img


def _load_folder(folder, into):
    if not os.path.isdir(folder):
        return
    for pn in PART_NAMES:
        fp = os.path.join(folder, pn + ".png")
        if os.path.isfile(fp):
            try:
                into[pn] = _remove_green(pygame.image.load(fp).convert_alpha())
            except Exception as exc:
                print("Aviso: nao consegui carregar %s (%s)" % (fp, exc))


def load_parts(name, outfit_idx=0):
    """personagens/<nome>/*.png  +  personagens/<nome>/uniforme<N>/*.png (substitui pecas)."""
    key = (name.lower(), outfit_idx)
    if key not in _parts_cache:
        parts = {}
        if pygame.display.get_surface() is not None:
            base = os.path.join(PARTS_DIR, name.lower())
            _load_folder(base, parts)
            _load_folder(os.path.join(base, "uniforme%d" % (outfit_idx + 1)), parts)
        _parts_cache[key] = parts
    return _parts_cache[key]


# --- Personagens quadro a quadro: personagens/<nome>/quadros/<animacao>/*.png --------
FRAME_ANIMS = ("parado", "andar", "pular", "cair", "soco", "chute", "soco_ar", "chute_ar",
               "especial", "defesa", "golpe", "nocaute", "vitoria", "carregar")
FRAME_FALLBACK = {"andar": "parado", "pular": "parado", "cair": "pular", "soco": "parado", "chute": "soco",
                  "soco_ar": "soco", "chute_ar": "chute", "especial": "chute", "defesa": "parado",
                  "golpe": "cair", "nocaute": "golpe", "vitoria": "parado", "carregar": "vitoria"}
_frames_cache = {}


def _feet_anchor(im):
    """Ponto dos pes (centro da faixa mais baixa da figura): fica parado no chao em todos os quadros."""
    br = im.get_bounding_rect()
    if br.h == 0:
        return im.get_width() / 2, im.get_height()
    band = max(4, int(br.h * 0.12))
    strip = im.subsurface(pygame.Rect(br.left, br.bottom - band, br.w, band)).get_bounding_rect()
    return br.left + strip.centerx, br.bottom


def load_frames(name, scale=1.0):
    key = (name.lower(), round(scale, 3))
    if key in _frames_cache:
        return _frames_cache[key]
    folder = os.path.join(PARTS_DIR, name.lower(), "quadros")
    raw = {}
    if pygame.display.get_surface() is not None and os.path.isdir(folder):
        for an in FRAME_ANIMS:
            d = os.path.join(folder, an)
            files = sorted(glob.glob(os.path.join(d, "*.png"))) if os.path.isdir(d) else (
                [d + ".png"] if os.path.isfile(d + ".png") else [])
            ims = []
            for fp in files:
                try:
                    ims.append(_remove_green(pygame.image.load(fp).convert_alpha()))
                except Exception as exc:
                    print("Aviso: nao consegui carregar %s (%s)" % (fp, exc))
            if ims:
                raw[an] = ims
    if "parado" not in raw:
        _frames_cache[key] = {}
        return {}
    zoom = 160 * scale / max(1, raw["parado"][0].get_bounding_rect().h)
    out = {}
    for an, ims in raw.items():
        out[an] = []
        for im in ims:
            w, h = im.get_size()
            im2 = pygame.transform.smoothscale(im, (max(1, int(w * zoom)), max(1, int(h * zoom))))
            out[an].append((im2,) + _feet_anchor(im2))
    for an in FRAME_ANIMS:
        k = an
        while k not in out:
            k = FRAME_FALLBACK.get(k, "parado")
        out[an] = out[k]
    _frames_cache[key] = out
    return out


def pick_frame(f):
    fr, st = f.frames, f.state

    def loop(lst, fps):
        return lst[int(f.anim * fps) % len(lst)]

    if st == "attack" and f.move:
        mv = f.moves[f.move]
        key = {"punch": "soco", "kick": "chute"}.get(f.move, "especial")
        if not f.on_ground and f.move in ("punch", "kick"):
            key += "_ar"
        lst = fr[key]
        a = mv["start"] + mv["active"]
        dashing = mv["type"] == "dash" or mv.get("kind") in ("clones", "flurry")
        if key == "especial" and dashing and mv["start"] <= f.t < a:
            return loop(lst, 18)
        if f.t <= a:
            idx = int(f.t / a * (len(lst) - 1) + 0.5)
        else:
            idx = int((1 - (f.t - a) / mv["rec"]) * (len(lst) - 1) + 0.5)
        return lst[int(clamp(idx, 0, len(lst) - 1))]
    if st == "jump":
        return fr["pular"][0] if f.vy < 0 else fr["cair"][0]
    if st == "walk":
        lst = fr["andar"]
        return lst[int(f.walk_phase / math.tau * len(lst)) % len(lst)]
    if st == "block":
        return fr["defesa"][0]
    if st == "charge":
        return loop(fr["carregar"], 10)
    if st == "hit":
        return fr["golpe"][0]
    if st == "ko":
        return fr["nocaute"][0]
    if st == "win":
        return loop(fr["vitoria"], 8)
    return loop(fr["parado"], 9)


def frame_image(f, face=None, scale=1.0):
    """Quadro atual ja virado, tingido (uniforme) e com flash de golpe. Devolve (imagem, ax, ay)."""
    img, ax, ay = pick_frame(f)
    if scale != 1.0:
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
        ax, ay = ax * scale, ay * scale
    face = f.face if face is None else face
    if face < 0:
        img = pygame.transform.flip(img, True, False)
        ax = img.get_width() - ax
    tint = f.ch.get("tint")
    if tint or f.flash > 0:
        img = img.copy()
        if tint:
            img.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
        if f.flash > 0:
            img.fill((150, 150, 150) if f.flash_col == WHITE else (170, 40, 40), special_flags=pygame.BLEND_RGB_ADD)
    return img, ax, ay


def put_seg(spr, img, a, b, extra=1.12, dark=0):
    """Desenha uma peca (desenhada em pe, junta de cima no topo) ao longo do osso a->b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = max(1.0, math.hypot(dx, dy))
    im = pygame.transform.rotozoom(img, math.degrees(math.atan2(dx, dy)), length * extra / img.get_height())
    if dark:
        im.fill((dark, dark, dark), special_flags=pygame.BLEND_RGB_SUB)
    spr.blit(im, im.get_rect(center=(int((a[0] + b[0]) / 2), int((a[1] + b[1]) / 2))))


# --- Desenho procedural (corpo com volume, sombra e brilho) ----------------------
def limb2(spr, a, b, w0, w1, col):
    """Membro afinado com contorno, lado iluminado e lado em sombra."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L

    def quad(e, k0=1.0, k1=1.0):
        h0, h1 = w0 / 2 * k0 + e, w1 / 2 * k1 + e
        return [(a[0] + nx * h0, a[1] + ny * h0), (b[0] + nx * h1, b[1] + ny * h1),
                (b[0] - nx * h1, b[1] - ny * h1), (a[0] - nx * h0, a[1] - ny * h0)]

    pygame.draw.polygon(spr, OUT, quad(2.5))
    pygame.draw.circle(spr, OUT, ip(a), int(w0 / 2 + 2.5))
    pygame.draw.circle(spr, OUT, ip(b), int(w1 / 2 + 2.5))
    pygame.draw.polygon(spr, col, quad(0))
    pygame.draw.circle(spr, col, ip(a), max(1, int(w0 / 2)))
    pygame.draw.circle(spr, col, ip(b), max(1, int(w1 / 2)))
    sg = 1 if (-ny + 0.6 * nx) >= 0 else -1          # lado voltado para a luz (cima/frente)
    for off, wk, c in ((-0.30, 0.30, shade(col, 0.70)), (0.26, 0.22, mix(col, WHITE, 0.30))):
        o0, o1 = w0 * off * sg, w1 * off * sg
        pygame.draw.line(spr, c, (a[0] + nx * o0, a[1] + ny * o0), (b[0] + nx * o1, b[1] + ny * o1),
                         max(1, int(min(w0, w1) * wk)))


def fist(spr, c, col, s, back=False):
    col = shade(col, 0.68) if back else col
    r = 7.5 * s
    pygame.draw.circle(spr, OUT, ip(c), int(r + 2.5))
    pygame.draw.circle(spr, col, ip(c), int(r))
    pygame.draw.circle(spr, mix(col, WHITE, 0.45), (int(c[0] + r * 0.2), int(c[1] - r * 0.35)), max(1, int(r * 0.35)))
    pygame.draw.line(spr, shade(col, 0.65), (c[0] + r * 0.1, c[1] - r * 0.6), (c[0] + r * 0.1, c[1] + r * 0.6), 2)


def boot(spr, ank, col, s, back=False):
    col = shade(col, 0.62) if back else col
    pts = [(ank[0] - 6 * s, ank[1] - 10 * s), (ank[0] + 6 * s, ank[1] - 10 * s), (ank[0] + 10 * s, ank[1] - 4 * s),
           (ank[0] + 18 * s, ank[1] - 1 * s), (ank[0] + 18 * s, ank[1] + 3 * s), (ank[0] - 7 * s, ank[1] + 3 * s)]
    pygame.draw.polygon(spr, col, pts)
    pygame.draw.polygon(spr, mix(col, WHITE, 0.3), [pts[0], pts[1], (ank[0] + 3 * s, ank[1] - 3 * s), (ank[0] - 5 * s, ank[1] - 4 * s)])
    pygame.draw.polygon(spr, OUT, pts, 3)
    pygame.draw.line(spr, OUT, (ank[0] - 6 * s, ank[1] + 1 * s), (ank[0] + 17 * s, ank[1] + 1 * s), 2)


def pauldron(spr, c, col, s, back=False):
    col = shade(col, 0.62) if back else col
    r = pygame.Rect(0, 0, int(24 * s), int(15 * s))
    r.center = (int(c[0]), int(c[1] - 2 * s))
    pygame.draw.ellipse(spr, OUT, r.inflate(5, 5))
    pygame.draw.ellipse(spr, col, r)
    pygame.draw.ellipse(spr, mix(col, WHITE, 0.5), r.inflate(-r.w // 2, -r.h // 2).move(-2, -2))


def draw_torso(spr, f, sh, hip, s, mw):
    ch = f.ch
    main, acc, skin, style = ch["main"], ch["accent"], ch["skin"], ch["style"]
    sw, ww = 19 * s * mw, 13 * s * mw
    tor = [(sh[0] - sw, sh[1] - 1), (sh[0] + sw, sh[1] + 1), (hip[0] + ww, hip[1] + 4 * s), (hip[0] - ww, hip[1] + 4 * s)]
    pygame.draw.polygon(spr, main, tor)
    mid_t, mid_b = ((tor[0][0] + tor[1][0]) / 2 + 3 * s, tor[0][1]), ((tor[2][0] + tor[3][0]) / 2 + 2 * s, tor[3][1])
    pygame.draw.polygon(spr, shade(main, 0.78), [tor[0], mid_t, mid_b, tor[3]])           # costas em sombra
    pygame.draw.polygon(spr, mix(main, WHITE, 0.18), [mid_t, tor[1], (tor[1][0] - 3 * s, tor[1][1] + 18 * s),
                                                      (mid_t[0], mid_t[1] + 22 * s)])        # peito iluminado
    bx, by = (hip[0] + sh[0]) / 2, (hip[1] + sh[1]) / 2
    if style == "bulky":
        chest = [(sh[0] - 11 * s, sh[1] + 2), (sh[0] + 13 * s, sh[1] + 3), (bx + 7 * s, by + 10 * s), (bx - 5 * s, by + 10 * s)]
        pygame.draw.polygon(spr, skin, chest)
        pygame.draw.polygon(spr, mix(skin, WHITE, 0.2), [chest[1], (sh[0] + 3 * s, sh[1] + 3), (bx + 2 * s, by + 4 * s)])
        for k in range(3):
            yy = sh[1] + 16 * s + k * 7 * s
            pygame.draw.line(spr, shade(skin, 0.7), (bx - 2 * s, yy), (bx + 6 * s, yy), 2)
        pygame.draw.polygon(spr, OUT, chest, 2)
    elif style == "visor":
        plate = pygame.Rect(0, 0, int(26 * s), int(28 * s))
        plate.center = (int(bx + 4 * s), int(by - 6 * s))
        pygame.draw.rect(spr, shade(main, 0.6), plate, border_radius=5)
        pygame.draw.rect(spr, OUT, plate, 2, border_radius=5)
        pygame.draw.circle(spr, acc, plate.center, int(6 * s))
        pygame.draw.circle(spr, WHITE, plate.center, int(2.5 * s))
    elif style == "hood":
        pygame.draw.line(spr, shade(main, 0.55), (sh[0] - sw * 0.6, sh[1] + 2), (hip[0] + ww * 0.8, hip[1] - 2), int(5 * s))
        pygame.draw.line(spr, acc, (sh[0] + sw * 0.7, sh[1] + 2), (hip[0] - ww * 0.6, hip[1] - 2), int(3 * s))
    elif style == "long":
        pygame.draw.line(spr, (96, 62, 40), (sh[0] - sw * 0.7, sh[1] + 1), (hip[0] + ww * 0.9, hip[1] - 1), int(4 * s))
        pygame.draw.circle(spr, OUT, ip((bx + 5 * s, by - 8 * s)), int(6 * s))
        pygame.draw.circle(spr, acc, ip((bx + 5 * s, by - 8 * s)), int(4 * s))
    elif style == "horns":
        for k in range(3):
            yy = sh[1] + 9 * s + k * 9 * s
            pygame.draw.line(spr, shade(main, 1.5), (sh[0] - sw * 0.7, yy), (sh[0] + sw * 0.8, yy + 1), 2)
        pygame.draw.polygon(spr, acc, [(bx + 4 * s, by - 14 * s), (bx + 10 * s, by - 7 * s), (bx + 4 * s, by), (bx - 2 * s, by - 7 * s)])
    else:   # kimono / gi (spiky e padrao)
        pygame.draw.line(spr, mix(acc, WHITE, 0.4), (sh[0] - sw * 0.35, sh[1] + 1), (bx + 3 * s, by + 8 * s), int(4 * s))
        pygame.draw.line(spr, mix(acc, WHITE, 0.4), (sh[0] + sw * 0.7, sh[1] + 1), (bx + 3 * s, by + 8 * s), int(4 * s))
        c = (int(bx + 7 * s), int(by - 7 * s))
        if style == "spiky":
            pygame.draw.circle(spr, OUT, c, int(6.5 * s))
            pygame.draw.circle(spr, acc, c, int(4.5 * s))
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(spr, acc, (c[0] + math.cos(a) * 6 * s, c[1] + math.sin(a) * 6 * s),
                                 (c[0] + math.cos(a) * 9 * s, c[1] + math.sin(a) * 9 * s), 2)
        else:
            dm = [(c[0], c[1] - 7 * s), (c[0] + 5 * s, c[1]), (c[0], c[1] + 7 * s), (c[0] - 5 * s, c[1])]
            pygame.draw.polygon(spr, OUT, dm)
            pygame.draw.polygon(spr, acc, [(x * 0.8 + c[0] * 0.2, y * 0.8 + c[1] * 0.2) for x, y in dm])
    pygame.draw.polygon(spr, OUT, tor, 3)
    # faixa / cinto com no e pontas balancando
    sway = math.sin(f.anim * 6) * 3 + abs(f.vx) * 0.01
    pygame.draw.line(spr, OUT, (hip[0] - 14 * s * mw, hip[1] + 1), (hip[0] + 14 * s * mw, hip[1] + 1), int(9 * s))
    pygame.draw.line(spr, acc, (hip[0] - 13 * s * mw, hip[1] + 1), (hip[0] + 13 * s * mw, hip[1] + 1), int(6 * s))
    knot = (hip[0] - 9 * s * mw, hip[1] + 2)
    for k in (0, 1):
        tip = (knot[0] - 9 * s - sway * (1.2 + k * 0.5), knot[1] + (10 + k * 6) * s)
        pygame.draw.line(spr, OUT, knot, tip, int(6 * s))
        pygame.draw.line(spr, acc, knot, tip, int(3.5 * s))
    pygame.draw.circle(spr, OUT, ip(knot), int(5 * s))
    pygame.draw.circle(spr, mix(acc, WHITE, 0.3), ip(knot), int(3.5 * s))


SPR_W, SPR_H, OX, OY = 340, 320, 170, 280


def draw_fighter_sprite(f):
    """Desenha o lutador virado para a direita num sprite temporario.
    Usa as pecas PNG de personagens/<nome>/ quando existirem; o resto e desenhado por codigo."""
    s = f.scale
    ch = f.ch
    spr = pygame.Surface((SPR_W, SPR_H), pygame.SRCALPHA)
    p = get_pose(f)
    main, acc, skin = ch["main"], ch["accent"], ch["skin"]
    dark = shade(main, 0.62)
    t = f.anim
    parts = getattr(f, "parts", {}) or {}
    extras = ch.get("extras", ())
    mw = 1.22 if ch["style"] == "bulky" or ch.get("muscle") else 1.0

    def X(pt):
        return (OX + pt[0] * s, OY + pt[1] * s)

    def seg(name, a, b, w0, w1, col, back=False):
        if name in parts:
            put_seg(spr, parts[name], a, b, 1.12, 55 if back else 0)
        else:
            limb2(spr, a, b, w0 * mw, w1 * mw, col)

    def foot(ank, back=False):
        if "pe" in parts:
            img = parts["pe"]
            im = pygame.transform.rotozoom(img, 0, 32 * s / img.get_width())
            if back:
                im.fill((55, 55, 55), special_flags=pygame.BLEND_RGB_SUB)
            spr.blit(im, im.get_rect(center=(int(ank[0] + im.get_width() * 0.28), int(ank[1] - im.get_height() * 0.15))))
        else:
            boot(spr, ank, acc, s, back)

    hip = X((0, p["hip"]))
    lean = p["lean"]
    sh = X((lean, p["hip"] - 52))
    hipb, hipf = (hip[0] - 4 * s, hip[1]), (hip[0] + 6 * s, hip[1])
    kb, fb = ik2(hipb, X(p["bf"]), 40 * s, 42 * s, -1)
    kf, ff = ik2(hipf, X(p["ff"]), 40 * s, 42 * s, -1)
    shb, shf = (sh[0] - 7 * s, sh[1] + 4 * s), (sh[0] + 7 * s, sh[1] + 4 * s)
    eb, hb = ik2(shb, X(p["bh"]), 29 * s, 29 * s, 1)
    ef, hf = ik2(shf, X(p["fh"]), 29 * s, 29 * s, 1)
    hc = (sh[0] + 3 * s + lean * 0.3, sh[1] - 21 * s)
    r = 14 * s

    # ---- capa / cachecol / aljava (atras de tudo) --------------------------------
    sway = math.sin(t * 5) * 4 + abs(f.vx) * 0.012
    if "capa" in parts:
        img = parts["capa"]
        im = pygame.transform.rotozoom(img, -sway * 1.5, 66 * s / img.get_height())
        spr.blit(im, im.get_rect(topright=(int(sh[0] + 4 * s), int(sh[1] - 3 * s))))
    elif ch.get("cape"):
        ln = (48 if ch["style"] != "hood" else 60) * s
        pts = [(sh[0] - 4 * s, sh[1] + 2 * s), (sh[0] - 4 * s, sh[1] + 24 * s),
               (sh[0] - ln * 0.7 - sway, sh[1] + 44 * s + sway), (sh[0] - ln - sway * 1.6, sh[1] + 22 * s),
               (sh[0] - ln * 0.7 - sway, sh[1] + 2 * s)]
        pygame.draw.polygon(spr, ch["cape"], pts)
        pygame.draw.polygon(spr, shade(ch["cape"], 0.7), [pts[0], pts[1], pts[2], ((pts[2][0] + pts[1][0]) / 2, pts[1][1] - 4 * s)])
        pygame.draw.line(spr, mix(ch["cape"], WHITE, 0.3), pts[4], pts[3], 2)
        pygame.draw.polygon(spr, OUT, pts, 3)
    if ch["style"] == "long" and "tronco" not in parts:
        q0, q1 = (sh[0] - 12 * s, sh[1] - 8 * s), (sh[0] - 4 * s, sh[1] + 30 * s)
        limb2(spr, q0, q1, 11 * s, 9 * s, (110, 70, 44))
        for k in range(3):
            pygame.draw.line(spr, acc, (q0[0] - 3 * s + k * 3 * s, q0[1]), (q0[0] - 5 * s + k * 3 * s, q0[1] - 10 * s), 2)

    # ---- membros de tras ---------------------------------------------------------
    seg("coxa", hipb, kb, 17 * s, 13 * s, shade(main, 0.5), True)
    seg("canela", kb, fb, 13 * s, 10 * s, shade(main, 0.55), True)
    foot(fb, True)
    if "ombreiras" in extras:
        pauldron(spr, shb, acc, s, True)
    seg("braco", shb, eb, 13 * s, 11 * s, shade(main, 0.55), True)
    seg("antebraco", eb, hb, 11 * s, 10 * s, shade(skin, 0.7), True)
    if "antebraco" not in parts:
        fist(spr, hb, acc, s, True)

    # ---- tronco --------------------------------------------------------------------
    if "tronco" in parts:
        put_seg(spr, parts["tronco"], (sh[0], sh[1] - 6 * s), (hip[0], hip[1] + 6 * s), 1.08)
    else:
        draw_torso(spr, f, sh, hip, s, mw)

    # ---- perna da frente -------------------------------------------------------------
    seg("coxa", hipf, kf, 18 * s, 14 * s, dark)
    seg("canela", kf, ff, 14 * s, 11 * s, main)
    foot(ff)

    # ---- cabeca ------------------------------------------------------------------------
    if "cabeca" in parts:
        img = parts["cabeca"]
        im = pygame.transform.rotozoom(img, -lean * 0.6, r * 2.9 / img.get_height())
        spr.blit(im, im.get_rect(center=(int(hc[0]), int(hc[1] - r * 0.1))))
    else:
        limb2(spr, (sh[0], sh[1] + 2), (hc[0] - 1, hc[1] + r * 0.6), 10 * s * mw, 9 * s * mw, shade(skin, 0.85))
        draw_head(spr, f, hc, r, t, p)

    # ---- braco da frente ------------------------------------------------------------------
    seg("braco", shf, ef, 14 * s, 12 * s, main)
    seg("antebraco", ef, hf, 12 * s, 11 * s, skin)
    if "antebraco" not in parts:
        limb2(spr, lerp_pt(ef, hf, 0.62), lerp_pt(ef, hf, 0.9), 13 * s * mw, 13 * s * mw, acc)   # munhequeira
        fist(spr, hf, acc, s)
    if ch.get("weapon"):
        draw_weapon(spr, ch["weapon"], ef, hf, s, acc)
    if "ombreiras" in extras:
        pauldron(spr, shf, acc, s)
    return spr


def draw_weapon(spr, kind, elbow, hand, s, acc):
    dx, dy = hand[0] - elbow[0], hand[1] - elbow[1]
    ang = math.atan2(dy, dx) - math.radians(75)          # lamina para cima e para frente
    ux, uy = math.cos(ang), math.sin(ang)
    nx, ny = -uy, ux
    if kind == "katana":
        ln, w = 74 * s, 4.5 * s
        base = (hand[0] + ux * 6 * s, hand[1] + uy * 6 * s)
        tip = (base[0] + ux * ln, base[1] + uy * ln)
        pygame.draw.line(spr, OUT, (hand[0] - ux * 12 * s, hand[1] - uy * 12 * s), base, int(7 * s))
        pygame.draw.line(spr, (60, 40, 70), (hand[0] - ux * 11 * s, hand[1] - uy * 11 * s), base, int(4 * s))
        poly = [(base[0] + nx * w, base[1] + ny * w), (tip[0] + nx * w * 0.3, tip[1] + ny * w * 0.3),
                (tip[0] + ux * 6 * s, tip[1] + uy * 6 * s), (base[0] - nx * w * 0.6, base[1] - ny * w * 0.6)]
        pygame.draw.polygon(spr, OUT, poly)
        pygame.draw.polygon(spr, (214, 220, 234), poly[:3] + [base])
        pygame.draw.line(spr, WHITE, base, tip, 1)
        pygame.draw.line(spr, acc, (base[0] - nx * 7 * s, base[1] - ny * 7 * s), (base[0] + nx * 7 * s, base[1] + ny * 7 * s), int(4 * s))
    else:   # espada de pedra
        ln, w = 82 * s, 10 * s
        base = (hand[0] + ux * 4 * s, hand[1] + uy * 4 * s)
        tip = (base[0] + ux * ln, base[1] + uy * ln)
        poly = [(base[0] + nx * w, base[1] + ny * w), (tip[0] + nx * w * 1.1, tip[1] + ny * w * 1.1),
                (tip[0] + ux * 10 * s, tip[1] + uy * 10 * s), (tip[0] - nx * w * 0.9, tip[1] - ny * w * 0.9),
                (base[0] - nx * w, base[1] - ny * w)]
        pygame.draw.polygon(spr, OUT, [(x + nx * 2.5, y + ny * 2.5) for x, y in poly])
        pygame.draw.polygon(spr, (150, 148, 158), poly)
        pygame.draw.polygon(spr, (182, 180, 190), [poly[0], poly[1], ((poly[1][0] + poly[3][0]) / 2, (poly[1][1] + poly[3][1]) / 2), base])
        pygame.draw.polygon(spr, OUT, poly, 3)
        for k in (0.3, 0.6):
            cx, cy = base[0] + ux * ln * k, base[1] + uy * ln * k
            pygame.draw.line(spr, (96, 94, 104), (cx - nx * w * 0.6, cy - ny * w * 0.6), (cx + nx * w * 0.2 + ux * 8, cy + ny * w * 0.2 + uy * 8), 2)
        pygame.draw.line(spr, acc, (base[0] - nx * 13 * s, base[1] - ny * 13 * s), (base[0] + nx * 13 * s, base[1] + ny * 13 * s), int(5 * s))


def draw_head(spr, f, c, r, t, p):
    ch = f.ch
    style = ch["style"]
    skin, hair, main, acc = ch["skin"], ch["hair"], ch["main"], ch["accent"]
    if getattr(f, "awake", 0) > 0:
        hair = ch.get("awake_hair", AWAKE_HAIR)
    cx, cy = c
    pygame.draw.circle(spr, OUT, ip(c), int(r + 2))
    if style in ("visor", "horns", "hood"):
        base = main if style != "hood" else shade(main, 0.8)
        pygame.draw.circle(spr, base, ip(c), int(r + 1))
    else:
        pygame.draw.circle(spr, skin, ip(c), int(r))
    sway = math.sin(t * 6) * 3

    def cap(rad, a0, a1, col):
        pts = [(cx, cy)]
        a = a0
        while a <= a1:
            pts.append((cx + math.cos(math.radians(a)) * rad, cy + math.sin(math.radians(a)) * rad))
            a += 12
        pygame.draw.polygon(spr, col, pts)

    if style == "spiky":
        for ang in (-178, -154, -128, -102, -76, -54):
            a1, a2 = math.radians(ang - 14), math.radians(ang + 14)
            tip_a = math.radians(ang - 14)
            b1 = (cx + math.cos(a1) * r * 0.9, cy + math.sin(a1) * r * 0.9)
            b2 = (cx + math.cos(a2) * r * 0.9, cy + math.sin(a2) * r * 0.9)
            tip = (cx + math.cos(tip_a) * r * 2.0, cy + math.sin(tip_a) * r * 2.0)
            pygame.draw.polygon(spr, OUT, [b1, tip, b2], 0)
            pygame.draw.polygon(spr, hair, [b1, (tip[0] + 1, tip[1] + 2), b2])
        cap(r * 1.02, -200, -35, hair)
        pygame.draw.line(spr, acc, (cx - r, cy - r * 0.35), (cx + r * 0.9, cy - r * 0.38), max(2, int(r * 0.25)))
    elif style == "long":
        pts = [(cx - r * 0.6, cy - r * 0.2), (cx - r * 1.6 - sway, cy + r * 0.8),
               (cx - r * 1.9 - sway * 1.5, cy + r * 2.2), (cx - r * 1.0, cy + r * 1.2), (cx - r * 0.2, cy + r * 0.3)]
        pygame.draw.polygon(spr, OUT, pts)
        pygame.draw.polygon(spr, hair, pts)
        cap(r * 1.04, -205, -28, hair)
        pygame.draw.polygon(spr, hair, [(cx + r * 0.2, cy - r * 0.8), (cx + r * 1.0, cy - r * 0.15),
                                        (cx + r * 0.1, cy - r * 0.35)])
    elif style == "visor":
        pygame.draw.line(spr, OUT, (cx - 2, cy - r), (cx - 6, cy - r * 1.7), 3)
        pygame.draw.circle(spr, acc, ip((cx - 6, cy - r * 1.7)), max(2, int(r * 0.2)))
        vis = pygame.Rect(0, 0, int(r * 1.35), int(r * 0.55))
        vis.center = (int(cx + r * 0.35), int(cy - r * 0.05))
        pygame.draw.rect(spr, OUT, vis.inflate(4, 4), border_radius=4)
        pygame.draw.rect(spr, acc, vis, border_radius=3)
        pygame.draw.rect(spr, mix(acc, WHITE, 0.6), vis.inflate(-4, -vis.h + 4).move(0, -vis.h // 4), border_radius=2)
    elif style == "hood":
        face = pygame.Rect(0, 0, int(r * 1.05), int(r * 0.75))
        face.center = (int(cx + r * 0.45), int(cy + r * 0.05))
        pygame.draw.rect(spr, skin, face, border_radius=4)
        pygame.draw.line(spr, acc, (face.left + 2, face.centery - 1), (face.right - 2, face.centery - 1), 2)
        tail = [(cx - r * 0.6, cy + r * 0.7), (cx - r * 2.0 - sway * 2, cy + r * 0.9 + sway),
                (cx - r * 2.5 - sway * 3, cy + r * 1.7), (cx - r * 1.1, cy + r * 1.3)]
        pygame.draw.polygon(spr, OUT, tail)
        pygame.draw.polygon(spr, ch["cape"], tail)
    elif style == "bulky":
        cap(r * 1.03, -200, -45, hair)
        pygame.draw.line(spr, OUT, (cx - r, cy - r * 0.3), (cx + r, cy - r * 0.34), int(r * 0.45))
        pygame.draw.line(spr, acc, (cx - r, cy - r * 0.3), (cx + r, cy - r * 0.34), int(r * 0.3))
        for k in (0, 1):
            pygame.draw.line(spr, acc, (cx - r, cy - r * 0.3), (cx - r * 1.9 - sway * (1 + k), cy - r * 0.2 + k * r * 0.5 + sway), 3)
    elif style == "short":
        cap(r * 1.05, -205, -20, hair)
        for k in range(3):
            bx = cx + r * (0.15 + k * 0.28)
            pygame.draw.polygon(spr, hair, [(bx - r * 0.3, cy - r * 0.75), (bx + r * 0.12, cy - r * 0.95),
                                            (bx - r * 0.02, cy - r * 0.35)])
    elif style == "wild":
        for i, ang in enumerate(range(-215, 0, 17)):
            ln = r * (1.55 + 0.45 * ((i * 37) % 5) / 4)
            a1, a2 = math.radians(ang - 11), math.radians(ang + 11)
            tip = (cx + math.cos(math.radians(ang - 6)) * ln, cy + math.sin(math.radians(ang - 6)) * ln)
            b1 = (cx + math.cos(a1) * r * 0.85, cy + math.sin(a1) * r * 0.85)
            b2 = (cx + math.cos(a2) * r * 0.85, cy + math.sin(a2) * r * 0.85)
            pygame.draw.polygon(spr, OUT, [b1, tip, b2])
            pygame.draw.polygon(spr, hair, [b1, (tip[0] * 0.92 + cx * 0.08, tip[1] * 0.92 + cy * 0.08), b2])
        cap(r * 1.05, -210, -25, hair)
    elif style == "horns":
        for sgn in (-1, 1):
            hx = cx + sgn * r * 0.6
            pts = [(hx - 4 * sgn, cy - r * 0.8), (hx + sgn * r * 0.9, cy - r * 2.1), (hx + sgn * 3, cy - r * 0.95)]
            pygame.draw.polygon(spr, OUT, pts)
            pygame.draw.polygon(spr, mix(acc, WHITE, 0.2), [(x, y + 1) for x, y in pts])
    # olhos
    if style not in ("visor", "hood"):
        ex, ey = cx + r * 0.42, cy - r * 0.05
        if f.state in ("hit", "ko"):
            pygame.draw.line(spr, OUT, (ex - 4, ey - 3), (ex + 4, ey + 3), 2)
            pygame.draw.line(spr, OUT, (ex - 4, ey + 3), (ex + 4, ey - 3), 2)
        elif style == "horns":
            pygame.draw.polygon(spr, acc, [(ex - 5, ey - 3), (ex + 6, ey), (ex - 5, ey + 3)])
        else:
            pygame.draw.ellipse(spr, WHITE, (ex - 3, ey - 4, 8, 9))
            pygame.draw.circle(spr, OUT, (int(ex + 2), int(ey)), 2)
            pygame.draw.line(spr, OUT, (ex - 5, ey - 6), (ex + 6, ey - 3), 2)
    elif style == "hood":
        pass


def draw_fighter(dst, f, shadow=True):
    if shadow:
        air = clamp((GROUND - f.y) / 260.0, 0, 1)
        w = int(110 * f.scale * (1 - air * 0.5))
        sh = pygame.Surface((w, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(120 * (1 - air * 0.6))), sh.get_rect())
        dst.blit(sh, (int(f.x - w / 2), int(GROUND - 9)))
    # aura de energia
    if f.state != "ko":
        k = f.energy / 100.0
        if k > 0.45:
            add_glow(dst, (f.x, f.y - 80 * f.scale), 110,
                     shade(f.ch["accent"], 0.22 + 0.14 * math.sin(f.anim * 6) * (k > 0.99) + 0.12 * k))
    if getattr(f, "invuln", 0) > 0 and int(f.invuln * 30) % 2:
        return
    if getattr(f, "awake", 0) > 0 and f.state != "ko":
        cy = f.y - 85 * f.scale
        add_glow(dst, (f.x, cy), 130, (120, 100, 30))
        for i in range(7):
            ph = (f.anim * 2.2 + i / 7.0) % 1.0
            px = f.x + math.sin(i * 2.3 + f.anim * 3) * 34 * f.scale
            py = f.y - ph * 190 * f.scale
            rr = max(2, int(9 * (1 - ph)))
            pygame.draw.circle(dst, (255, 236, 120) if i % 2 else (255, 200, 60), (int(px), int(py)), rr)
    if "aura" in f.ch.get("extras", ()) and f.state != "ko":
        cy = f.y - 85 * f.scale
        add_glow(dst, (f.x, cy), 96, shade(f.ch["accent"], 0.28))
        for i in range(5):
            a = f.anim * 1.8 + i * math.tau / 5
            px, py = f.x + math.cos(a) * 46 * f.scale, cy + math.sin(a * 1.3) * 70 * f.scale
            k = 0.5 + 0.5 * math.sin(f.anim * 7 + i)
            ln = 3 + 5 * k
            col = mix(f.ch["accent"], WHITE, 0.5)
            pygame.draw.line(dst, col, (px - ln, py), (px + ln, py), 2)
            pygame.draw.line(dst, col, (px, py - ln), (px, py + ln), 2)
    if getattr(f, "frames", None):
        img, ax, ay = frame_image(f)
        if f.state == "ko":
            ang = 84 * ease_out(f.ko_t / 0.45)
            blit_rot(dst, img, (ax, ay), (f.x, f.y + 2), ang if f.face > 0 else -ang)
        else:
            dst.blit(img, (int(f.x - ax), int(f.y - ay)))
        return
    spr = draw_fighter_sprite(f)
    if f.face < 0:
        spr = pygame.transform.flip(spr, True, False)
    if f.flash > 0:
        spr.fill((150, 150, 150) if f.flash_col == WHITE else (170, 40, 40),
                 special_flags=pygame.BLEND_RGB_ADD)
    pos = (f.x, f.y)
    if f.state == "ko":
        ang = 84 * ease_out(f.ko_t / 0.45)
        ang = ang if f.face > 0 else -ang
        blit_rot(dst, spr, (OX, OY), (pos[0], pos[1] + 2), ang)
    else:
        dst.blit(spr, (int(pos[0] - OX), int(pos[1] - OY)))


def fighter_snapshot(f):
    """Imagem do lutador no quadro atual, ja virada. Devolve (imagem, ax, ay) com ax/ay = pes."""
    if getattr(f, "frames", None):
        return frame_image(f)
    spr = draw_fighter_sprite(f)
    if f.face < 0:
        spr = pygame.transform.flip(spr, True, False)
    return spr, OX, OY


def blit_rot(dst, img, pivot, pos, angle):
    w, h = img.get_size()
    rot = pygame.transform.rotate(img, angle)
    off = pygame.math.Vector2(w / 2 - pivot[0], h / 2 - pivot[1]).rotate(-angle)
    dst.blit(rot, rot.get_rect(center=(pos[0] + off.x, pos[1] + off.y)))


# ----------------------------------------------------------------------------
# Cenario com paralaxe
# ----------------------------------------------------------------------------
class Background:
    def __init__(self, idx):
        th = THEMES[idx % len(THEMES)]
        self.th = th
        rng = random.Random(1000 + idx)
        self.sky = pygame.Surface((W, H))
        for y in range(HORIZON + 40):
            self.sky.fill(mix(th["top"], th["bot"], (y / (HORIZON + 40)) ** 1.25), (0, y, W, 1))
        for _ in range(140):
            x, y = rng.randrange(W), rng.randrange(0, 380)
            b = rng.randint(90, 230)
            self.sky.set_at((x, y), (b, b, min(255, b + 20)))
            if rng.random() < 0.15:
                pygame.draw.circle(self.sky, (b, b, 255), (x, y), 1)
        ox, oy = int(W * (0.68 + 0.1 * math.sin(idx))), 190
        add_glow(self.sky, (ox, oy), 240, shade(th["orb"], 0.55))
        pygame.draw.circle(self.sky, th["orb"], (ox, oy), 64)
        pygame.draw.circle(self.sky, mix(th["orb"], WHITE, 0.5), (ox - 14, oy - 14), 40)
        # chao
        for y in range(HORIZON, H):
            k = (y - HORIZON) / (H - HORIZON)
            self.sky.fill(mix(shade(th["floor"], 1.35), shade(th["floor"], 0.45), k ** 0.8), (0, y, W, 1))
        lc = th["line"]
        for i in range(1, 14):
            k = (i / 14) ** 2.0
            y = HORIZON + (H - HORIZON) * k
            pygame.draw.line(self.sky, shade(lc, 0.2 + 0.25 * k), (0, int(y)), (W, int(y)), 1)
        for i in range(-16, 17):
            x0 = W / 2 + i * 38
            x1 = W / 2 + i * 150
            pygame.draw.line(self.sky, shade(lc, 0.28), (int(x0), HORIZON), (int(x1), H), 1)
        pygame.draw.line(self.sky, lc, (0, HORIZON), (W, HORIZON), 3)
        add_glow(self.sky, (W // 2, HORIZON), 420, shade(lc, 0.14))
        self.far = self._layer(th["far"], th["c1"], 540, 260, rng, th)
        self.near = self._layer(th["near"], th["c2"], 575, 190, rng, th)
        self.vig = self._vignette()

    def _layer(self, kind, col, base, hgt, rng, th):
        w = W + 300
        s = pygame.Surface((w, H), pygame.SRCALPHA)
        s0, s1 = rng.uniform(0, 6), rng.uniform(0, 6)
        if kind == "mount":
            pts = [(0, base + 10)]
            for x in range(0, w + 12, 12):
                y = base - hgt * (0.38 + 0.30 * math.sin(x * 0.0042 + s0) + 0.22 * math.sin(x * 0.0125 + s1)
                                  + 0.10 * math.sin(x * 0.033 + s0))
                pts.append((x, y))
            pts.append((w, base + 10))
            pygame.draw.polygon(s, col, pts)
        elif kind == "city":
            x = 0
            while x < w:
                bw = rng.randint(46, 100)
                bh = rng.randint(int(hgt * 0.3), int(hgt))
                pygame.draw.rect(s, col, (x, base - bh, bw, bh + 20))
                pygame.draw.rect(s, shade(col, 1.5), (x, base - bh, bw, 3))
                for wy in range(base - bh + 10, base - 6, 14):
                    for wx in range(x + 7, x + bw - 8, 12):
                        if rng.random() < 0.38:
                            pygame.draw.rect(s, mix(th["line"], WHITE, rng.random() * 0.5), (wx, wy, 5, 7))
                if rng.random() < 0.3:
                    pygame.draw.line(s, shade(col, 1.6), (x + bw // 2, base - bh), (x + bw // 2, base - bh - 26), 2)
                x += bw + rng.randint(0, 10)
        elif kind == "forest":
            x = -20
            while x < w:
                tw = rng.randint(50, 96)
                th_ = rng.randint(int(hgt * 0.5), int(hgt))
                for i in range(3):
                    yy = base - th_ + i * th_ * 0.26
                    pygame.draw.polygon(s, col, [(x + tw / 2, yy - th_ * 0.1), (x + tw * (0.1 - i * 0.04), yy + th_ * 0.45),
                                                 (x + tw * (0.9 + i * 0.04), yy + th_ * 0.45)])
                pygame.draw.rect(s, col, (x + tw / 2 - 4, base - 20, 8, 40))
                x += rng.randint(30, 70)
        elif kind == "spike":
            x = -10
            while x < w:
                sw = rng.randint(30, 80)
                sh = rng.randint(int(hgt * 0.3), int(hgt))
                pygame.draw.polygon(s, col, [(x, base + 20), (x + sw * rng.uniform(0.3, 0.7), base - sh), (x + sw, base + 20)])
                x += rng.randint(20, 60)
        elif kind == "float":
            for _ in range(11):
                x, y = rng.randint(0, w), rng.randint(int(base - hgt), int(base - 40))
                rw, rh = rng.randint(60, 150), rng.randint(24, 60)
                pygame.draw.polygon(s, col, [(x - rw / 2, y), (x + rw / 2, y), (x + rw * 0.1, y + rh * 1.6), (x - rw * 0.2, y + rh)])
                pygame.draw.ellipse(s, shade(col, 1.5), (x - rw / 2, y - 6, rw, 14))
        return s

    def _vignette(self):
        small = pygame.Surface((64, 36), pygame.SRCALPHA)
        for y in range(36):
            for x in range(64):
                d = math.hypot((x - 31.5) / 32, (y - 17.5) / 18)
                small.set_at((x, y), (0, 0, 0, int(clamp((d - 0.55) * 210, 0, 170))))
        return pygame.transform.smoothscale(small, (W, H))

    def draw(self, dst, cam, t):
        dst.blit(self.sky, (0, 0))
        dst.blit(self.far, (-150 - cam * 0.03, 0))
        dst.blit(self.near, (-150 - cam * 0.08, 0))
        # bruma no horizonte
        add_glow(dst, (W // 2 - cam * 0.05, HORIZON + 10), 380, shade(self.th["line"], 0.07))

    def draw_front(self, dst):
        dst.blit(self.vig, (0, 0))


# ----------------------------------------------------------------------------
# Particulas e projeteis
# ----------------------------------------------------------------------------
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size", "col", "grav", "kind", "img", "drag")

    def __init__(self, x, y, vx, vy, life, size, col, grav=0.0, kind="dot", img=None, drag=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.size, self.col, self.grav, self.kind, self.img, self.drag = size, col, grav, kind, img, drag

    def update(self, dt):
        self.life -= dt
        self.vy += self.grav * dt
        if self.drag:
            k = math.exp(-self.drag * dt)
            self.vx *= k
            self.vy *= k
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, dst):
        k = clamp(self.life / self.max, 0, 1)
        if self.kind == "dot":
            pygame.draw.circle(dst, self.col, (int(self.x), int(self.y)), max(1, int(self.size * k)))
        elif self.kind == "line":
            m = max(0.01, math.hypot(self.vx, self.vy))
            ln = clamp(m * 0.035, 3, 40) * k
            pygame.draw.line(dst, self.col, (self.x, self.y),
                             (self.x - self.vx / m * ln, self.y - self.vy / m * ln), max(1, int(self.size * k)))
        elif self.kind == "ring":
            r = self.size * ease_out(1 - k)
            pygame.draw.circle(dst, self.col, (int(self.x), int(self.y)), max(2, int(r)), max(1, int(7 * k)))
        elif self.kind == "wave":
            r = self.size * ease_out(1 - k)
            rect = pygame.Rect(0, 0, int(r * 2), max(4, int(r * 0.34)))
            rect.center = (int(self.x), int(self.y))
            pygame.draw.ellipse(dst, self.col, rect, max(1, int(6 * k)))
        elif self.kind == "glow":
            add_glow(dst, (self.x, self.y), self.size * (0.5 + 0.5 * k), self.col)
        elif self.kind == "img":
            self.img.set_alpha(int(255 * clamp(k * 2.2, 0, 1)))
            dst.blit(self.img, self.img.get_rect(center=(int(self.x), int(self.y))))


class Projectile:
    def __init__(self, owner, x, y, spec):
        self.owner, self.x, self.y = owner, x, y
        self.vx = owner.face * spec["speed"]
        self.spec = spec
        self.size = spec["size"]
        self.col = spec["col"]
        self.shape = spec.get("shape", "orb")
        self.age = 0.0
        self.dead = False
        self.mv = dict(type="proj", dmg=spec["dmg"], stun=0.42, kb=340, pop=230, hs=0.08, sfx="special")

    def rect(self):
        w = self.size * (2.6 if self.shape == "arrow" else 2.0)
        h = self.size * 1.3 if self.shape != "arrow" else self.size * 0.9
        return pygame.Rect(self.x - w / 2, self.y - h / 2, w, h)

    def update(self, dt, fight):
        self.age += dt
        self.x += self.vx * dt
        if self.x < -120 or self.x > W + 120:
            self.dead = True
        if random.random() < dt * 90:
            fight.parts.append(Particle(self.x, self.y + random.uniform(-self.size * .5, self.size * .5),
                                        -self.vx * 0.12, random.uniform(-40, 40), 0.3, self.size * 0.45,
                                        self.col, 0, "dot"))

    def draw(self, dst):
        pulse = 1 + 0.12 * math.sin(self.age * 30)
        add_glow(dst, (self.x, self.y), self.size * 3.2 * pulse, shade(self.col, 0.75))
        if self.shape == "arrow":
            d = 1 if self.vx > 0 else -1
            L = self.size * 4
            pts = [(self.x + d * L * 0.5, self.y), (self.x - d * L * 0.5, self.y - self.size * 0.35),
                   (self.x - d * L * 0.3, self.y), (self.x - d * L * 0.5, self.y + self.size * 0.35)]
            pygame.draw.polygon(dst, self.col, pts)
            pygame.draw.line(dst, WHITE, (self.x - d * L * 0.25, self.y), (self.x + d * L * 0.45, self.y), 3)
        else:
            pygame.draw.circle(dst, self.col, (int(self.x), int(self.y)), int(self.size * pulse))
            pygame.draw.circle(dst, mix(self.col, WHITE, 0.6), (int(self.x), int(self.y)), int(self.size * 0.62 * pulse))
            pygame.draw.circle(dst, WHITE, (int(self.x), int(self.y)), int(self.size * 0.3))


# ----------------------------------------------------------------------------
# Lutador
# ----------------------------------------------------------------------------
class Fighter:
    def __init__(self, ch, level, x, face, idx):
        self.ch = ch
        self.idx = idx
        self.level = level
        self.moves = build_moves(ch)
        self.parts = load_parts(ch["name"], ch.get("outfit_idx", 0))
        self.frames = load_frames(ch["name"], ch.get("scale", 1.0))
        self.scale = ch.get("scale", 1.0)
        self.maxhp = ch["hp"] * (1 + 0.06 * (level - 1))
        self.dmg_mult = ch["pow"] * (1 + 0.04 * (level - 1))
        self.speed = 330 * ch["spd"]
        self.jump_v = 1000
        self.name = ch["name"]
        self.reset(x, face)
        self.energy = 25.0

    def reset(self, x, face):
        self.x, self.y = float(x), float(GROUND)
        self.vx = self.vy = 0.0
        self.face = face
        self.hp = self.maxhp
        self.trail = self.maxhp
        self.trail_delay = 0.0
        self.state = "idle"
        self.on_ground = True
        self.t = 0.0
        self.move = None
        self.hit_done = False
        self.spawned = False
        self.stun = 0.0
        self.anim = random.random() * 3
        self.walk_phase = 0.0
        self.flash = 0.0
        self.flash_col = WHITE
        self.combo = 0
        self.combo_t = 0.0
        self.buffer = None
        self.buffer_t = 0.0
        self.ko_t = 0.0
        self.invuln = 0.0
        self.awake = 0.0
        self.charge_full = 0.0
        self.ult_hits = 0
        self.ult_cd = 0.0

    def power(self):
        return self.dmg_mult * (1.25 if self.awake > 0 else 1.0)

    # ---- caixas de colisao (AABB) --------------------------------------------
    def hurtbox(self):
        s = self.scale
        h = 150 * s if self.state != "block" else 140 * s
        return pygame.Rect(self.x - 27 * s, self.y - h, 54 * s, h)

    def hitbox(self, mv):
        if mv["type"] == "ult" and mv["kind"] == "quake":
            return pygame.Rect(self.x - mv["reach"], self.y - mv["h"], mv["reach"] * 2, mv["h"])
        if mv["type"] == "ult" and mv["kind"] == "storm":
            left = self.x + 60 if self.face > 0 else self.x - 60 - mv["reach"]
            return pygame.Rect(left, self.y - mv["h"], mv["reach"], mv["h"])
        if mv["type"] == "slam":
            return pygame.Rect(self.x - mv["reach"], self.y - mv["h"], mv["reach"] * 2, mv["h"])
        w, h = mv["reach"] * self.scale, mv["h"]
        left = self.x + 8 if self.face > 0 else self.x - 8 - w
        return pygame.Rect(left, self.y - mv["yc"] * self.scale - h / 2, w, h)

    # ---- atualizacao -------------------------------------------------------------
    def update(self, dt, inp, foe, fight):
        self.anim += dt
        self.flash = max(0.0, self.flash - dt)
        self.buffer_t -= dt
        self.combo_t -= dt
        if self.combo_t <= 0:
            self.combo = 0
        if self.trail_delay > 0:
            self.trail_delay -= dt
        elif self.trail > self.hp:
            self.trail = max(self.hp, self.trail - self.maxhp * 0.45 * dt)
        if self.state == "ko":
            self.ko_t += dt
            self.physics(dt, fight)
            return
        self.invuln = max(0.0, self.invuln - dt)
        if self.awake > 0:
            self.awake = max(0.0, self.awake - dt)
            if self.awake == 0:
                fight.floater(self.x, self.y - 200, "FIM DO DESPERTAR", (220, 210, 160), 26)
        if self.state != "win":
            self.energy = min(100.0, self.energy + 2.5 * dt)
        for tap in inp["taps"]:
            self.buffer, self.buffer_t = tap, 0.18
        if self.state == "hit" and "charge" in inp["taps"] and self.energy >= 30:
            self.substitute(foe, fight)

        if self.state == "hit":
            self.stun -= dt
            if self.stun <= 0:
                self.state = "idle" if self.on_ground else "jump"
        elif self.state == "attack":
            self.t += dt
            self.attack_logic(dt, foe, fight)
        elif self.state == "win":
            pass
        else:
            self.free_control(inp, foe, fight, dt)
        self.physics(dt, fight)
        if self.state == "walk":
            self.walk_phase += dt * abs(self.vx) / 30.0 * (1 if self.vx * self.face >= 0 else -1)

    def substitute(self, foe, fight):
        """Substituicao: some numa nuvem de fumaca, deixa um tronco e reaparece atras do inimigo."""
        self.energy -= 30
        fight.substitution_fx(self.x, self.y)
        self.x = clamp(foe.x - foe.face * 85, STAGE_L, STAGE_R)
        self.y, self.vy, self.vx, self.on_ground = float(GROUND), 0.0, 0.0, True
        self.state, self.stun, self.move = "idle", 0.0, None
        self.invuln = 0.35
        self.face = 1 if foe.x >= self.x else -1
        foe.combo = 0
        fight.substitution_fx(self.x, self.y, log=False)
        fight.floater(self.x, self.y - 205, "SUBSTITUICAO!", (200, 240, 255), 30)
        fight.sfx.play("jump")

    def awaken(self, fight):
        """Despertar: transformacao que gasta a barra inteira e da +25% de dano e +15% de velocidade."""
        self.energy, self.awake, self.charge_full = 0.0, 12.0, 0.0
        fight.flash_a = max(fight.flash_a, 0.7)
        fight.shake = max(fight.shake, 12)
        cy = self.y - 90 * self.scale
        fight.parts.append(Particle(self.x, cy, 0, 0, 0.6, 220, (255, 230, 120), 0, "ring"))
        fight.parts.append(Particle(self.x, self.y - 4, 0, 0, 0.7, 300, (255, 210, 80), 0, "wave"))
        fight.burst(self.x, cy, (255, 236, 140), 30, 700, 0.6, 5, 0)
        fight.floater(self.x, self.y - 215, "DESPERTAR!", (255, 228, 90), 48)
        fight.sfx.play("level")

    def free_control(self, inp, foe, fight, dt=0.0):
        mv = int(inp["right"]) - int(inp["left"])
        buf = self.buffer if self.buffer_t > 0 else None
        if self.on_ground and inp.get("charge") and not inp["down"] and buf != "ult":
            self.face = 1 if foe.x >= self.x else -1
            self.state, self.vx = "charge", 0.0
            self.energy = min(100.0, self.energy + 40 * dt)
            if self.energy >= 100 and self.awake <= 0:
                self.charge_full += dt
                if self.charge_full >= 0.8:
                    self.awaken(fight)
            fight.chakra_fx(self, dt)
            return
        self.charge_full = 0.0
        if self.on_ground:
            self.face = 1 if foe.x >= self.x else -1
            if inp["down"]:
                self.state, self.vx = "block", 0.0
            else:
                self.vx = mv * self.speed * (1.15 if self.awake > 0 else 1.0)
                self.state = "walk" if mv else "idle"
        else:
            self.state = "jump"
        if buf == "ult":
            self.buffer = None
            if self.state == "block":
                self.state = "idle"
            self.start_attack("ult", fight)
            return
        if buf == "jump" and self.on_ground and self.state != "block":
            self.vy, self.on_ground, self.state = -self.jump_v, False, "jump"
            self.vx = mv * self.speed
            self.buffer = None
            fight.sfx.play("jump")
            fight.dust(self.x, self.y, 6)
        elif buf in ("punch", "kick", "special") and self.state != "block":
            if self.start_attack(buf, fight):
                self.buffer = None
        elif buf in ("punch", "kick", "special") and self.state == "block":
            self.state = "idle"
            if self.start_attack(buf, fight):
                self.buffer = None

    def start_attack(self, name, fight):
        mv = self.moves[name]
        if mv["cost"] > self.energy:
            if name == "special":
                fight.floater(self.x, self.y - 190, "SEM ENERGIA", (200, 200, 220), 26)
            elif name == "ult":
                fight.floater(self.x, self.y - 190, "PRECISA DE 100% DE ENERGIA", (200, 200, 220), 24)
            return False
        self.energy -= mv["cost"]
        if name == "special" and self.idx == 0:
            fight.stats["specials"] += 1
        self.state, self.move, self.t = "attack", name, 0.0
        self.hit_done = self.spawned = False
        if self.on_ground and mv["type"] != "dash":
            self.vx = 0.0
        fight.sfx.play("swing" if name not in ("special", "ult") else "special")
        if name == "ult":
            self.ult_hits, self.ult_cd = 0, 0.0
            fight.begin_cutin(self)
        return True

    def attack_logic(self, dt, foe, fight):
        mv = self.moves[self.move]
        total = mv["start"] + mv["active"] + mv["rec"]
        if self.t >= total:
            self.state = "idle" if self.on_ground else "jump"
            self.move = None
            return
        active = mv["start"] <= self.t < mv["start"] + mv["active"]
        typ = mv["type"]
        if typ == "ult":
            if mv["kind"] in ("clones", "flurry"):
                self.vx = self.face * mv["speed"] if active else self.vx * math.exp(-12 * dt)
            if active and not self.spawned:
                self.spawned = True
                fight.ult_fx(self, mv)
            if active:
                self.ult_cd -= dt
                if self.ult_cd <= 0 and self.ult_hits < mv["hits"] and foe.state != "ko" and foe.invuln <= 0:
                    hb = self.hitbox(mv)
                    if hb.colliderect(foe.hurtbox()):
                        self.ult_hits += 1
                        self.ult_cd = 0.07
                        last = self.ult_hits >= mv["hits"]
                        hit = dict(mv, dmg=mv["dmg"] / mv["hits"], kb=mv["kb"] if last else 40,
                                   pop=mv["pop"] if last else 0, stun=mv["stun"] if last else 0.45,
                                   hs=mv["hs"] if last else 0.03)
                        foe.take_hit(self, hit, fight, hb)
            return
        if typ == "proj":
            if not self.spawned and self.t >= mv["start"]:
                self.spawned = True
                fight.projectiles.append(Projectile(self, self.x + self.face * 60 * self.scale,
                                                    self.y - 118 * self.scale, mv))
                fight.burst(self.x + self.face * 60, self.y - 118 * self.scale, mv["col"], 10, 360, 0.3, 4, 0, "line")
                fight.shake = max(fight.shake, 3)
        else:
            if typ == "dash":
                self.vx = self.face * mv["speed"] if active else self.vx * math.exp(-14 * dt)
                if active and random.random() < 0.8:
                    fight.parts.append(Particle(self.x, self.y - random.uniform(20, 140), -self.face * 100, 0, 0.3, 7,
                                                mv["col"], 0, "dot"))
            elif typ == "slam" and active and not self.spawned:
                self.spawned = True
                fight.parts.append(Particle(self.x, self.y - 4, 0, 0, 0.55, mv["reach"], mv["col"], 0, "wave"))
                fight.parts.append(Particle(self.x, self.y - 4, 0, 0, 0.4, mv["reach"] * 0.6, WHITE, 0, "wave"))
                fight.dust(self.x - 60, self.y, 8)
                fight.dust(self.x + 60, self.y, 8)
                fight.shake = max(fight.shake, 10)
            if active and not self.hit_done:
                if mv.get("ground_only") and not foe.on_ground:
                    return
                hb = self.hitbox(mv)
                if foe.state != "ko" and foe.invuln <= 0 and hb.colliderect(foe.hurtbox()):
                    self.hit_done = True
                    foe.take_hit(self, mv, fight, hb)

    def take_hit(self, atk, mv, fight, hb=None, point=None):
        if self.invuln > 0:
            return
        hurt = self.hurtbox()
        if point is None:
            point = hb.clip(hurt).center if hb is not None and hb.clip(hurt).w else hurt.center
        blocked = self.state == "block" and self.on_ground
        was_hit = self.state == "hit"
        dmg = mv["dmg"] * atk.power()
        if was_hit and mv["type"] != "ult":
            dmg *= max(0.45, 1 - 0.1 * atk.combo)
        if blocked:
            dmg *= 0.3 if mv["type"] == "ult" else 0.12
            self.vx = atk.face * mv["kb"] * 0.55
            self.energy = min(100, self.energy + 5)
            fight.burst(point[0], point[1], (170, 220, 255), 8, 340, 0.25, 3)
            fight.parts.append(Particle(point[0], point[1], 0, 0, 0.25, 46, (170, 220, 255), 0, "ring"))
            fight.sfx.play("block")
            fight.hitstop = max(fight.hitstop, 0.04)
            fight.shake = max(fight.shake, 2)
        else:
            self.state, self.stun, self.move = "hit", mv["stun"], None
            self.vx = atk.face * mv["kb"]
            if mv["pop"]:
                self.vy, self.on_ground = -mv["pop"], False
            atk.combo = atk.combo + 1 if was_hit else 1
            atk.combo_t = 1.1
            atk.energy = min(100, atk.energy + 7)
            self.energy = min(100, self.energy + 5)
            self.flash, self.flash_col = 0.09, WHITE
            fight.sfx.play(mv.get("sfx", "punch") if mv["type"] == "melee" else "kick")
            fight.hitstop = max(fight.hitstop, mv["hs"])
            fight.shake = max(fight.shake, 4 + dmg * 0.7)
            col = atk.ch["accent"]
            fight.burst(point[0], point[1], mix(col, WHITE, 0.4), 12 + int(dmg), 520 + dmg * 12, 0.38, 4, 700)
            fight.parts.append(Particle(point[0], point[1], 0, 0, 0.3, 64 + dmg * 3, WHITE, 0, "ring"))
            fight.parts.append(Particle(point[0], point[1], 0, 0, 0.18, 120 + dmg * 5, mix(col, WHITE, 0.3), 0, "glow"))
        self.hp -= dmg
        self.trail_delay = 0.45
        st = fight.stats
        if self.idx == 0:
            st["blocks" if blocked else "hits_taken"] += 1
        elif atk.idx == 0:
            st["hits"] += 1
            st["dmg_dealt"] += dmg
            st["max_combo"] = max(st["max_combo"], atk.combo)
        fight.floater(point[0] + random.uniform(-14, 14), point[1] - 30, str(max(1, int(round(dmg)))),
                      (170, 220, 255) if blocked else (255, 236, 120), 40 if not blocked else 28)
        if self.hp <= 0:
            self.hp = 0
            self.state, self.move = "ko", None
            self.vx, self.vy, self.on_ground = atk.face * 560, -520, False
            self.ko_t = 0.0
            fight.sfx.play("ko")
            fight.hitstop = max(fight.hitstop, 0.2)
            fight.shake = max(fight.shake, 16)

    def physics(self, dt, fight):
        self.vy += GRAV * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y >= GROUND:
            if not self.on_ground and self.vy > 250:
                fight.dust(self.x, GROUND, 5)
                if self.state != "ko":
                    fight.sfx.play("land")
            self.y, self.vy, self.on_ground = float(GROUND), 0.0, True
            if self.state == "jump":
                self.state = "idle"
        else:
            self.on_ground = False
        if self.on_ground:
            if self.state in ("hit", "ko"):
                self.vx *= math.exp(-8 * dt)
            elif self.state == "attack" and self.moves[self.move]["type"] != "dash" and \
                    self.moves[self.move].get("kind") not in ("clones", "flurry"):
                self.vx *= math.exp(-14 * dt)
            elif self.state == "block":
                self.vx *= math.exp(-10 * dt)
        self.x = clamp(self.x, STAGE_L, STAGE_R)


# ----------------------------------------------------------------------------
# Entradas (humano / IA)
# ----------------------------------------------------------------------------
def make_keymap(player, story):
    if player == 0:
        km = dict(left=[pygame.K_a], right=[pygame.K_d], up=[pygame.K_w], down=[pygame.K_s],
                  punch=[pygame.K_j], kick=[pygame.K_k], special=[pygame.K_l],
                  charge=[pygame.K_u], ult=[pygame.K_i])
        if story:
            km["left"].append(pygame.K_LEFT)
            km["right"].append(pygame.K_RIGHT)
            km["up"].append(pygame.K_UP)
            km["down"].append(pygame.K_DOWN)
            km["punch"].append(pygame.K_z)
            km["kick"].append(pygame.K_x)
            km["special"].append(pygame.K_c)
            km["charge"].append(pygame.K_v)
            km["ult"].append(pygame.K_b)
        return km
    return dict(left=[pygame.K_LEFT], right=[pygame.K_RIGHT], up=[pygame.K_UP], down=[pygame.K_DOWN],
                punch=[pygame.K_n, pygame.K_KP1], kick=[pygame.K_m, pygame.K_KP2],
                special=[pygame.K_COMMA, pygame.K_KP3], charge=[pygame.K_PERIOD, pygame.K_KP4],
                ult=[pygame.K_SLASH, pygame.K_KP5])


class AI:
    def __init__(self, diff):
        self.diff = diff
        self.cool = 0.5
        self.mode = "approach"
        self.mode_t = 0.0
        self.was_hit = False

    def think(self, dt, me, foe):
        inp = dict(left=False, right=False, up=False, down=False, charge=False, taps=[])
        self.cool -= dt
        self.mode_t -= dt
        d = foe.x - me.x
        ad = abs(d)
        toward = "right" if d > 0 else "left"
        away = "left" if d > 0 else "right"
        if me.state == "hit":
            if not self.was_hit and me.energy >= 30 and random.random() < 0.3 * self.diff:
                inp["taps"].append("charge")          # substituicao
            self.was_hit = True
        else:
            self.was_hit = False
        committed = self.mode == "charge" and self.mode_t > 0      # nao interrompe a carga de chakra
        if self.cool <= 0 and me.state not in ("hit", "ko") and not committed:
            self.cool = random.uniform(0.10, 0.34) * (1.7 - self.diff)
            sp = me.moves["special"]
            ult = me.moves["ult"]
            r = random.random()
            if me.energy >= 100 and ad < ULT_RANGE[ult["kind"]] and abs(me.y - foe.y) < 120 and r < 0.6:
                self.mode, self.mode_t = "ult", 0.05
            elif me.energy >= 100 and me.awake <= 0 and ad > 300 and r < 0.5:
                self.mode, self.mode_t = "charge", 1.1
            elif me.energy < 40 and ad > 340 and r < 0.25:
                self.mode, self.mode_t = "charge", random.uniform(0.4, 0.8)
            elif foe.state == "attack" and ad < 190 and r < 0.18 + 0.6 * self.diff:
                self.mode, self.mode_t = "block", random.uniform(0.25, 0.5)
            elif sp["type"] == "proj" and ad > 260 and me.energy >= sp["cost"] and r < 0.5:
                self.mode, self.mode_t = "special", 0.05
            elif ad > 150:
                self.mode, self.mode_t = ("approach", random.uniform(0.2, 0.5)) if r < 0.85 else ("jump", 0.1)
            else:
                if sp["type"] != "proj" and me.energy >= sp["cost"] and ad < sp.get("reach", 150) + 40 and r < 0.18:
                    self.mode, self.mode_t = "special", 0.05
                else:
                    pick = random.random()
                    if pick < 0.40 * (0.6 + self.diff):
                        self.mode, self.mode_t = "punch", 0.05
                    elif pick < 0.62:
                        self.mode, self.mode_t = "kick", 0.05
                    elif pick < 0.78:
                        self.mode, self.mode_t = "retreat", random.uniform(0.15, 0.35)
                    elif pick < 0.88:
                        self.mode, self.mode_t = "block", random.uniform(0.2, 0.4)
                    else:
                        self.mode, self.mode_t = "jump", 0.1
        m = self.mode
        if m == "approach" and self.mode_t > 0:
            inp[toward] = True
        elif m == "retreat" and self.mode_t > 0:
            inp[away] = True
        elif m == "block" and self.mode_t > 0:
            inp["down"] = True
        elif m == "charge" and self.mode_t > 0:
            inp["charge"] = True
        elif m == "ult":
            inp["taps"].append("ult")
            self.mode, self.mode_t = "approach", 0.0
        elif m in ("punch", "kick", "special", "jump"):
            inp["taps"].append(m)
            if m == "jump":
                inp[toward] = True
            self.mode, self.mode_t = "approach", 0.0
        return inp


# ----------------------------------------------------------------------------
# Cena de luta
# ----------------------------------------------------------------------------
class Fight:
    def __init__(self, game, ch1, ch2, lv1, lv2, mode, stage=0, ai_diff=0.5, theme=0):
        self.game = game
        self.sfx = game.sfx
        self.mode = mode
        self.stage = stage
        self.p = [Fighter(ch1, lv1, W / 2 - 230, 1, 0), Fighter(ch2, lv2, W / 2 + 230, -1, 1)]
        self.ai = AI(ai_diff) if mode in ("story", "cpu", "mine", "raid") else None
        self.keymaps = [make_keymap(0, mode != "versus"), make_keymap(1, False)]
        self.taps = [[], []]
        self.bg = game.get_bg(theme)
        self.canvas = pygame.Surface((W, H))
        self.flash_surf = pygame.Surface((W, H))
        self.flash_surf.fill(WHITE)
        self.parts = []
        self.projectiles = []
        self.shake = 0.0
        self.hitstop = 0.0
        self.flash_a = 0.0
        self.wins = [0, 0]
        self.round = 1
        self.paused = False
        self.t_total = 0.0
        self.result = None
        self.perfect = True
        self.cutin = None
        self.effects = []
        self.stats = dict(blocks=0, hits_taken=0, hits=0, dmg_dealt=0.0, specials=0, max_combo=0)
        self.announce_txt, self.announce_t, self.announce_col = "", 0.0, WHITE
        self.start_round()

    # ---- efeitos -------------------------------------------------------------------
    def burst(self, x, y, col, n=12, spd=420, life=0.35, size=4, grav=900, kind="line"):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            v = random.uniform(spd * 0.3, spd)
            self.parts.append(Particle(x, y, math.cos(a) * v, math.sin(a) * v, life * random.uniform(0.6, 1.2),
                                       size, col, grav, kind, drag=2.0))

    def dust(self, x, y, n):
        for _ in range(n):
            d = random.choice((-1, 1))
            self.parts.append(Particle(x + random.uniform(-14, 14), y - 4, d * random.uniform(30, 160),
                                       random.uniform(-90, -10), random.uniform(0.25, 0.5), random.uniform(5, 10),
                                       (200, 190, 200), -40, "dot", drag=3.0))

    def floater(self, x, y, s, col, size):
        img = font(size).render(s, True, col)
        sh = font(size).render(s, True, (10, 6, 20))
        out = pygame.Surface((img.get_width() + 4, img.get_height() + 4), pygame.SRCALPHA)
        out.blit(sh, (3, 3))
        out.blit(sh, (1, 3))
        out.blit(img, (1, 1))
        self.parts.append(Particle(x, y, random.uniform(-20, 20), -90, 0.9, 0, col, 60, "img", out))

    # ---- efeitos ninja/anime -----------------------------------------------------------
    def chakra_fx(self, f, dt):
        col = AWAKE_HAIR if f.awake > 0 else f.ch["accent"]
        n = int(dt * 60) + (1 if random.random() < (dt * 60) % 1 else 0)
        for _ in range(n):
            self.parts.append(Particle(f.x + random.uniform(-34, 34), f.y - random.uniform(0, 40),
                                       random.uniform(-15, 15), random.uniform(-300, -150), random.uniform(0.4, 0.7),
                                       random.uniform(4, 8), col, -60, "dot"))
        if int(f.anim * 3) != int((f.anim - dt) * 3):
            self.parts.append(Particle(f.x, f.y - 4, 0, 0, 0.5, 90, col, 0, "wave"))

    _log_img = None

    def substitution_fx(self, x, y, log=True):
        for _ in range(16):
            a = random.uniform(0, math.tau)
            v = random.uniform(40, 200)
            self.parts.append(Particle(x + random.uniform(-20, 20), y - random.uniform(30, 140), math.cos(a) * v,
                                       math.sin(a) * v - 40, random.uniform(0.4, 0.7), random.uniform(10, 20),
                                       random.choice([(230, 230, 236), (200, 200, 210), (170, 170, 182)]), -80, "dot", drag=3))
        if log:
            if Fight._log_img is None:
                img = pygame.Surface((40, 92), pygame.SRCALPHA)
                pygame.draw.rect(img, OUT, (2, 2, 36, 88), border_radius=14)
                pygame.draw.rect(img, (140, 92, 52), (5, 5, 30, 82), border_radius=12)
                pygame.draw.rect(img, (170, 118, 70), (9, 8, 9, 76), border_radius=4)
                pygame.draw.ellipse(img, (214, 170, 110), (6, 4, 28, 14))
                pygame.draw.ellipse(img, (150, 100, 56), (12, 7, 16, 8), 2)
                for yy in (34, 58):
                    pygame.draw.line(img, (100, 64, 34), (7, yy), (33, yy + 4), 2)
                Fight._log_img = img
            self.parts.append(Particle(x, y - 80, random.uniform(-40, 40), -160, 0.9, 0, WHITE, 900, "img",
                                       Fight._log_img.copy()))

    def begin_cutin(self, f):
        self.cutin = dict(f=f, t=0.0, dur=1.25)
        self.flash_a = max(self.flash_a, 0.35)

    def ult_fx(self, f, mv):
        self.effects.append(dict(kind=mv["kind"], t=0.0, dur=mv["active"] + 0.35, owner=f, x=f.x, y=f.y,
                                 face=f.face, col=mv["col"], seed=random.random()))
        self.shake = max(self.shake, 14)

    def draw_effects(self, c):
        for e in self.effects:
            k = clamp(e["t"] / e["dur"], 0, 1)
            col, f = e["col"], e["owner"]
            fade = math.sin(math.pi * k)
            if e["kind"] == "beam":
                y0 = f.y - 112 * f.scale
                x0 = f.x + f.face * 50
                x1 = W + 60 if f.face > 0 else -60
                w = 20 + 90 * fade * (0.9 + 0.1 * math.sin(e["t"] * 60))
                left, right = min(x0, x1), max(x0, x1)
                pygame.draw.rect(c, col, (left, y0 - w / 2, right - left, w))
                pygame.draw.rect(c, mix(col, WHITE, 0.6), (left, y0 - w * 0.3, right - left, w * 0.6))
                pygame.draw.rect(c, WHITE, (left, y0 - w * 0.12, right - left, w * 0.24))
                add_glow(c, (x0, y0), 120 + 60 * fade, shade(col, 0.8))
            elif e["kind"] == "storm":
                rnd = random.Random(int(e["t"] * 20) + int(e["seed"] * 1000))
                tx = e["x"] + e["face"] * 320
                for i in range(5):
                    if rnd.random() < 0.75:
                        bx = tx + (i - 2) * 70 + rnd.uniform(-20, 20)
                        pts, yy, xx = [], 0, bx + rnd.uniform(-30, 30)
                        while yy < GROUND:
                            pts.append((xx, yy))
                            yy += rnd.uniform(30, 60)
                            xx += rnd.uniform(-25, 25)
                        pts.append((bx, GROUND))
                        pygame.draw.lines(c, col, False, pts, 8)
                        pygame.draw.lines(c, WHITE, False, pts, 3)
                        add_glow(c, (bx, GROUND - 10), 70, shade(col, 0.7))
            elif e["kind"] == "quake":
                for i in range(-4, 5):
                    hgt = 280 * fade * (1 - abs(i) / 6)
                    px = e["x"] + i * 92
                    pygame.draw.rect(c, col, (px - 24, GROUND - hgt, 48, hgt))
                    pygame.draw.rect(c, mix(col, WHITE, 0.6), (px - 10, GROUND - hgt * 0.9, 20, hgt * 0.9))
                    add_glow(c, (px, GROUND - hgt * 0.6), 60, shade(col, 0.6))
            elif e["kind"] in ("clones", "flurry"):
                img, ax, ay = fighter_snapshot(f)
                n = 3 if e["kind"] == "clones" else 2
                for j in range(n):
                    ghost = img.copy()
                    ghost.fill((90, 60, 110) if e["kind"] == "clones" else (60, 40, 20), special_flags=pygame.BLEND_RGB_SUB)
                    ghost.set_alpha(int((170 - j * 45) * fade))
                    off = -f.face * 70 * (j + 1)
                    c.blit(ghost, (int(f.x + off - ax), int(f.y - ay)))
                if e["kind"] == "flurry":
                    rnd = random.Random(int(e["t"] * 30))
                    for _ in range(8):
                        sx = f.x + f.face * rnd.uniform(40, 130)
                        sy = f.y - rnd.uniform(60, 150)
                        pygame.draw.line(c, mix(col, WHITE, 0.4), (sx, sy), (sx + f.face * 40, sy + rnd.uniform(-10, 10)), 5)
                        pygame.draw.circle(c, WHITE, (int(sx + f.face * 40), int(sy)), 6)

    def draw_cutin(self, c):
        cu = self.cutin
        f, k = cu["f"], cu["t"] / cu["dur"]
        alpha = clamp(min(k * 6, (1 - k) * 6), 0, 1)
        self.dim(c, int(160 * alpha))
        col = f.ch["accent"]
        band = pygame.Surface((W, 260), pygame.SRCALPHA)
        band.fill(col + (int(200 * alpha),))
        for i in range(22):
            yy = (i * 37 + int(cu["t"] * 900)) % 260
            ln = 120 + (i * 53) % 300
            xx = (i * 211 + int(cu["t"] * 2200)) % (W + ln) - ln
            pygame.draw.line(band, (255, 255, 255, int(160 * alpha)), (xx, yy), (xx + ln, yy), 3)
        band = pygame.transform.rotate(band, 6)
        c.blit(band, band.get_rect(center=(W // 2, 330)))
        bx = lerp(-260, 360, ease_out(min(1, k * 3)))
        draw_bust(c, f, (bx, 470), 2.5, 1)
        mv = f.moves["ult"]
        tx = lerp(W + 400, 820, ease_out(min(1, k * 2.4)))
        text(c, "JUTSU FINAL!", 40, (tx, 255), shade(WHITE, 0.4 + 0.6 * alpha), "center", OUT, 3)
        text(c, mv["name"].upper(), 76, (tx, 330), shade(mix(col, WHITE, 0.7), 0.4 + 0.6 * alpha), "center", OUT, 5)

    def announce(self, s, col=WHITE, dur=1.4):
        self.announce_txt, self.announce_t, self.announce_col, self.announce_max = s, dur, col, dur

    # ---- fluxo de rounds -----------------------------------------------------------
    def start_round(self):
        a, b = self.p
        a.reset(W / 2 - 230, 1)
        b.reset(W / 2 + 230, -1)
        a.energy, b.energy = max(a.energy, 25), max(b.energy, 25)
        self.parts.clear()
        self.projectiles.clear()
        self.effects = []
        self.cutin = None
        self.phase, self.phase_t = "intro", 0.0
        self.timer = float(ROUND_TIME)
        self.said_fight = False
        self.announce("ROUND %d" % self.round, WHITE, 1.2)

    def end_round(self, winner, why):
        self.phase, self.phase_t = "ko", 0.0
        self.winner_round = winner
        if winner is not None:
            self.wins[winner] += 1
            if winner == 1:
                self.perfect = False
            self.p[winner].state = "win" if self.p[winner].state != "ko" else "ko"
        self.announce(why, (255, 70, 70) if why == "K.O.!" else (255, 220, 90), 2.2)
        if why == "K.O.!":
            self.flash_a = 1.0

    def finish_match(self):
        self.phase = "matchend"
        winner = 0 if self.wins[0] >= 2 else 1
        self.match_winner = winner
        res = dict(winner=winner, stats=dict(self.stats), perfect=self.perfect)
        if self.mode == "story":
            prof = self.game.profile
            name = self.p[0].name
            if winner == 0:
                gain = 70 + 45 * self.stage + (40 if self.perfect else 0)
                old, new = prof.add_xp(name, gain)
                prof.cleared = max(prof.cleared, self.stage + 1)
                prof.save()
                res.update(xp=gain, old=old, new=new)
                if new > old:
                    self.sfx.play("level")
            else:
                gain = 20
                old, new = prof.add_xp(name, gain)
                res.update(xp=gain, old=old, new=new)
        elif self.mode in ("cpu", "mine", "raid") and winner == 0:
            gain = 25 if self.mode == "cpu" else 35
            old, new = self.game.profile.add_xp(self.p[0].name, gain)
            res.update(xp=gain, old=old, new=new)
            if new > old:
                self.sfx.play("level")
        if "xp" in res:
            res["unlocked"] = outfits_unlocked_between(self.p[0].name, res["old"], res["new"])
        self.result = res

    # ---- entrada ---------------------------------------------------------------------
    def event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if self.phase == "matchend":
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.game.fight_finished(self)
            elif e.key == pygame.K_ESCAPE:
                if self.mode in ("mine", "raid"):
                    self.game.fight_finished(self)
                else:
                    self.game.go_menu()
            return
        if e.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            return
        if self.paused:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.paused = False
            elif e.key == pygame.K_q:
                self.game.go_menu()
            return
        for i in (0, 1):
            km = self.keymaps[i]
            if e.key in km["up"]:
                self.taps[i].append("jump")
            for a in ("punch", "kick", "special", "charge", "ult"):
                if e.key in km[a]:
                    self.taps[i].append(a)

    def read_input(self, i, keys):
        if i == 1 and self.ai:
            return self._ai_inp
        km = self.keymaps[i]

        def held(n):
            return any(keys[k] for k in km[n])

        inp = dict(left=held("left"), right=held("right"), up=held("up"), down=held("down"),
                   charge=held("charge"), taps=self.taps[i])
        self.taps[i] = []
        return inp

    # ---- atualizacao ----------------------------------------------------------------
    def update(self, dt):
        if self.paused:
            return
        self.t_total += dt
        self.shake = max(0.0, self.shake - 60 * dt)
        self.flash_a = max(0.0, self.flash_a - 2.2 * dt)
        self.announce_t -= dt
        if self.cutin:
            self.cutin["t"] += dt
            for p in self.parts:
                p.update(dt * 0.1)
            for fz in self.p:
                fz.anim += dt
            if self.cutin["t"] >= self.cutin["dur"]:
                self.cutin = None
                self.taps = [[], []]
                self.shake = max(self.shake, 12)
                self.flash_a = max(self.flash_a, 0.5)
            return
        if self.hitstop > 0:
            self.hitstop -= dt
            for p in self.parts:
                p.update(dt * 0.15)
            self.parts = [p for p in self.parts if p.life > 0]
            return
        if self.phase == "matchend":
            self.step(dt, False)
            return
        scale = 0.38 if self.phase == "ko" else 1.0
        n = max(1, int(math.ceil(dt * scale / MAX_SUBSTEP)))
        sdt = dt * scale / n
        keys = pygame.key.get_pressed()
        for _ in range(n):
            self.step(sdt, True, keys)
        self.phase_t += dt
        if self.phase == "intro":
            if self.phase_t > 1.2 and not self.said_fight:
                self.said_fight = True
                self.announce("LUTAR!", (255, 220, 80), 0.9)
                self.sfx.play("ok")
            if self.phase_t > 2.1:
                self.phase, self.phase_t = "fight", 0.0
        elif self.phase == "fight":
            self.timer -= dt
            a, b = self.p
            if a.hp <= 0 and b.hp <= 0:
                self.end_round(None, "EMPATE!")
            elif b.hp <= 0:
                self.end_round(0, "K.O.!")
            elif a.hp <= 0:
                self.end_round(1, "K.O.!")
            elif self.timer <= 0:
                ra, rb = a.hp / a.maxhp, b.hp / b.maxhp
                if abs(ra - rb) < 1e-6:
                    self.end_round(None, "EMPATE!")
                else:
                    self.end_round(0 if ra > rb else 1, "TEMPO!")
        elif self.phase == "ko":
            if self.phase_t > 2.6:
                if max(self.wins) >= 2:
                    self.finish_match()
                else:
                    if self.winner_round is not None:
                        self.round += 1
                    self.start_round()

    def step(self, dt, active, keys=None):
        a, b = self.p
        if active:
            fighting = self.phase == "fight"
            empty = dict(left=False, right=False, up=False, down=False, taps=[])
            if fighting and self.ai:
                self._ai_inp = self.ai.think(dt, b, a)
            else:
                self._ai_inp = empty
            ia = self.read_input(0, keys) if fighting else empty
            ib = self.read_input(1, keys) if fighting else empty
            if not fighting:
                self.taps = [[], []]
            a.update(dt, ia, b, self)
            b.update(dt, ib, a, self)
            self.separate(a, b)
            for e in self.effects:
                e["t"] += dt
            self.effects = [e for e in self.effects if e["t"] < e["dur"]]
            for pr in self.projectiles:
                pr.update(dt, self)
                for tgt in self.p:
                    if tgt is pr.owner or pr.dead or tgt.state == "ko" or tgt.invuln > 0:
                        continue
                    if pr.rect().colliderect(tgt.hurtbox()):
                        pr.dead = True
                        tgt.take_hit(pr.owner, pr.mv, self, point=(pr.x, pr.y))
                        self.burst(pr.x, pr.y, pr.col, 16, 600, 0.4, 5)
            for i, p1 in enumerate(self.projectiles):
                for p2 in self.projectiles[i + 1:]:
                    if p1.owner is not p2.owner and not p1.dead and not p2.dead and p1.rect().colliderect(p2.rect()):
                        p1.dead = p2.dead = True
                        self.burst((p1.x + p2.x) / 2, (p1.y + p2.y) / 2, WHITE, 18, 640, 0.4, 5)
                        self.parts.append(Particle((p1.x + p2.x) / 2, (p1.y + p2.y) / 2, 0, 0, 0.35, 90, WHITE, 0, "ring"))
            self.projectiles = [p for p in self.projectiles if not p.dead]
        else:
            a.update(dt, dict(left=False, right=False, up=False, down=False, taps=[]), b, self)
            b.update(dt, dict(left=False, right=False, up=False, down=False, taps=[]), a, self)
        for p in self.parts:
            p.update(dt)
        self.parts = [p for p in self.parts if p.life > 0]

    def separate(self, a, b):
        if a.state == "ko" or b.state == "ko":
            return
        if abs(a.y - b.y) > 110:
            return
        min_d = 54 * (a.scale + b.scale) / 2
        dx = b.x - a.x
        if abs(dx) < min_d:
            push = (min_d - abs(dx)) / 2
            d = 1 if dx > 0 else (-1 if dx < 0 else a.face)
            a.x = clamp(a.x - d * push, STAGE_L, STAGE_R)
            b.x = clamp(b.x + d * push, STAGE_L, STAGE_R)

    # ---- desenho ---------------------------------------------------------------------
    def draw(self, screen):
        c = self.canvas
        cam = (self.p[0].x + self.p[1].x) / 2 - W / 2
        self.bg.draw(c, cam, self.t_total)
        order = sorted(self.p, key=lambda f: (f.state != "ko", f.y))
        for f in order:
            draw_fighter(c, f)
        self.draw_effects(c)
        for pr in self.projectiles:
            pr.draw(c)
        for p in self.parts:
            p.draw(c)
        self.bg.draw_front(c)
        self.draw_hud(c)
        if self.cutin:
            self.draw_cutin(c)
        self.draw_overlays(c)
        if self.flash_a > 0:
            self.flash_surf.set_alpha(int(150 * self.flash_a))
            c.blit(self.flash_surf, (0, 0))
        ox = oy = 0
        if self.shake > 0.5:
            ox = int(random.uniform(-1, 1) * self.shake)
            oy = int(random.uniform(-1, 1) * self.shake)
            screen.fill((0, 0, 0))
        screen.blit(c, (ox, oy))

    def draw_hud(self, c):
        for i, f in enumerate(self.p):
            left = i == 0
            x = 54 if left else W - 54 - 520
            frac = f.hp / f.maxhp
            slant_bar(c, x, 46, 520, 34, frac, (120, 255, 120) if frac > 0.5 else (255, 220, 70) if frac > 0.25 else (255, 80, 70),
                      (30, 160, 50) if frac > 0.5 else (200, 140, 20) if frac > 0.25 else (170, 20, 30),
                      anchor_right=not left, trail=f.trail / f.maxhp, trail_col=(255, 245, 235))
            slant_bar(c, x + 6, 90, 300, 14, f.energy / 100, mix(f.ch["accent"], WHITE, 0.3), shade(f.ch["accent"], 0.7),
                      anchor_right=not left, slant=10)
            if f.energy >= f.moves["special"]["cost"]:
                a = 0.6 + 0.4 * math.sin(self.t_total * 8)
                lbl = "JUTSU FINAL PRONTO!" if f.energy >= 100 else "ESPECIAL!"
                text(c, lbl, 20, (x + 322, 97), shade(f.ch["accent"], a + 0.3), "midleft")
            if f.awake > 0:
                text(c, "DESPERTAR %ds" % math.ceil(f.awake), 22, (x + (330 if left else 190), 122),
                     AWAKE_HAIR, "midleft" if left else "midright")
            nm = "%s  Nv.%d" % (f.name, f.level)
            text(c, nm, 34, (x + (6 if left else 514), 28), WHITE, "midleft" if left else "midright")
            for r in range(2):
                cx = x + (20 + r * 28 if left else 500 - r * 28)
                cy = 122
                pygame.draw.circle(c, OUT, (cx, cy), 10)
                pygame.draw.circle(c, (255, 210, 60) if r < self.wins[i] else (50, 44, 70), (cx, cy), 7)
            if f.combo >= 2:
                s = "%d HITS!" % f.combo
                text(c, s, 58 + min(f.combo, 8) * 3, (150 if left else W - 150, 250), (255, 220, 70),
                     "center", (140, 30, 20), 4)
        # cronometro
        pygame.draw.circle(c, OUT, (W // 2, 62), 42)
        pygame.draw.circle(c, (36, 30, 62), (W // 2, 62), 37)
        tcol = (255, 90, 80) if self.timer < 10 else WHITE
        text(c, "%02d" % max(0, int(math.ceil(self.timer))), 62, (W // 2, 62), tcol)
        text(c, self.bg.th["name"].upper(), 20, (W // 2, 118), (200, 190, 230))

    def draw_overlays(self, c):
        if self.announce_t > 0 and self.phase != "matchend":
            k = 1 - self.announce_t / self.announce_max
            sc = 1.0 + 0.8 * (1 - ease_out(k * 4))
            size = int(120 * sc)
            a = clamp(self.announce_t * 3, 0, 1)
            col = shade(self.announce_col, 0.4 + 0.6 * a)
            text(c, self.announce_txt, size, (W // 2, 300), col, "center", (60, 10, 30), 6)
        if self.paused:
            self.dim(c, 170)
            text(c, "PAUSADO", 110, (W // 2, 270), WHITE)
            text(c, "ENTER continuar   |   Q menu principal", 36, (W // 2, 360), (210, 210, 240))
        if self.phase == "matchend" and self.result:
            self.dim(c, 190)
            r = self.result
            if self.mode == "story":
                won = r["winner"] == 0
                text(c, "VITORIA!" if won else "DERROTA", 120, (W // 2, 170),
                     (255, 220, 80) if won else (255, 90, 90), "center", (50, 10, 20), 6)
                f = self.p[0]
                prof = self.game.profile
                xp = prof.xp.get(f.name, 0)
                lv = level_from_xp(xp)
                lo, hi = xp_for_level(lv), xp_for_level(lv + 1)
                text(c, "+%d XP" % r["xp"], 54, (W // 2, 262), (170, 230, 255))
                slant_bar(c, W // 2 - 260, 300, 520, 26, (xp - lo) / (hi - lo), (140, 200, 255), (60, 110, 220))
                text(c, "%s  Nivel %d   (%d / %d XP)" % (f.name, lv, xp - lo, hi - lo), 30, (W // 2, 354), WHITE)
                if r["new"] > r["old"]:
                    text(c, "NIVEL %d!  +6%% Vida   +4%% Dano" % r["new"], 48, (W // 2, 410),
                         (255, 230, 90) if int(self.t_total * 4) % 2 else WHITE)
                if r.get("unlocked"):
                    text(c, "NOVO UNIFORME: " + ", ".join(r["unlocked"]).upper(), 40, (W // 2, 460), (140, 255, 200))
                nxt = ("ENTER o desfecho" if self.stage >= 4 else "ENTER continuar a historia") if won else "ENTER tentar de novo"
                text(c, nxt + "    |    ESC menu", 34, (W // 2, 520), (210, 210, 240))
            else:
                w = self.p[r["winner"]]
                if self.mode in ("cpu", "mine", "raid"):
                    text(c, "VITORIA!" if r["winner"] == 0 else "DERROTA", 120, (W // 2, 230),
                         (255, 220, 80) if r["winner"] == 0 else (255, 90, 90), "center", (50, 10, 20), 6)
                else:
                    text(c, "%s VENCEU!" % w.name, 110, (W // 2, 230), w.ch["accent"], "center", (30, 10, 30), 6)
                if self.mode in ("cpu", "mine", "raid") and "xp" in r:
                    text(c, "+%d XP  (%s Nivel %d)" % (r["xp"], self.p[0].name, r["new"]), 44, (W // 2, 330), (170, 230, 255))
                    if r.get("unlocked"):
                        text(c, "NOVO UNIFORME: " + ", ".join(r["unlocked"]).upper(), 40, (W // 2, 375), (140, 255, 200))
                text(c, "ENTER voltar ao Pouso" if self.mode in ("mine", "raid") else "ENTER revanche    |    ESC menu",
                     38, (W // 2, 440), (210, 210, 240))

    @staticmethod
    def dim(c, a):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((6, 4, 16, a))
        c.blit(s, (0, 0))


# ----------------------------------------------------------------------------
# Menus
# ----------------------------------------------------------------------------
class Scene:
    def event(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, s):
        pass


class Menu(Scene):
    ITEMS = ["MODO HISTORIA", "LUTA VS MAQUINA (1P)", "1 VS 1 LOCAL (2P)", "O POUSO: FAZENDA E VILA", "CONTROLES",
             "CREDITOS", "SAIR"]

    def __init__(self, game, msg=None):
        self.game = game
        self.bg = game.get_bg(1)
        self.sel = 0
        self.t = 0.0
        self.show_controls = False
        self.show_credits = False
        self.msg = msg
        a = Fighter(ROSTER[0], 1, 250, 1, 0)
        b = Fighter(ROSTER[3], 1, W - 250, -1, 1)
        self.show = [a, b]

    def event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if self.show_controls or self.show_credits:
            self.show_controls = self.show_credits = False
            return
        if e.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.ITEMS)
            self.game.sfx.play("move")
        elif e.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.ITEMS)
            self.game.sfx.play("move")
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.game.sfx.play("ok")
            if self.sel == 0:
                self.game.go(Select(self.game, "story"))
            elif self.sel == 1:
                self.game.go(Select(self.game, "cpu"))
            elif self.sel == 2:
                self.game.go(Select(self.game, "versus"))
            elif self.sel == 3:
                farm = self.game.profile.farm
                if isinstance(farm, dict) and "day" in farm:
                    self.game.start_hub()
                else:
                    self.game.go(Select(self.game, "hub"))
            elif self.sel == 4:
                self.show_controls = True
            elif self.sel == 5:
                self.show_credits = True
            else:
                self.game.running = False
        elif e.key == pygame.K_ESCAPE:
            self.game.running = False

    def update(self, dt):
        self.t += dt
        for f in self.show:
            f.anim += dt

    def draw(self, s):
        cam = math.sin(self.t * 0.5) * 90
        self.bg.draw(s, cam, self.t)
        for f in self.show:
            draw_fighter(s, f)
        self.bg.draw_front(s)
        pulse = 0.8 + 0.2 * math.sin(self.t * 3)
        add_glow(s, (W // 2, 170), 330, (70, 30, 90))
        text(s, "CLASH", 190, (W // 2, 120), (255, int(190 * pulse), 60), "center", (90, 20, 10), 8)
        text(s, "OF LEGENDS", 98, (W // 2, 230), (240, 240, 255), "center", (40, 20, 90), 6)
        if self.show_controls:
            self.draw_controls(s)
            return
        if self.show_credits:
            self.draw_credits(s)
            return
        for i, it in enumerate(self.ITEMS):
            y = 312 + i * 46
            on = i == self.sel
            if on:
                r = pygame.Rect(0, 0, 560, 42)
                r.center = (W // 2, y)
                pygame.draw.polygon(s, (255, 190, 60), [(r.left + 14, r.top), (r.right + 14, r.top), (r.right - 14, r.bottom), (r.left - 14, r.bottom)])
                pygame.draw.polygon(s, OUT, [(r.left + 14, r.top), (r.right + 14, r.top), (r.right - 14, r.bottom), (r.left - 14, r.bottom)], 3)
            text(s, it, 42, (W // 2, y), OUT if on else (225, 220, 245), "center", None if on else (0, 0, 0))
        if self.msg:
            text(s, self.msg, 40, (W // 2, 628), (255, 230, 100))
        text(s, "W/S ou setas + ENTER     |     Finais descobertos: %d/3" % len(self.game.profile.endings),
             24, (W // 2, 694), (160, 150, 190))

    def draw_credits(self, s):
        Fight.dim(s, 215)
        text(s, "CREDITOS", 84, (W // 2, 90), (255, 200, 80))
        lines = [
            ("Jogo", "Clash of Legends  -  herois desenhados por codigo em Python", WHITE),
            ("Arte do BIGODE", '"Fighter Moustache Man" por nemezes  (OpenGameArt, CC0)', (255, 230, 120)),
            ("Arte propria", "coloque seus desenhos em personagens/  (veja LEIA-ME.txt)", (190, 190, 220)),
            ("Fonte", "fonte padrao do pygame (freesansbold)", (190, 190, 220)),
            ("Sons", "sintetizados pelo proprio jogo", (190, 190, 220)),
        ]
        for i, (a, b, col) in enumerate(lines):
            text(s, a, 28, (W // 2, 190 + i * 80), (170, 165, 200))
            text(s, b, 34, (W // 2, 222 + i * 80), col)
        text(s, "Pressione qualquer tecla", 28, (W // 2, 690), (160, 150, 190))

    def draw_controls(self, s):
        Fight.dim(s, 215)
        text(s, "CONTROLES", 84, (W // 2, 90), (255, 200, 80))
        lines = [
            ("JOGADOR 1", "A / D mover   W pular   S defender   J soco   K chute   L especial", (130, 200, 255)),
            ("(Historia)", "tambem: setas + Z soco  X chute  C especial  V chakra  B jutsu final", (160, 160, 190)),
            ("JOGADOR 2", "Setas mover/pular/defender  N soco  M chute  , especial (ou num. 1-5)", (255, 150, 130)),
            ("ESPECIAL", "gasta energia (barra colorida). Cada heroi tem um especial unico.", WHITE),
            ("DEFESA", "segure BAIXO no chao para bloquear (dano 88% menor).", WHITE),
            ("RPG", "vencer no Modo Historia da XP; cada nivel: +6% vida e +4% dano.", (255, 230, 120)),
            ("FINAL", "so existe um final: ele muda conforme o SEU jeito de lutar.", (255, 230, 120)),
            ("UNIFORME", "na selecao, Q/E troca a roupa. Novas roupas nos niveis 2, 4 e 6.", (140, 255, 200)),
            ("POUSO", "WASD andar | E plantar/regar/colher/usar | Q troca semente | ESC casa", (140, 220, 140)),
            ("CHAKRA", "segure U (P2: .) para carregar | U levando golpe = SUBSTITUICAO (30%)", (255, 200, 120)),
            ("FINAL", "I (P2: /) com 100% = JUTSU FINAL | segure U com 100% = DESPERTAR", (255, 200, 120)),
            ("GERAL", "ESC pausa  |  F11 tela cheia  |  progresso salvo em ~/.clash_of_legends.json", (190, 190, 220)),
        ]
        for i, (a, b, col) in enumerate(lines):
            text(s, a, 30, (110, 150 + i * 46), col, "midleft")
            text(s, b, 27, (290, 150 + i * 46), col if a else WHITE, "midleft")
        text(s, "Pressione qualquer tecla", 28, (W // 2, 690), (160, 150, 190))


class Select(Scene):
    DIFFS = [("FACIL", 0.30, 0), ("NORMAL", 0.55, 0), ("DIFICIL", 0.88, 1)]
    COLS, TILE, GAP, GX, GY = 6, 108, 8, 560, 128

    def __init__(self, game, mode):
        self.game = game
        self.mode = mode
        self.bg = game.get_bg(2)
        self.cur = 0
        self.picks = []            # lista de (indice do heroi, uniforme)
        self.t = 0.0
        self.diff = 1
        self.choosing_diff = False
        self.msg, self.msg_t = "", 0.0
        self.osel = [game.profile.get_outfit(c["name"]) for c in ROSTER]
        self.prev = [self.make_preview(i) for i in range(len(ROSTER))]
        self.tiles = [self.make_tile(i) for i in range(len(ROSTER))]

    def make_preview(self, i):
        ch = ROSTER[i]
        return Fighter(outfit_ch(ch, self.osel[i]), self.game.profile.level(ch["name"]), 0, 1, 0)

    def make_tile(self, i):
        f = self.prev[i]
        f.anim = 1.0
        img, ax, ay = fighter_snapshot(f)
        k = 0.52 / max(1.0, f.scale)
        img = pygame.transform.smoothscale(img, (int(img.get_width() * k), int(img.get_height() * k)))
        tile = pygame.Surface((self.TILE, self.TILE), pygame.SRCALPHA)
        tile.blit(img, (int(self.TILE / 2 - ax * k), int(self.TILE - 16 - ay * k)))
        return tile

    def locked(self, i):
        return self.game.profile.level(ROSTER[i]["name"]) < OUTFIT_LEVELS[self.osel[i]]

    def change_outfit(self, step):
        self.osel[self.cur] = (self.osel[self.cur] + step) % len(OUTFIT_LEVELS)
        self.prev[self.cur] = self.make_preview(self.cur)
        self.tiles[self.cur] = self.make_tile(self.cur)
        self.game.sfx.play("move")

    def event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        ok = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_j)
        if self.choosing_diff:
            if e.key in (pygame.K_LEFT, pygame.K_a):
                self.diff = (self.diff - 1) % len(self.DIFFS)
                self.game.sfx.play("move")
            elif e.key in (pygame.K_RIGHT, pygame.K_d):
                self.diff = (self.diff + 1) % len(self.DIFFS)
                self.game.sfx.play("move")
            elif e.key in ok:
                self.game.sfx.play("ok")
                self.game.start_cpu(self.picks[0], self.picks[1], self.diff)
            elif e.key == pygame.K_ESCAPE:
                self.choosing_diff = False
                self.picks.pop()
            return
        n = len(ROSTER)
        if e.key in (pygame.K_LEFT, pygame.K_a):
            self.cur = (self.cur - 1) % n
            self.game.sfx.play("move")
        elif e.key in (pygame.K_RIGHT, pygame.K_d):
            self.cur = (self.cur + 1) % n
            self.game.sfx.play("move")
        elif e.key in (pygame.K_UP, pygame.K_w):
            self.cur = (self.cur - self.COLS) % n if self.cur - self.COLS >= 0 else self.cur
            self.game.sfx.play("move")
        elif e.key in (pygame.K_DOWN, pygame.K_s):
            if self.cur + self.COLS < n:
                self.cur += self.COLS
            self.game.sfx.play("move")
        elif e.key in (pygame.K_e, pygame.K_TAB):
            self.change_outfit(1)
        elif e.key == pygame.K_q:
            self.change_outfit(-1)
        elif e.key in ok:
            if self.locked(self.cur):
                self.game.sfx.play("block")
                self.msg = "Uniforme bloqueado: chegue ao nivel %d com %s" % (
                    OUTFIT_LEVELS[self.osel[self.cur]], ROSTER[self.cur]["name"])
                self.msg_t = 2.5
                return
            self.game.sfx.play("ok")
            self.game.profile.set_outfit(ROSTER[self.cur]["name"], self.osel[self.cur])
            self.picks.append((self.cur, self.osel[self.cur]))
            need = 1 if self.mode in ("story", "hub") else 2
            if len(self.picks) >= need:
                if self.mode == "hub":
                    self.game.start_hub(self.picks[0])
                elif self.mode == "story":
                    self.game.begin_story(*self.picks[0])
                elif self.mode == "cpu":
                    self.choosing_diff = True
                else:
                    self.game.start_versus(self.picks[0], self.picks[1])
        elif e.key == pygame.K_ESCAPE:
            if self.picks:
                self.picks.pop()
            else:
                self.game.go_menu()

    def update(self, dt):
        self.t += dt
        self.msg_t -= dt
        self.prev[self.cur].anim += dt

    def draw(self, s):
        self.bg.draw(s, math.sin(self.t * 0.4) * 80, self.t)
        if self.mode == "story":
            who = "ESCOLHA SEU HEROI"
        elif self.mode == "hub":
            who = "QUEM CUIDA DO POUSO?"
        elif self.mode == "cpu":
            who = "SEU LUTADOR" if not self.picks else "ESCOLHA O ADVERSARIO"
        else:
            who = "JOGADOR %d: ESCOLHA" % (min(len(self.picks), 1) + 1)
        text(s, who, 64, (W // 2, 56), (255, 220, 100), "center", (60, 20, 20), 5)
        picked = [pk[0] for pk in self.picks]
        # ---- painel grande do heroi selecionado
        i = self.cur
        ch, f = ROSTER[i], self.prev[i]
        acc = f.ch["accent"]
        r = pygame.Rect(30, 104, 500, 560)
        add_glow(s, (r.centerx, r.y + 250), 260, shade(acc, 0.3))
        card = pygame.Surface(r.size, pygame.SRCALPHA)
        card.fill((16, 12, 34, 220))
        s.blit(card, r)
        pygame.draw.rect(s, acc, r, 4, border_radius=10)
        locked = self.locked(i)
        text(s, f.ch.get("outfit_name", "Classico").upper(), 26, (r.centerx, r.y + 24),
             (255, 230, 120) if not locked else (150, 145, 170))
        for k in range(len(OUTFIT_LEVELS)):
            cx = r.centerx - 27 + k * 18
            pygame.draw.circle(s, OUT, (cx, r.y + 48), 6)
            pygame.draw.circle(s, (255, 220, 90) if k == self.osel[i] else (70, 64, 96), (cx, r.y + 48), 4)
        portrait = f.parts.get("retrato")
        if portrait is not None:
            im = pygame.transform.rotozoom(portrait, 0, min(240 / portrait.get_width(), 240 / portrait.get_height()))
            s.blit(im, im.get_rect(midbottom=(r.centerx, r.y + 300)))
        else:
            f.x, f.y = r.centerx, r.y + 296
            draw_fighter(s, f, shadow=False)
        if locked:
            veil = pygame.Surface((r.w - 8, 240), pygame.SRCALPHA)
            veil.fill((10, 8, 20, 170))
            s.blit(veil, (r.x + 4, r.y + 62))
            text(s, "BLOQUEADO", 40, (r.centerx, r.y + 170), (255, 120, 120))
            text(s, "Nivel %d" % OUTFIT_LEVELS[self.osel[i]], 30, (r.centerx, r.y + 206), WHITE)
        text(s, ch["name"], 54, (r.centerx, r.y + 332), acc)
        text(s, ch["title"], 26, (r.centerx, r.y + 364), (200, 195, 225))
        text(s, "Nivel %d" % self.game.profile.level(ch["name"]), 26, (r.centerx, r.y + 390), (255, 230, 120))
        stats = [("VIDA", ch["hp"] / 135), ("VEL", ch["spd"] / 1.25), ("FORCA", ch["pow"] / 1.2)]
        for k, (nm, v) in enumerate(stats):
            yy = r.y + 414 + k * 24
            text(s, nm, 20, (r.x + 40, yy + 6), (190, 185, 215), "midleft")
            pygame.draw.rect(s, OUT, (r.x + 120, yy, 330, 13))
            pygame.draw.rect(s, acc, (r.x + 122, yy + 2, int(326 * clamp(v, 0, 1)), 9))
        text(s, "Especial: " + ch["special"]["name"], 24, (r.centerx, r.y + 500), shade(ch["special"]["col"], 1.0))
        text(s, "Jutsu final: " + ULTS.get(ch["name"], ("Golpe Final",))[0], 24, (r.centerx, r.y + 528), (255, 210, 140))
        # ---- grade de herois
        for j in range(len(ROSTER)):
            col, row = j % self.COLS, j // self.COLS
            tr = pygame.Rect(self.GX + col * (self.TILE + self.GAP), self.GY + row * (self.TILE + self.GAP), self.TILE, self.TILE)
            sel = j == self.cur
            tacc = self.prev[j].ch["accent"]
            bg = pygame.Surface(tr.size, pygame.SRCALPHA)
            bg.fill((30, 24, 60, 230) if sel else (16, 12, 34, 200))
            s.blit(bg, tr)
            s.blit(self.tiles[j], tr)
            text(s, ROSTER[j]["name"], 17, (tr.centerx, tr.bottom - 9), tacc if sel else WHITE)
            pygame.draw.rect(s, tacc if sel else (80, 70, 110), tr, 4 if sel else 2, border_radius=6)
            if j in picked:
                text(s, "P%d" % (picked.index(j) + 1), 24, (tr.x + 16, tr.y + 14), (255, 230, 90))
        if self.msg_t > 0:
            text(s, self.msg, 28, (900, 520), (255, 140, 140))
        text(s, "Setas/WASD heroi     Q/E uniforme     ENTER confirmar     ESC voltar", 26, (W // 2, 692), (190, 185, 220))
        if self.choosing_diff:
            Fight.dim(s, 200)
            text(s, "DIFICULDADE", 90, (W // 2, 230), (255, 220, 100), "center", (60, 20, 20), 5)
            for k, (nm, _, _) in enumerate(self.DIFFS):
                on = k == self.diff
                rr = pygame.Rect(0, 0, 260, 90)
                rr.center = (W // 2 + (k - 1) * 300, 380)
                pygame.draw.rect(s, (255, 190, 60) if on else (40, 34, 70), rr, border_radius=12)
                pygame.draw.rect(s, OUT, rr, 4, border_radius=12)
                text(s, nm, 48, rr.center, OUT if on else (220, 215, 240), "center", None if on else (0, 0, 0))
            text(s, "< >  escolher    ENTER lutar    ESC voltar", 28, (W // 2, 520), (200, 195, 225))
        self.bg.draw_front(s)


def wrap_text(fnt, s, width):
    out, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if fnt.size(t)[0] <= width:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def draw_bust(dst, f, pos, scale, face, dim=0):
    portrait = f.parts.get("retrato") if getattr(f, "parts", None) else None
    if portrait is not None:
        im = pygame.transform.rotozoom(portrait, 0, 330 * scale / 1.7 / portrait.get_height())
        if face < 0:
            im = pygame.transform.flip(im, True, False)
        if dim:
            im.fill((dim, dim, dim), special_flags=pygame.BLEND_RGB_SUB)
        dst.blit(im, im.get_rect(midbottom=(int(pos[0]), int(pos[1] + 24))))
        return
    if getattr(f, "frames", None):
        img, ax, ay = frame_image(f, face, scale)
        if dim:
            img = img.copy()
            img.fill((dim, dim, dim), special_flags=pygame.BLEND_RGB_SUB)
        dst.blit(img, (int(pos[0] - ax), int(pos[1] - ay)))
        return
    spr = draw_fighter_sprite(f)
    if face < 0:
        spr = pygame.transform.flip(spr, True, False)
    if dim:
        spr.fill((dim, dim, dim), special_flags=pygame.BLEND_RGB_SUB)
    w, h = spr.get_size()
    spr = pygame.transform.smoothscale(spr, (int(w * scale), int(h * scale)))
    dst.blit(spr, (int(pos[0] - OX * scale), int(pos[1] - OY * scale)))


class DialogueScene(Scene):
    """Cena de dialogo com maquina de escrever (Enter avanca, Esc pula)."""

    def __init__(self, game, lines, theme, hero, foe=None, hero_lv=1, foe_lv=1,
                 title=None, subtitle=None, on_done=None):
        self.game = game
        self.bg = game.get_bg(theme)
        self.hero, self.foe = hero, foe
        self.hf = Fighter(hero, hero_lv, 0, 1, 0)
        self.ff = Fighter(foe, foe_lv, 0, -1, 1) if foe else None
        self.lines = [(w, self.fmt(t)) for w, t in lines]
        self.idx = 0
        self.chars = 0.0
        self.t = 0.0
        self.title, self.sub = title, subtitle
        self.title_t = 2.8 if title else 0.0
        self.on_done = on_done
        self.done = False

    def fmt(self, t):
        t = t.replace("{QUOTE}", self.foe["quote"] if self.foe else "")
        t = t.replace("{H}", self.hero["name"].title())
        return t.replace("{E}", self.foe["name"].title() if self.foe else "")

    def finish(self):
        if not self.done:
            self.done = True
            if self.on_done:
                self.on_done()

    def event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if e.key == pygame.K_ESCAPE:
            self.finish()
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_j, pygame.K_z):
            if self.title_t > 0:
                self.title_t = 0.0
            elif self.chars < len(self.lines[self.idx][1]):
                self.chars = len(self.lines[self.idx][1])
            else:
                self.idx += 1
                self.chars = 0.0
                self.game.sfx.play("move")
                if self.idx >= len(self.lines):
                    self.idx = len(self.lines) - 1
                    self.finish()

    def update(self, dt):
        self.t += dt
        self.hf.anim += dt
        if self.ff:
            self.ff.anim += dt
        if self.title_t > 0:
            self.title_t -= dt
        else:
            self.chars += 62 * dt

    def draw(self, s):
        self.bg.draw(s, math.sin(self.t * 0.3) * 60, self.t)
        who, txt = self.lines[self.idx]
        if self.foe:
            draw_bust(s, self.hf, (330, 476), 1.7, 1, 0 if who == "H" else (70 if who == "E" else 35))
            draw_bust(s, self.ff, (950, 476), 1.7, -1, 0 if who == "E" else (70 if who == "H" else 35))
        else:
            draw_bust(s, self.hf, (W // 2, 476), 1.9, 1, 0 if who == "H" else 30)
        self.bg.draw_front(s)
        if self.title_t > 0:
            Fight.dim(s, 170)
            a = clamp(min(self.title_t, 2.8 - self.title_t) * 3, 0, 1)
            text(s, self.title, 84, (W // 2, 300), shade((255, 215, 90), a), "center", shade((60, 20, 20), a), 6)
            if self.sub:
                text(s, self.sub, 38, (W // 2, 380), shade((220, 215, 245), a))
            return
        box = pygame.Rect(50, 500, W - 100, 190)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((10, 8, 24, 225))
        s.blit(panel, box)
        col = self.hero["accent"] if who == "H" else (self.foe["accent"] if who == "E" and self.foe else (190, 190, 215))
        pygame.draw.rect(s, col, box, 4, border_radius=10)
        name = (self.hero["name"] if who == "H" else (self.foe["name"] if who == "E" and self.foe else "NARRADOR"))
        tag = pygame.Rect(box.x + 22, box.y - 22, 36 + len(name) * 17, 40)
        pygame.draw.rect(s, col, tag, border_radius=8)
        pygame.draw.rect(s, OUT, tag, 3, border_radius=8)
        text(s, name, 34, tag.center, OUT, "center", None)
        fnt = font(36)
        shown = txt[:int(self.chars)]
        lines = wrap_text(fnt, txt, box.w - 70)
        # desenha somente o trecho ja digitado, mantendo a quebra de linha do texto completo
        n = 0
        for i, ln in enumerate(lines):
            part = ln[:max(0, len(shown) - n)]
            n += len(ln) + 1
            if part:
                col_t = (205, 205, 225) if who == "N" else WHITE
                text(s, part, 36, (box.x + 34, box.y + 40 + i * 40), col_t, "midleft")
        if self.chars >= len(txt) and int(self.t * 3) % 2 == 0:
            text(s, "v", 30, (box.right - 36, box.bottom - 26), col)
        text(s, "ENTER avancar   |   ESC pular", 20, (box.right - 20, box.y - 14), (170, 165, 195), "midright")


class EndingSummary(Scene):
    def __init__(self, game, key, saga):
        self.game = game
        self.key = key
        self.saga = saga
        self.bg = game.get_bg(4)
        self.t = 0.0

    def event(self, e):
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
            self.game.go_menu("Obrigado por jogar! Tente outro jeito de lutar.")

    def update(self, dt):
        self.t += dt

    def draw(self, s):
        self.bg.draw(s, math.sin(self.t * 0.3) * 60, self.t)
        Fight.dim(s, 190)
        e = ENDINGS[self.key]
        text(s, "FIM", 150, (W // 2, 130), (255, 215, 90), "center", (60, 20, 20), 8)
        text(s, e["title"], 56, (W // 2, 240), WHITE)
        text(s, e["hint"], 32, (W // 2, 292), (200, 195, 230))
        sg = self.saga
        defesa = sg["blocks"] + sg["hits_taken"]
        pct = int(round(100 * sg["blocks"] / defesa)) if defesa else 0
        rows = [("Lutas perfeitas", str(sg["perfects"])), ("Derrotas", str(sg["defeats"])),
                ("Defesa (golpes bloqueados)", "%d%%" % pct), ("Maior combo", str(sg["max_combo"])),
                ("Especiais usados", str(sg["specials"])), ("Dano causado", str(int(sg["dmg_dealt"])))]
        for i, (a, b) in enumerate(rows):
            y = 360 + i * 40
            text(s, a, 32, (W // 2 - 20, y), (190, 185, 215), "midright")
            text(s, b, 34, (W // 2 + 20, y), (255, 230, 120), "midleft")
        text(s, "Finais descobertos: %d/3   (o final depende do seu jeito de lutar)" % len(self.game.profile.endings),
             28, (W // 2, 640), (170, 165, 200))
        text(s, "ENTER voltar ao menu", 30, (W // 2, 686), WHITE)
        self.bg.draw_front(s)


# ----------------------------------------------------------------------------
# O POUSO: Vila do Cla + Fazenda (modo de farmar, vista de cima)
# ----------------------------------------------------------------------------
SEASONS = ["Primavera", "Verao", "Outono", "Inverno"]
SEASON_DAYS = 28
CROPS = {
    "nabo": dict(name="Nabo Solar", season=0, days=3, sell=35, seed=15, col=(255, 214, 90)),
    "batata": dict(name="Batata de Brasa", season=0, days=5, sell=60, seed=25, col=(230, 120, 60)),
    "milho": dict(name="Milho Dourado", season=1, days=4, sell=55, seed=20, col=(255, 226, 70)),
    "melao": dict(name="Melao Trovao", season=1, days=6, sell=110, seed=45, col=(110, 200, 90)),
    "uva": dict(name="Uva Cristal", season=2, days=5, sell=80, seed=30, col=(150, 110, 230)),
    "abobora": dict(name="Abobora do Vazio", season=2, days=7, sell=140, seed=55, col=(255, 140, 40)),
}
VILLAGE_MAX = 5
VILLAGE_INFO = {"muralha": ("Muralha", 2), "torre": ("Torres", 3), "quartel": ("Quartel", 2)}
PLOT_COLS, PLOT_ROWS, PLOT_SIZE, PLOT_X, PLOT_Y = 6, 3, 66, 660, 410
FORT = pygame.Rect(40, 110, 470, 470)
GATE_Y0, GATE_Y1 = 310, 390


def new_farm():
    return dict(day=1, gold=150, ore=0, seeds={"nabo": 6}, inv={}, plots=[None] * (PLOT_COLS * PLOT_ROWS),
                village={"muralha": 1, "torre": 1, "quartel": 1}, hero=[0, 0], raids_won=0)


def season_of(day):
    return ((day - 1) // SEASON_DAYS) % 4


def village_defense(v):
    return sum(v[k] * VILLAGE_INFO[k][1] for k in VILLAGE_INFO)


def raid_power(day):
    return 4 + (day // 4) * 3


def upgrade_cost(kind, lv):
    return 90 * lv, 2 * lv


class Hub(Scene):
    def __init__(self, game, hero=None, result=None):
        self.game = game
        prof = game.profile
        if not isinstance(getattr(prof, "farm", None), dict) or "day" not in prof.farm:
            prof.farm = new_farm()
        self.st = prof.farm
        if hero is not None:
            self.st["hero"] = [int(hero[0]), int(hero[1])]
        hi, ho = self.st["hero"]
        hi = hi if 0 <= hi < len(ROSTER) else 0
        self.hero_ch = outfit_ch(ROSTER[hi], ho)
        self.avatar = Fighter(self.hero_ch, prof.level(self.hero_ch["name"]), 0, 1, 0)
        self.px, self.py = 600.0, 360.0
        self.face = 1
        self.moving = False
        self.t = 0.0
        self.clock = 6 * 60.0
        self.energy = 100.0
        self.seed_sel = 0
        self.menu = None
        self.toasts = []
        self.parts = []
        self.drone = [self.px - 50, self.py - 80]
        self.bg = self.build_bg()
        self.soldiers = [[random.uniform(120, 420), random.uniform(360, 540), random.uniform(0, 6)] for _ in range(12)]
        self.solids = [pygame.Rect(900, 100, 170, 110), pygame.Rect(1120, 270, 130, 86), pygame.Rect(150, 230, 140, 90),
                       pygame.Rect(1110, 520, 150, 70),
                       pygame.Rect(FORT.left, FORT.top, FORT.w, 16), pygame.Rect(FORT.left, FORT.bottom - 16, FORT.w, 16),
                       pygame.Rect(FORT.left, FORT.top, 16, FORT.h),
                       pygame.Rect(FORT.right - 16, FORT.top, 16, GATE_Y0 - FORT.top),
                       pygame.Rect(FORT.right - 16, GATE_Y1, 16, FORT.bottom - GATE_Y1)]
        self.spots = [dict(id="casa", pos=(985, 232), label="Casa: dormir / salvar"),
                      dict(id="loja", pos=(1185, 372), label="Mercado: vender e comprar sementes"),
                      dict(id="mina", pos=(1185, 610), label="Mina: lutar por ouro e minerio"),
                      dict(id="cla", pos=(560, 300), label="Quadro do Cla: melhorar a vila")]
        if result:
            self.apply_result(*result)
        else:
            self.toast("Bem-vindo ao Pouso! Dia %d de %s." % (self.day_in_season(), SEASONS[season_of(self.st["day"])]))
        self.save()

    # ---- estado ----
    def save(self):
        self.game.profile.save()

    def day_in_season(self):
        return (self.st["day"] - 1) % SEASON_DAYS + 1

    def toast(self, msg, col=WHITE):
        self.toasts.append([msg, 3.2, col])
        self.toasts = self.toasts[-4:]

    def season_seeds(self):
        sea = season_of(self.st["day"])
        return [k for k, c in CROPS.items() if c["season"] == sea]

    def owned_seeds(self):
        return [k for k in CROPS if self.st["seeds"].get(k, 0) > 0]

    def plot_rect(self, i):
        c, r = i % PLOT_COLS, i // PLOT_COLS
        return pygame.Rect(PLOT_X + c * PLOT_SIZE, PLOT_Y + r * PLOT_SIZE, PLOT_SIZE - 6, PLOT_SIZE - 6)

    def plot_here(self):
        for i in range(PLOT_COLS * PLOT_ROWS):
            if self.plot_rect(i).inflate(4, 4).collidepoint(self.px, self.py):
                return i
        return None

    def spot_here(self):
        best, bd = None, 70
        for sp in self.spots:
            d = math.hypot(sp["pos"][0] - self.px, sp["pos"][1] - self.py)
            if d < bd:
                best, bd = sp, d
        return best

    def spend(self, amount):
        if self.energy < amount:
            self.toast("Sem energia! Va dormir na casa.", (255, 150, 150))
            return False
        self.energy -= amount
        return True

    # ---- acoes ----
    def act(self):
        i = self.plot_here()
        if i is not None:
            self.act_plot(i)
            return
        sp = self.spot_here()
        if sp:
            self.open_menu(sp["id"])

    def act_plot(self, i):
        p = self.st["plots"][i]
        r = self.plot_rect(i)
        if p is None:
            owned = self.owned_seeds()
            if not owned:
                self.toast("Sem sementes. Compre no Mercado.", (255, 200, 140))
                return
            key = owned[self.seed_sel % len(owned)]
            if CROPS[key]["season"] != season_of(self.st["day"]):
                self.toast("%s nao cresce em %s." % (CROPS[key]["name"], SEASONS[season_of(self.st['day'])]), (255, 200, 140))
                return
            if self.spend(3):
                self.st["seeds"][key] -= 1
                self.st["plots"][i] = dict(crop=key, stage=0, watered=False, dead=False)
                self.dust(r.center, (150, 110, 70))
                self.game.sfx.play("move")
        elif p.get("dead"):
            if self.spend(1):
                self.st["plots"][i] = None
                self.toast("Planta seca removida.")
        elif p["stage"] >= CROPS[p["crop"]]["days"]:
            if self.spend(1):
                self.st["inv"][p["crop"]] = self.st["inv"].get(p["crop"], 0) + 1
                self.st["plots"][i] = None
                self.burst_fx(r.center, CROPS[p["crop"]]["col"])
                self.toast("+1 %s" % CROPS[p["crop"]]["name"], CROPS[p["crop"]]["col"])
                self.game.sfx.play("ok")
        elif not p["watered"]:
            if self.spend(2):
                p["watered"] = True
                for _ in range(10):
                    self.parts.append(Particle(r.centerx + random.uniform(-20, 20), r.top, random.uniform(-20, 20),
                                               random.uniform(60, 160), 0.4, 3, (120, 190, 255), 300, "dot"))
                self.game.sfx.play("move")
        else:
            left = CROPS[p["crop"]]["days"] - p["stage"]
            self.toast("Ja regado. Fica pronto em %d dia(s)." % left)
        self.save()

    def open_menu(self, kind):
        st = self.st
        opts = []
        if kind == "casa":
            title = "CASA"
            opts = [("Dormir (proximo dia)", self.sleep), ("Salvar e voltar ao menu", self.quit_to_menu), ("Cancelar", None)]
        elif kind == "loja":
            title = "MERCADO"
            value = sum(CROPS[k]["sell"] * n for k, n in st["inv"].items())
            opts.append(("Vender toda a colheita  (+%d ouro)" % value, self.sell_all))
            for k in self.season_seeds():
                c = CROPS[k]
                opts.append(("Comprar 1 semente de %s  (%d ouro, %d dias)" % (c["name"], c["seed"], c["days"]),
                             lambda k=k: self.buy(k, 1)))
                opts.append(("Comprar 5 sementes de %s  (%d ouro)" % (c["name"], c["seed"] * 5), lambda k=k: self.buy(k, 5)))
            if not self.season_seeds():
                opts.append(("Inverno: nada cresce. Va a mina!", None))
            opts.append(("Sair", None))
        elif kind == "mina":
            title = "MINA DAS FENDAS"
            opts = [("Explorar a mina e lutar  (25 energia)", self.enter_mine), ("Sair", None)]
        else:
            title = "QUADRO DO CLA   (defesa %d)" % village_defense(st["village"])
            for k, (nm, _) in VILLAGE_INFO.items():
                lv = st["village"][k]
                if lv >= VILLAGE_MAX:
                    opts.append(("%s Nv %d  (maximo)" % (nm, lv), None))
                else:
                    g, o = upgrade_cost(k, lv)
                    opts.append(("Melhorar %s  Nv %d -> %d   (%d ouro, %d minerio)" % (nm, lv, lv + 1, g, o),
                                 lambda k=k: self.upgrade(k)))
            nxt = 4 - (st["day"] % 4) if st["day"] % 4 else 4
            opts.append(("Proxima incursao em %d dia(s): forca %d" % (nxt, raid_power(st["day"] + nxt)), None))
            opts.append(("Sair", None))
        self.menu = dict(title=title, opts=opts, sel=0)
        self.game.sfx.play("ok")

    def sell_all(self):
        value = sum(CROPS[k]["sell"] * n for k, n in self.st["inv"].items())
        if value <= 0:
            self.toast("Nada para vender.")
            return
        self.st["gold"] += value
        self.st["inv"] = {}
        self.toast("+%d ouro!" % value, (255, 220, 90))
        self.game.sfx.play("level")

    def buy(self, key, n):
        cost = CROPS[key]["seed"] * n
        if self.st["gold"] < cost:
            self.toast("Ouro insuficiente.", (255, 150, 150))
            return
        self.st["gold"] -= cost
        self.st["seeds"][key] = self.st["seeds"].get(key, 0) + n
        self.toast("+%d semente(s) de %s" % (n, CROPS[key]["name"]))

    def upgrade(self, kind):
        lv = self.st["village"][kind]
        g, o = upgrade_cost(kind, lv)
        if self.st["gold"] < g or self.st["ore"] < o:
            self.toast("Precisa de %d ouro e %d minerio." % (g, o), (255, 150, 150))
            return
        self.st["gold"] -= g
        self.st["ore"] -= o
        self.st["village"][kind] = lv + 1
        self.toast("%s agora e Nv %d!" % (VILLAGE_INFO[kind][0], lv + 1), (140, 255, 200))
        self.game.sfx.play("level")
        if kind == "quartel":
            self.soldiers.append([random.uniform(120, 420), random.uniform(360, 540), 0.0])

    def sleep(self, fainted=False):
        st = self.st
        old_season = season_of(st["day"])
        st["day"] += 1
        sea = season_of(st["day"])
        for i, p in enumerate(st["plots"]):
            if p is None or p.get("dead"):
                continue
            if CROPS[p["crop"]]["season"] != sea:
                p["dead"] = True
                continue
            if p["watered"]:
                p["stage"] = min(CROPS[p["crop"]]["days"], p["stage"] + 1)
            p["watered"] = False
        self.clock, self.energy = 6 * 60.0, (70.0 if fainted else 100.0)
        msg = "Dia %d de %s." % (self.day_in_season(), SEASONS[sea])
        if sea != old_season:
            msg = "Nova estacao: %s! Plantas de outra estacao secaram." % SEASONS[sea]
        self.toast(("Voce desmaiou de sono... " if fainted else "Bom dia! ") + msg)
        self.save()
        if st["day"] % 4 == 0:
            self.raid()

    def raid(self):
        st = self.st
        power, defense = raid_power(st["day"]), village_defense(st["village"])
        if defense >= power:
            reward = 60 + 10 * (st["day"] // 4)
            st["gold"] += reward
            st["raids_won"] += 1
            self.menu = dict(title="INCURSAO DO VAZIO!", opts=[
                ("Sua defesa (%d) venceu a horda (%d)!  +%d ouro" % (defense, power, reward), None), ("Continuar", None)], sel=1)
            self.save()
        else:
            self.menu = dict(title="INCURSAO DO VAZIO!", opts=[
                ("A horda (%d) e mais forte que sua defesa (%d)!" % (power, defense), None),
                ("Defender a vila lutando!", self.start_raid_fight)], sel=1, locked=True)
        self.game.sfx.play("ko")

    def enemy(self, allow_frames=True, level=1, name=None):
        hero = self.hero_ch["name"]
        pool = [c for c in ROSTER if c["name"] != hero and (allow_frames or c["name"] != "BIGODE")]
        ch = outfit_ch(random.choice(pool), 2)
        if name:
            ch = dict(ch, name=name)
        return ch, level

    def hero_level(self):
        return self.game.profile.level(self.hero_ch["name"])

    def enter_mine(self):
        if not self.spend(25):
            return
        self.save()
        ch, lv = self.enemy(True, max(1, self.hero_level() - 1 + self.st["day"] // 8))
        self.game.go(Fight(self.game, self.hero_ch, ch, self.hero_level(), lv, "mine", 0, 0.45, 3))

    def start_raid_fight(self):
        self.save()
        ch, lv = self.enemy(False, self.hero_level() + self.st["day"] // 12, "INVASOR")
        self.game.go(Fight(self.game, self.hero_ch, ch, self.hero_level(), lv, "raid", 0, 0.55, 4))

    def apply_result(self, mode, won):
        st = self.st
        if mode == "mine":
            if won:
                g, o = 40 + 5 * st["day"] // 2, random.randint(2, 4)
                st["gold"] += g
                st["ore"] += o
                self.toast("Mina: +%d ouro, +%d minerio!" % (g, o), (255, 220, 90))
            else:
                self.toast("Voce fugiu da mina sem nada.", (255, 160, 160))
        elif mode == "raid":
            if won:
                g = 120 + 20 * (st["day"] // 4)
                st["gold"] += g
                st["raids_won"] += 1
                self.toast("Vila defendida! +%d ouro" % g, (140, 255, 200))
            else:
                lost = st["gold"] // 3
                st["gold"] -= lost
                st["inv"] = {}
                self.toast("Os invasores levaram %d ouro e a colheita guardada." % lost, (255, 140, 140))
        self.energy = max(30.0, self.energy)

    def quit_to_menu(self):
        self.save()
        self.game.go_menu("Seu Pouso foi salvo.")

    # ---- efeitos ----
    def dust(self, pos, col):
        for _ in range(8):
            self.parts.append(Particle(pos[0] + random.uniform(-15, 15), pos[1] + random.uniform(-8, 8),
                                       random.uniform(-60, 60), random.uniform(-80, -20), 0.4, 5, col, 200, "dot"))

    def burst_fx(self, pos, col):
        for _ in range(14):
            a = random.uniform(0, math.tau)
            self.parts.append(Particle(pos[0], pos[1], math.cos(a) * 160, math.sin(a) * 160 - 60, 0.5, 5, col, 300, "dot"))
        self.parts.append(Particle(pos[0], pos[1], 0, 0, 0.35, 40, WHITE, 0, "ring"))

    # ---- entrada ----
    def event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if self.menu:
            m = self.menu
            if e.key in (pygame.K_UP, pygame.K_w):
                m["sel"] = (m["sel"] - 1) % len(m["opts"])
                self.game.sfx.play("move")
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                m["sel"] = (m["sel"] + 1) % len(m["opts"])
                self.game.sfx.play("move")
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e, pygame.K_j):
                fn = m["opts"][m["sel"]][1]
                if fn is None and m.get("locked"):
                    return
                self.menu = None
                if fn:
                    fn()
                self.save()
            elif e.key == pygame.K_ESCAPE and not m.get("locked"):
                self.menu = None
            return
        if e.key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_j):
            self.act()
        elif e.key in (pygame.K_q, pygame.K_TAB):
            owned = self.owned_seeds()
            if owned:
                self.seed_sel = (self.seed_sel + 1) % len(owned)
                self.toast("Semente: %s" % CROPS[owned[self.seed_sel]]["name"])
        elif e.key == pygame.K_ESCAPE:
            self.open_menu("casa")

    # ---- atualizacao ----
    def update(self, dt):
        self.t += dt
        for tt in self.toasts:
            tt[1] -= dt
        self.toasts = [tt for tt in self.toasts if tt[1] > 0]
        for p in self.parts:
            p.update(dt)
        self.parts = [p for p in self.parts if p.life > 0]
        for sd in self.soldiers:
            sd[2] += dt
            sd[0] = clamp(sd[0] + math.cos(sd[2] * 0.7 + sd[1]) * 30 * dt, FORT.left + 40, FORT.right - 50)
            sd[1] = clamp(sd[1] + math.sin(sd[2] * 0.5 + sd[0] * 0.01) * 20 * dt, 350, FORT.bottom - 40)
        self.avatar.anim += dt
        if self.menu:
            return
        self.clock += dt * 4.0
        if self.clock >= 24 * 60:
            self.sleep(fainted=True)
            return
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        self.move(dx, dy, dt)
        tx, ty = self.px - 46 * self.face, self.py - 92 + math.sin(self.t * 3) * 6
        self.drone[0] += (tx - self.drone[0]) * min(1, dt * 3)
        self.drone[1] += (ty - self.drone[1]) * min(1, dt * 3)

    def move(self, dx, dy, dt):
        self.moving = bool(dx or dy)
        if not self.moving:
            self.avatar.state = "idle"
            return
        n = math.hypot(dx, dy)
        sp = 230 * dt
        if dx:
            self.face = 1 if dx > 0 else -1
        for axis, d in ((0, dx), (1, dy)):
            if not d:
                continue
            nx = self.px + (d / n * sp if axis == 0 else 0)
            ny = self.py + (d / n * sp if axis == 1 else 0)
            feet = pygame.Rect(nx - 14, ny - 10, 28, 12)
            if not any(feet.colliderect(r) for r in self.solids) and 20 < nx < W - 20 and 96 < ny < H - 8:
                self.px, self.py = nx, ny
        self.avatar.state = "walk"
        self.avatar.vx = 230 * self.face
        self.avatar.walk_phase += dt * 230 / 30.0

    # ---- desenho ----
    def build_bg(self):
        rng = random.Random(7)
        s = pygame.Surface((W, H))
        for y in range(H):
            s.fill(mix((96, 168, 72), (70, 140, 58), y / H), (0, y, W, 1))
        for _ in range(900):
            x, y = rng.randrange(W), rng.randrange(60, H)
            pygame.draw.circle(s, mix((96, 168, 72), (130, 196, 90) if rng.random() < .5 else (64, 130, 52), .6),
                               (x, y), rng.randint(3, 10))
        path = (214, 186, 130)
        for a, b in [((520, 350), (860, 350)), ((860, 350), (985, 240)), ((860, 350), (1185, 380)),
                     ((860, 350), (860, 400)), ((1060, 470), (1185, 600)), ((860, 350), (1060, 470))]:
            pygame.draw.line(s, shade(path, .85), a, b, 44)
            pygame.draw.line(s, path, a, b, 36)
            for p in (a, b):
                pygame.draw.circle(s, path, p, 18)
        for _ in range(80):
            x, y = rng.randrange(W), rng.randrange(80, H)
            if not FORT.inflate(40, 40).collidepoint(x, y) and not (600 < x < 1270 and 80 < y < 700):
                col = rng.choice([(255, 230, 120), (255, 160, 200), (255, 255, 255)])
                pygame.draw.circle(s, col, (x, y), 2)
        # cerca da fazenda
        fr = pygame.Rect(PLOT_X - 18, PLOT_Y - 18, PLOT_COLS * PLOT_SIZE + 30, PLOT_ROWS * PLOT_SIZE + 30)
        for x in range(fr.left, fr.right + 1, 24):
            for y in (fr.top, fr.bottom):
                if not (y == fr.top and 820 < x < 900):
                    pygame.draw.rect(s, (120, 80, 46), (x - 3, y - 12, 6, 18))
        pygame.draw.line(s, (150, 104, 60), (fr.left, fr.top - 6), (820, fr.top - 6), 4)
        pygame.draw.line(s, (150, 104, 60), (900, fr.top - 6), (fr.right, fr.top - 6), 4)
        pygame.draw.line(s, (150, 104, 60), (fr.left, fr.bottom - 6), (fr.right, fr.bottom - 6), 4)
        # arvores na borda
        trees = [(x, rng.randint(66, 92)) for x in range(560, W, 60)] + [(x, rng.randint(690, 715)) for x in range(0, 640, 55)]
        trees += [(rng.randint(560, 620), y) for y in range(450, 700, 60)]
        for x, y in sorted(trees, key=lambda p: p[1]):
            pygame.draw.ellipse(s, (40, 80, 36), (x - 26, y + 14, 52, 16))
            pygame.draw.rect(s, (100, 64, 40), (x - 5, y, 10, 22))
            for dx, dy, r in ((0, -18, 26), (-14, -6, 18), (14, -6, 18)):
                pygame.draw.circle(s, (36, 104, 46), (x + dx, y + dy), r + 2)
                pygame.draw.circle(s, (56, 136, 60), (x + dx, y + dy), r)
            pygame.draw.circle(s, (86, 170, 80), (x - 6, y - 26), 9)
        return s

    def draw_fort(self, s):
        v = self.st["village"]
        wall_lv, tower_lv, bar_lv = v["muralha"], v["torre"], v["quartel"]
        pygame.draw.rect(s, (110, 150, 80), FORT.inflate(-30, -30))
        stone = mix((120, 120, 130), (190, 190, 200), wall_lv / VILLAGE_MAX)
        thick = 12 + wall_lv * 3
        segs = [(FORT.left, FORT.top, FORT.w, thick), (FORT.left, FORT.bottom - thick, FORT.w, thick),
                (FORT.left, FORT.top, thick, FORT.h), (FORT.right - thick, FORT.top, thick, GATE_Y0 - FORT.top),
                (FORT.right - thick, GATE_Y1, thick, FORT.bottom - GATE_Y1)]
        for r in segs:
            rr = pygame.Rect(r)
            pygame.draw.rect(s, OUT, rr.inflate(4, 4))
            pygame.draw.rect(s, stone, rr)
            pygame.draw.rect(s, mix(stone, WHITE, .25), (rr.x, rr.y, rr.w, max(3, rr.h // 4)) if rr.w > rr.h else
                             (rr.x, rr.y, max(3, rr.w // 4), rr.h))
            if rr.w > rr.h:
                for x in range(rr.left, rr.right - 8, 18):
                    pygame.draw.rect(s, shade(stone, .8), (x, rr.top - 6, 10, 7))
            else:
                for y in range(rr.top, rr.bottom - 8, 18):
                    pygame.draw.rect(s, shade(stone, .8), (rr.left - 6, y, 7, 10))
        # portao
        pygame.draw.rect(s, (110, 72, 40), (FORT.right - thick, GATE_Y0, thick, GATE_Y1 - GATE_Y0))
        for y in range(GATE_Y0 + 6, GATE_Y1, 12):
            pygame.draw.line(s, (70, 44, 24), (FORT.right - thick, y), (FORT.right, y), 2)
        # torres
        corners = [FORT.topleft, (FORT.right, FORT.top), (FORT.left, FORT.bottom), FORT.bottomright,
                   (FORT.right, GATE_Y0 - 10)]
        for i, (x, y) in enumerate(corners[:min(5, tower_lv + 1)]):
            r = 24 + tower_lv * 2
            pygame.draw.circle(s, OUT, (x, y), r + 3)
            pygame.draw.circle(s, shade(stone, .9), (x, y), r)
            pygame.draw.polygon(s, (170, 50, 50), [(x - r, y - 6), (x + r, y - 6), (x, y - r - 28)])
            pygame.draw.polygon(s, OUT, [(x - r, y - 6), (x + r, y - 6), (x, y - r - 28)], 3)
            pygame.draw.line(s, OUT, (x, y - r - 28), (x, y - r - 46), 2)
            wave = math.sin(self.t * 4 + i) * 4
            pygame.draw.polygon(s, self.hero_ch["accent"], [(x, y - r - 46), (x + 18, y - r - 41 + wave), (x, y - r - 36)])
        # quartel
        q = pygame.Rect(150, 230, 140, 90)
        pygame.draw.rect(s, OUT, q.inflate(6, 6))
        pygame.draw.rect(s, (150, 104, 62), q)
        for x in range(q.left + 8, q.right, 16):
            pygame.draw.line(s, (120, 80, 46), (x, q.top), (x, q.bottom), 2)
        pygame.draw.polygon(s, (90, 60, 120), [(q.left - 10, q.top + 4), (q.right + 10, q.top + 4), (q.centerx, q.top - 40)])
        pygame.draw.polygon(s, OUT, [(q.left - 10, q.top + 4), (q.right + 10, q.top + 4), (q.centerx, q.top - 40)], 3)
        pygame.draw.rect(s, (70, 44, 24), (q.centerx - 14, q.bottom - 38, 28, 38))
        text(s, "QUARTEL Nv%d" % bar_lv, 20, (q.centerx, q.bottom + 14), WHITE)
        # bonecos de treino e soldados
        for x in (340, 400):
            pygame.draw.rect(s, (110, 72, 40), (x - 3, 250, 6, 40))
            pygame.draw.circle(s, (210, 180, 120), (x, 246), 12)
            pygame.draw.circle(s, OUT, (x, 246), 12, 2)
        for i, (x, y, ph) in enumerate(self.soldiers[:bar_lv * 2 + 2]):
            bob = abs(math.sin(ph * 6)) * 3
            pygame.draw.ellipse(s, (40, 70, 36), (x - 9, y + 10, 18, 6))
            pygame.draw.rect(s, OUT, (x - 7, y - 14 - bob, 14, 22), border_radius=4)
            pygame.draw.rect(s, (70, 90, 160), (x - 5, y - 12 - bob, 10, 18), border_radius=3)
            pygame.draw.circle(s, OUT, (int(x), int(y - 20 - bob)), 7)
            pygame.draw.circle(s, (230, 190, 150), (int(x), int(y - 20 - bob)), 5)
            pygame.draw.line(s, (200, 200, 210), (x + 7, y - 16 - bob), (x + 7, y - 34 - bob), 2)
        # quadro do cla
        bx, by = 560, 280
        pygame.draw.rect(s, (110, 72, 40), (bx - 3, by, 6, 30))
        pygame.draw.rect(s, OUT, (bx - 26, by - 26, 52, 32))
        pygame.draw.rect(s, (200, 160, 100), (bx - 24, by - 24, 48, 28))
        text(s, "CLA", 18, (bx, by - 10), OUT, shadow=None)

    def draw_buildings(self, s):
        # casa
        h = pygame.Rect(900, 110, 170, 100)
        pygame.draw.rect(s, OUT, h.inflate(6, 6))
        pygame.draw.rect(s, (196, 60, 52), h)
        for x in range(h.left + 10, h.right, 18):
            pygame.draw.line(s, (160, 44, 40), (x, h.top), (x, h.bottom), 2)
        roof = [(h.left - 16, h.top + 6), (h.right + 16, h.top + 6), (h.centerx, h.top - 56)]
        pygame.draw.polygon(s, (110, 70, 60), roof)
        pygame.draw.polygon(s, OUT, roof, 3)
        pygame.draw.rect(s, (90, 56, 40), (h.centerx - 16, h.bottom - 46, 32, 46))
        pygame.draw.rect(s, (255, 230, 150), (h.left + 18, h.top + 26, 28, 24))
        pygame.draw.rect(s, (255, 230, 150), (h.right - 46, h.top + 26, 28, 24))
        pygame.draw.rect(s, (90, 90, 96), (h.right - 40, h.top - 50, 18, 36))
        if int(self.t * 3) % 2 == 0 and random.random() < 0.3:
            self.parts.append(Particle(h.right - 31, h.top - 54, random.uniform(-10, 10), -40, 1.6, 9, (220, 220, 225), -5, "dot"))
        text(s, "CASA", 20, (h.centerx, h.bottom + 34), WHITE)
        # mercado
        m = pygame.Rect(1120, 280, 130, 76)
        pygame.draw.rect(s, OUT, m.inflate(6, 6))
        pygame.draw.rect(s, (170, 120, 70), m)
        for i in range(6):
            col = (230, 70, 70) if i % 2 == 0 else (250, 245, 235)
            pygame.draw.polygon(s, col, [(m.left - 8 + i * 24, m.top), (m.left + 16 + i * 24, m.top),
                                         (m.left + 16 + i * 24, m.top - 26), (m.left - 8 + i * 24, m.top - 26)])
        pygame.draw.rect(s, OUT, (m.left - 8, m.top - 26, 146, 26), 3)
        for i, k in enumerate(("abobora", "melao", "nabo", "uva")):
            pygame.draw.circle(s, CROPS[k]["col"], (m.left + 22 + i * 28, m.top + 30), 10)
            pygame.draw.circle(s, OUT, (m.left + 22 + i * 28, m.top + 30), 10, 2)
        text(s, "MERCADO", 20, (m.centerx, m.bottom + 34), WHITE)
        # mina
        cx, cy = 1185, 560
        for dx, dy, r in ((-50, 10, 38), (50, 10, 38), (0, -10, 52)):
            pygame.draw.circle(s, OUT, (cx + dx, cy + dy), r + 3)
            pygame.draw.circle(s, (130, 126, 130), (cx + dx, cy + dy), r)
            pygame.draw.circle(s, (160, 156, 160), (cx + dx - 10, cy + dy - 12), r // 2)
        pygame.draw.ellipse(s, (20, 16, 20), (cx - 28, cy + 4, 56, 56))
        pygame.draw.rect(s, (20, 16, 20), (cx - 28, cy + 30, 56, 30))
        pygame.draw.rect(s, (110, 72, 40), (cx - 34, cy, 8, 62))
        pygame.draw.rect(s, (110, 72, 40), (cx + 26, cy, 8, 62))
        pygame.draw.rect(s, (110, 72, 40), (cx - 36, cy - 4, 72, 10))
        text(s, "MINA", 22, (cx, cy - 74), (255, 230, 150))

    def draw_plots(self, s):
        for i in range(PLOT_COLS * PLOT_ROWS):
            r = self.plot_rect(i)
            p = self.st["plots"][i]
            wet = p is not None and p.get("watered")
            soil = (92, 62, 40) if wet else (140, 98, 62)
            pygame.draw.rect(s, OUT, r.inflate(4, 4), border_radius=6)
            pygame.draw.rect(s, soil, r, border_radius=5)
            for k in range(3):
                pygame.draw.line(s, shade(soil, .8), (r.left + 6, r.top + 14 + k * 16), (r.right - 6, r.top + 14 + k * 16), 3)
            if p is None:
                continue
            c = CROPS[p["crop"]]
            cx, cy = r.centerx, r.bottom - 12
            if p.get("dead"):
                pygame.draw.line(s, (120, 100, 60), (cx, cy), (cx - 6, cy - 22), 3)
                pygame.draw.line(s, (120, 100, 60), (cx, cy), (cx + 8, cy - 16), 3)
                continue
            k = p["stage"] / c["days"]
            sway = math.sin(self.t * 2 + i) * 2
            hgt = 10 + 30 * k
            pygame.draw.line(s, (50, 120, 40), (cx, cy), (cx + sway, cy - hgt), 4)
            for side in (-1, 1):
                pygame.draw.ellipse(s, (70, 160, 60), (cx + sway + side * 4 - (12 if side < 0 else 0), cy - hgt * 0.6, 12, 7))
            if k >= 1:
                for dx in (-12, 0, 12):
                    pygame.draw.circle(s, OUT, (int(cx + dx + sway), int(cy - hgt + 4)), 10)
                    pygame.draw.circle(s, c["col"], (int(cx + dx + sway), int(cy - hgt + 4)), 8)
                    pygame.draw.circle(s, mix(c["col"], WHITE, .5), (int(cx + dx + sway - 3), int(cy - hgt + 1)), 3)
                if int(self.t * 2 + i) % 3 == 0:
                    pygame.draw.circle(s, (255, 255, 200), (r.right - 8, r.top + 8), 3)

    def draw_avatar(self, s):
        self.avatar.face = self.face
        img, ax, ay = fighter_snapshot(self.avatar)
        k = 0.42
        img = pygame.transform.smoothscale(img, (int(img.get_width() * k), int(img.get_height() * k)))
        pygame.draw.ellipse(s, (40, 80, 36), (self.px - 20, self.py - 6, 40, 12))
        s.blit(img, (int(self.px - ax * k), int(self.py - ay * k)))

    def draw_drone(self, s):
        x, y = self.drone
        pygame.draw.ellipse(s, (40, 80, 36), (x - 12, self.py - 4, 24, 8))
        add_glow(s, (x, y), 34, (30, 70, 70))
        pygame.draw.circle(s, OUT, (int(x), int(y)), 15)
        pygame.draw.circle(s, (200, 220, 235), (int(x), int(y)), 13)
        pygame.draw.rect(s, OUT, (x - 10, y - 5, 20, 9), border_radius=4)
        pygame.draw.rect(s, (80, 255, 200), (x - 8, y - 3, 16, 5), border_radius=3)
        spin = math.sin(self.t * 30) * 16
        pygame.draw.line(s, OUT, (x, y - 14), (x, y - 20), 2)
        pygame.draw.line(s, (220, 230, 240), (x - spin, y - 21), (x + spin, y - 21), 3)

    def prompt(self):
        i = self.plot_here()
        if i is not None:
            p = self.st["plots"][i]
            if p is None:
                owned = self.owned_seeds()
                return "E: plantar %s" % CROPS[owned[self.seed_sel % len(owned)]]["name"] if owned else "Sem sementes: va ao Mercado"
            if p.get("dead"):
                return "E: limpar planta seca"
            if p["stage"] >= CROPS[p["crop"]]["days"]:
                return "E: colher %s" % CROPS[p["crop"]]["name"]
            return "E: regar" if not p["watered"] else "Regado. Volte amanha!"
        sp = self.spot_here()
        return ("E: " + sp["label"]) if sp else None

    def draw(self, s):
        s.blit(self.bg, (0, 0))
        self.draw_fort(s)
        self.draw_plots(s)
        self.draw_buildings(s)
        self.draw_avatar(s)
        self.draw_drone(s)
        for p in self.parts:
            p.draw(s)
        # noite
        night = clamp((self.clock - 18 * 60) / (4 * 60), 0, 1)
        if night > 0:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((10, 16, 60, int(140 * night)))
            s.blit(veil, (0, 0))
        self.draw_hud(s)
        if self.menu:
            self.draw_menu(s)

    def draw_hud(self, s):
        st = self.st
        bar = pygame.Surface((W, 56), pygame.SRCALPHA)
        bar.fill((14, 10, 28, 220))
        s.blit(bar, (0, 0))
        hh, mm = int(self.clock // 60), int(self.clock % 60) // 10 * 10
        text(s, "%s  Dia %d" % (SEASONS[season_of(st["day"])], self.day_in_season()), 30, (16, 18), (255, 230, 150), "midleft")
        text(s, "%02d:%02d" % (hh % 24, mm), 30, (16, 42), WHITE, "midleft")
        text(s, "Ouro %d" % st["gold"], 30, (300, 18), (255, 214, 80), "midleft")
        text(s, "Minerio %d" % st["ore"], 30, (300, 42), (190, 200, 220), "midleft")
        text(s, "ENERGIA", 20, (500, 16), WHITE, "midleft")
        slant_bar(s, 500, 30, 200, 16, self.energy / 100, (140, 255, 140), (40, 160, 60), slant=8)
        owned = self.owned_seeds()
        if owned:
            k = owned[self.seed_sel % len(owned)]
            text(s, "Semente (Q): %s x%d" % (CROPS[k]["name"], st["seeds"][k]), 24, (740, 18), CROPS[k]["col"], "midleft")
        else:
            text(s, "Sem sementes", 24, (740, 18), (200, 190, 220), "midleft")
        n = sum(st["inv"].values())
        text(s, "Colheita guardada: %d" % n, 24, (740, 42), WHITE, "midleft")
        text(s, "Defesa %d" % village_defense(st["village"]), 26, (W - 16, 18), (140, 255, 200), "midright")
        text(s, "ESC: casa", 20, (W - 16, 42), (180, 175, 210), "midright")
        pr = self.prompt()
        if pr and not self.menu:
            text(s, pr, 30, (W // 2, H - 26), WHITE, "center", OUT, 3)
        for i, (msg, tl, col) in enumerate(self.toasts):
            a = clamp(tl, 0, 1)
            text(s, msg, 26, (W // 2, 84 + i * 30), shade(col, 0.4 + 0.6 * a), "center", OUT, 2)

    def draw_menu(self, s):
        m = self.menu
        Fight.dim(s, 150)
        w = 860
        h = 110 + 46 * len(m["opts"])
        r = pygame.Rect(0, 0, w, h)
        r.center = (W // 2, H // 2 + 10)
        pygame.draw.rect(s, (24, 18, 44), r, border_radius=14)
        pygame.draw.rect(s, (255, 200, 90), r, 4, border_radius=14)
        text(s, m["title"], 44, (r.centerx, r.top + 40), (255, 220, 100))
        for i, (lbl, fn) in enumerate(m["opts"]):
            y = r.top + 96 + i * 46
            on = i == m["sel"]
            if on:
                pygame.draw.rect(s, (255, 190, 60), (r.left + 24, y - 20, w - 48, 40), border_radius=8)
            col = OUT if on else (WHITE if fn else (190, 185, 215))
            text(s, lbl, 28, (r.left + 44, y), col, "midleft", None if on else (0, 0, 0))
        text(s, "W/S escolher   ENTER confirmar" + ("" if m.get("locked") else "   ESC fechar"), 22,
             (r.centerx, r.bottom - 18), (180, 175, 210))


# ----------------------------------------------------------------------------
# Jogo (loop principal, transicoes)
# ----------------------------------------------------------------------------
class Game:
    def __init__(self, headless=False):
        pygame.init()
        flags = pygame.SCALED | pygame.RESIZABLE
        try:
            self.screen = pygame.display.set_mode((W, H), flags, vsync=0 if headless else 1)
        except Exception:
            self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Clash of Legends")
        self.clock = pygame.time.Clock()
        self.sfx = Sfx()
        self.profile = Profile()
        self.running = True
        self.scene = None
        self.pending = None
        self.fade = 0.0
        self.fade_dir = 0
        self.fade_surf = pygame.Surface((W, H))
        self.bgs = {}
        self.saga = None
        self.hero_idx = 0
        self.hero_ch = outfit_ch(ROSTER[0], 0)
        self.scene = Menu(self)

    def get_bg(self, idx):
        if idx not in self.bgs:
            self.bgs[idx] = Background(idx)
        return self.bgs[idx]

    # ---- transicoes ----
    def go(self, scene):
        self.pending = scene
        self.fade_dir = 1

    def go_menu(self, msg=None):
        self.go(Menu(self, msg))

    def story_order(self, hero_idx):
        if getattr(self, "story_foes", None) and getattr(self, "story_foes_hero", None) == hero_idx:
            return self.story_foes
        others = [c for i, c in enumerate(ROSTER) if i != hero_idx]
        self.story_foes = random.sample(others, len(STORY) - 1) + [BOSS]
        self.story_foes_hero = hero_idx
        return self.story_foes

    # ---- Historia ----
    def begin_story(self, hero_idx, outfit=0):
        self.hero_idx = hero_idx
        self.story_foes = None
        self.story_order(hero_idx)
        self.hero_ch = outfit_ch(ROSTER[hero_idx], outfit)
        self.saga = dict(blocks=0, hits_taken=0, hits=0, dmg_dealt=0.0, specials=0, max_combo=0,
                         perfects=0, defeats=0, fights=0)
        hero = self.hero_ch
        self.go(DialogueScene(self, PROLOGUE, 0, hero, None, self.profile.level(hero["name"]),
                              title="CLASH OF LEGENDS", subtitle="Prologo",
                              on_done=lambda: self.story_pre(0)))

    def story_foe(self, stage):
        return self.story_order(self.hero_idx)[stage]

    def story_lv_foe(self, stage):
        return 1 + stage + (1 if self.story_foe(stage).get("boss") else 0)

    def story_pre(self, stage):
        hero, foe, st = self.hero_ch, self.story_foe(stage), STORY[stage]
        self.go(DialogueScene(self, st["pre"], st["theme"], hero, foe, self.profile.level(hero["name"]),
                              self.story_lv_foe(stage), st["title"], st["sub"],
                              on_done=lambda: self.story_fight(stage)))

    def story_fight(self, stage):
        hero, foe = self.hero_ch, self.story_foe(stage)
        self.go(Fight(self, hero, foe, self.profile.level(hero["name"]), self.story_lv_foe(stage), "story",
                      stage, 0.38 + 0.14 * stage, STORY[stage]["theme"]))

    def story_post(self, stage):
        hero, foe, st = self.hero_ch, self.story_foe(stage), STORY[stage]
        nxt = self.story_ending if stage >= len(STORY) - 1 else (lambda: self.story_pre(stage + 1))
        self.go(DialogueScene(self, st["post"], st["theme"], hero, foe, self.profile.level(hero["name"]),
                              self.story_lv_foe(stage), on_done=nxt))

    def story_ending(self):
        key = decide_ending(self.saga)
        self.profile.unlock_ending(key)
        hero, foe = self.hero_ch, self.story_foe(len(STORY) - 1)
        e = ENDINGS[key]
        self.go(DialogueScene(self, e["lines"], 4, hero, foe, self.profile.level(hero["name"]),
                              self.story_lv_foe(len(STORY) - 1), e["title"], "O desfecho foi definido pelo seu jeito de lutar",
                              on_done=lambda: self.go(EndingSummary(self, key, dict(self.saga)))))

    # ---- lutas avulsas ----
    @staticmethod
    def _pair(p1, p2):
        """Mesmo heroi com a mesma roupa nos dois lados: o P2 veste a proxima, para ninguem se confundir."""
        p1 = p1 if isinstance(p1, tuple) else (int(p1), 0)
        p2 = p2 if isinstance(p2, tuple) else (int(p2), 0)
        if p1 == p2:
            p2 = (p2[0], (p2[1] + 1) % len(OUTFIT_LEVELS))
        return outfit_ch(ROSTER[p1[0]], p1[1]), outfit_ch(ROSTER[p2[0]], p2[1])

    def start_cpu(self, p1, p2, diff):
        self.cpu_args = (p1, p2, diff)
        _, ai, bonus = Select.DIFFS[diff]
        c1, c2 = self._pair(p1, p2)
        lv = self.profile.level(c1["name"])
        self.go(Fight(self, c1, c2, lv, max(1, lv + bonus), "cpu", 0, ai, random.randrange(len(THEMES))))

    def start_versus(self, p1, p2):
        self.vs = (p1, p2)
        c1, c2 = self._pair(p1, p2)
        self.go(Fight(self, c1, c2, self.profile.level(c1["name"]), self.profile.level(c2["name"]),
                      "versus", 0, 0.5, random.randrange(len(THEMES))))

    def start_hub(self, pick=None):
        self.go(Hub(self, hero=pick))

    def fight_finished(self, fight):
        if fight.mode in ("mine", "raid"):
            self.go(Hub(self, result=(fight.mode, fight.result["winner"] == 0)))
            return
        if fight.mode == "versus":
            self.start_versus(*self.vs)
            return
        if fight.mode == "cpu":
            self.start_cpu(*self.cpu_args)
            return
        sg, st = self.saga, fight.stats
        sg["fights"] += 1
        for k in ("blocks", "hits_taken", "hits", "dmg_dealt", "specials"):
            sg[k] += st[k]
        sg["max_combo"] = max(sg["max_combo"], st["max_combo"])
        if fight.result["winner"] == 0:
            if fight.perfect:
                sg["perfects"] += 1
            self.story_post(fight.stage)
        else:
            sg["defeats"] += 1
            self.story_fight(fight.stage)

    # ---- loop ----
    def run(self):
        while self.running:
            real = self.clock.tick(240) / 1000.0
            dt = min(real, 1 / 20)     # Delta Time (limitado p/ evitar saltos)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif self.fade_dir == 0:
                    self.scene.event(e)
            self.tick(dt)
        self.profile.save()
        pygame.quit()

    def tick(self, dt):
        self.scene.update(dt)
        self.scene.draw(self.screen)
        if self.fade_dir:
            self.fade += self.fade_dir * dt * 4.5
            if self.fade >= 1:
                self.fade, self.fade_dir = 1.0, -1
                self.scene, self.pending = self.pending, None
            elif self.fade <= 0:
                self.fade, self.fade_dir = 0.0, 0
        if self.fade > 0:
            self.fade_surf.set_alpha(int(255 * self.fade))
            self.screen.blit(self.fade_surf, (0, 0))
        pygame.display.flip()


def export_template(folder):
    """Gera personagens/MOLDE_PECAS.png: cada peca no tamanho certo, com as juntas marcadas."""
    os.makedirs(folder, exist_ok=True)
    surf = pygame.Surface((1400, 900))
    surf.fill((250, 250, 252))
    text(surf, "MOLDE DAS PECAS  -  desenhe por cima, tudo virado para a DIREITA  ->", 40, (700, 40), (30, 30, 40), shadow=None)
    text(surf, "Pontos vermelhos = juntas (encaixe). Braco/perna: junta de cima no TOPO, de baixo na PONTA.", 28,
         (700, 80), (90, 90, 110), shadow=None)
    items = [("cabeca", 140, 140, "pescoco embaixo"), ("tronco", 160, 220, "ombro em cima / cintura embaixo"),
             ("braco", 60, 130, "ombro / cotovelo"), ("antebraco", 56, 140, "cotovelo / mao fechada"),
             ("coxa", 68, 160, "quadril / joelho"), ("canela", 60, 164, "joelho / tornozelo"),
             ("pe", 100, 50, "tornozelo / (lado esquerdo)"), ("capa", 120, 160, "presa no ombro / (canto direito)")]
    x = 40
    for name, w, h, note in items:
        r = pygame.Rect(x, 150, w, h)
        pygame.draw.rect(surf, (200, 205, 220), r)
        pygame.draw.rect(surf, (40, 40, 60), r, 3)
        if name in ("braco", "antebraco", "coxa", "canela", "tronco"):
            for yy in (r.top + 6, r.bottom - 6):
                pygame.draw.circle(surf, (230, 40, 40), (r.centerx, yy), 7)
        elif name == "cabeca":
            pygame.draw.circle(surf, (230, 40, 40), (r.centerx, r.bottom - 6), 7)
        elif name == "pe":
            pygame.draw.circle(surf, (230, 40, 40), (r.left + 22, r.top + 12), 7)
        else:
            pygame.draw.circle(surf, (230, 40, 40), (r.right - 8, r.top + 8), 7)
        text(surf, name + ".png", 30, (r.centerx, 400), (30, 30, 40), shadow=None)
        text(surf, "%dx%d" % (w, h), 24, (r.centerx, 425), (90, 90, 110), shadow=None)
        for i, part in enumerate(note.split(" / ")):
            text(surf, part, 20, (r.centerx, 450 + i * 20), (120, 120, 140), shadow=None)
        x += max(w, 120) + 40
    r = pygame.Rect(40, 540, 300, 300)
    pygame.draw.rect(surf, (200, 205, 220), r)
    pygame.draw.rect(surf, (40, 40, 60), r, 3)
    text(surf, "retrato.png (600x600)", 30, (r.centerx, r.centery - 10), (30, 30, 40), shadow=None)
    text(surf, "busto para selecao e dialogos", 22, (r.centerx, r.centery + 20), (90, 90, 110), shadow=None)
    lines = ["COMO USAR",
             "1. Crie a pasta personagens/zeno/ (ou lyra, pixelion, sombra, brasa, malakar).",
             "2. Salve as pecas em PNG com os nomes acima. Fundo transparente ou verde puro (#00FF00).",
             "3. Pode faltar peca: o que faltar o jogo desenha sozinho.",
             "4. Roupa alternativa: personagens/zeno/uniforme2/ (ate uniforme4) com so as pecas que mudam.",
             "5. Pode desenhar maior (o dobro): o jogo ajusta o tamanho pelo esqueleto."]
    for i, ln in enumerate(lines):
        text(surf, ln, 30 if i == 0 else 26, (390, 560 + i * 40), (30, 30, 40) if i == 0 else (60, 60, 80), "midleft", None)
    path = os.path.join(folder, "MOLDE_PECAS.png")
    pygame.image.save(surf, path)
    return path


def main():
    if "--molde" in sys.argv:
        pygame.init()
        print("Molde salvo em:", export_template(PARTS_DIR))
        return
    Game().run()


if __name__ == "__main__":
    main()
