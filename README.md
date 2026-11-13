# J<div align="center">

# ⚔️ CLASH OF LEGENDS

**RPG de luta 2D feito em Python, inspirado em animes shonen e nos jogos de luta clássicos.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5%2B-2E8B57)
![Plataformas](https://img.shields.io/badge/Windows%20%7C%20Linux%20%7C%20macOS-suportado-555555)
![Heróis](https://img.shields.io/badge/her%C3%B3is-17-E25822)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-F5A623)

Criado por **[Allysson](https://github.com/AllyssonM)**

![Tela de seleção de heróis](docs/selecao.png)

</div>

---

## 📖 Sobre o jogo

Em **Ardhen**, tudo vive do **Éter**, a luz que pinga do Sol de Vidro, uma estrela rachada no céu.
Mas o Sol está secando, e o Conclave tem uma resposta pronta: a **Colheita**. A cada século, uma Terra inteira é sacrificada para recarregá-lo.

Escolha o seu herói e descubra a verdade por trás da Colheita: lute, farme, fortaleça a sua vila
e decida, **com o seu jeito de lutar**, como essa história termina.

---

## ✨ Destaques

- 🥋 **17 heróis originais**, cada um com atributos, especial, jutsu final e **4 uniformes** desbloqueáveis.
- 💥 **Combate de verdade:** golpes com fases (antecipação, acerto e recuperação), hitboxes retangulares, combos, defesa, hit-stop e tremor de tela.
- 🌀 **Mecânicas de anime:**
  - **Carregar chakra:** segure para encher a barra de energia.
  - **Substituição:** some numa nuvem de fumaça e reaparece atrás do inimigo.
  - **Jutsu final:** cena cinematográfica e golpe gigante de 5 acertos.
  - **Despertar:** transformação com aura e cabelo brilhante (+25% de dano por 12 segundos).
- 📜 **Modo História:** prólogo e 5 atos com diálogos. Existe **um único final**, e ele muda conforme o seu estilo de luta.
- 🌾 **O Pouso:** fazenda com 4 estações, mercado, mina com lutas e uma vila do clã que sofre incursões.
- 📈 **RPG:** XP, níveis (+6% de vida e +4% de dano por nível), uniformes liberados por nível e progresso salvo automaticamente.
- 🎨 **Tudo feito em código:** personagens com esqueleto animado, cenários com paralaxe, partículas e **sons sintetizados** pelo próprio jogo.
- 🖌️ **Aceita a sua arte:** coloque PNGs na pasta `personagens/` e o jogo usa no lugar do desenho padrão.

| Jutsu final | Despertar |
|:---:|:---:|
| ![Jutsu final](docs/jutsu_final.png) | ![Despertar](docs/despertar.png) |

| Cena cinematográfica | Modo História |
|:---:|:---:|
| ![Cena do jutsu final](docs/cutscene.png) | ![Diálogo do Modo História](docs/dialogo.png) |

---

## 🎮 Modos de jogo

| Modo | Descrição |
|---|---|
| **Modo História** | 5 atos contra rivais sorteados e o chefe **Malakar**; 3 finais possíveis |
| **Luta vs Máquina** | 1 jogador, com dificuldade Fácil, Normal ou Difícil |
| **1 vs 1 local** | 2 jogadores no mesmo teclado |
| **O Pouso** | Fazenda e Vila do Clã, para farmar ouro, minério e XP |

### 🏆 Os três finais

| Como você jogou | Final |
|---|---|
| Perdeu 3 lutas ou mais | **O Último Amanhecer** |
| Bloqueou 28% ou mais dos golpes, ou venceu 3 lutas sem perder round | **O Ciclo Quebrado** |
| Venceu só na força bruta | **O Novo Conclave** |

---

## 🦸 Heróis

| Herói | Título | Especial | Jutsu final |
|---|---|---|---|
| **Zeno** | O Guerreiro Solar | Bola Solar | Supernova Solar |
| **Lyra** | Arqueira do Trovão | Flecha Trovão | Chuva de Relâmpagos |
| **Pixelion** | Sentinela Digital | Pixel Burst | Protocolo Ômega |
| **Sombra** | Ninja do Eclipse | Investida Sombria | Clones do Eclipse |
| **Brasa** | Gigante Vulcânico | Terremoto | Erupção Titânica |
| **Bigode** | Mestre do Punho de Rua | Investida do Bigode | Mil Socos do Bigode |
| **Kaze** | Ninja do Vendaval | Lâmina de Vento | Tempestade de Clones |
| **Toran** | Punho Estelar | Cometa | Cometa Estelar |
| **Varn** | Príncipe Rubro | Investida Carmesim | Ruína Carmesim |
| **Kairo** | O Herdeiro | Esfera do Herdeiro | Onda do Herdeiro |
| **Rei** | Lâmina do Eclipse | Corte Relâmpago | Trovão do Eclipse |
| **Orin** | Irmão da Névoa | Névoa Viva | Ilusão da Névoa |
| **Morgran** | O Primeiro Lorde | Raízes Ancestrais | Floresta Ancestral |
| **Pip** | O Rastreador | Bote do Instinto | Fúria Selvagem |
| **Nix** | Herdeiro das Sombras | Garras de Trovão | Dança das Garras |
| **Gram** | O Sem-Grimório | Golpe de Pedra | Rocha Devoradora |
| **Elian** | Rival do Vento | Rajada Cortante | Furacão Celeste |

**Chefe final:** **Malakar**, o Imperador do Vazio, com o jutsu *Vazio Absoluto*.

Cada herói tem **4 uniformes**, liberados nos níveis **1, 2, 4 e 6**. O uniforme lendário vem com ombreiras e aura.

---

## 🌾 O Pouso: Fazenda e Vila do Clã

![O Pouso](docs/pouso.png)

- **Fazenda:** 18 canteiros para plantar, regar e colher.
- **Estações:** 4 estações de 28 dias. O que é de outra estação seca.
- **Culturas:** Nabo Solar, Batata de Brasa, Milho Dourado, Melão Trovão, Uva Cristal e Abóbora do Vazio.
- **Mercado:** vende a colheita e compra sementes.
- **Mina das Fendas:** lutas que rendem ouro e minério.
- **Quadro do Clã:** melhora a Muralha, as Torres e o Quartel.
- **Incursões:** a cada 4 dias. Se a defesa da vila for maior que a força da horda, você vence sozinho; se não, luta para defender.

---

## 🚀 Como instalar e jogar

### 1. Baixe o jogo
Clique no botão verde **Code** desta página → **Download ZIP** e descompacte.
Ou, se você usa Git, copie o endereço que aparece em **Code** e rode `git clone` com ele.

### 2. Instale o Python e a biblioteca
- **Python 3.10 ou mais novo:** baixe em [python.org](https://www.python.org/downloads/). No Windows, marque **"Add Python to PATH"** na instalação.
- **pygame-ce:**

```bash
pip install pygame-ce
```

> Use **pygame-ce**, e não o `pygame` comum: ele tem versão pronta para todas as versões do Python, inclusive a 3.14. Não instale os dois juntos.

### 3. Jogue

```bash
python clash_of_legends.py
```

No Windows, use `py clash_of_legends.py` ou dê dois cliques em **`JOGAR.bat`**.

<details>
<summary><b>Problemas comuns</b></summary>

| Problema | Solução |
|---|---|
| `python` não é reconhecido no Windows | Use `py` no lugar de `python` |
| Erro ao instalar o `pygame` | Instale o `pygame-ce` no lugar dele |
| `can't open file 'clash_of_legends.py'` | Você não está na pasta do jogo. Entre nela com `cd` (dica: `dir` mostra os arquivos da pasta) |
| `No module named 'pygame'` no PyCharm | Instale o `pygame-ce` pelo Terminal do PyCharm ou em Settings → Python Interpreter |

</details>

---

## 🕹️ Controles

### Luta
| Ação | Jogador 1 | Jogador 2 |
|---|:---:|:---:|
| Mover | A / D | ← / → |
| Pular | W | ↑ |
| Defender | S | ↓ |
| Soco | J | N |
| Chute | K | M |
| Especial | L | , |
| Carregar chakra (segure) | U | . |
| Jutsu final (barra em 100%) | I | / |

- **No Modo História**, o Jogador 1 também pode usar as setas + Z, X, C, V e B.
- **O Jogador 2** também pode usar o teclado numérico, de 1 a 5.
- **Substituição:** aperte chakra enquanto leva um golpe (gasta 30% da energia).
- **Despertar:** segure chakra com a barra em 100%.

### Menus e Pouso
| Ação | Tecla |
|---|---|
| Escolher herói | Setas / WASD |
| Trocar uniforme | Q / E |
| Confirmar | Enter |
| Voltar / Pausar | Esc |
| Tela cheia | F11 |
| Andar no Pouso | WASD / setas |
| Usar (plantar, regar, colher, lojas) | E |
| Trocar semente | Q |

---

## 🖌️ Coloque a sua própria arte

A pasta `personagens/` aceita dois tipos de arte. As instruções completas estão em `personagens/LEIA-ME.txt`.

1. **Peças do corpo** (`cabeca.png`, `tronco.png`, `braco.png`...): o esqueleto do jogo anima tudo sozinho.
2. **Quadros de animação** (`quadros/parado/`, `quadros/soco/`...): para personagens já desenhados pose a pose, como o Bigode.

Para gerar um molde com o tamanho de cada peça:

```bash
python clash_of_legends.py --molde
```

---

## 🗂️ Estrutura do projeto

```
├── clash_of_legends.py      # o jogo inteiro, em um único arquivo
├── personagens/             # arte opcional dos heróis, molde e instruções
├── docs/                    # capturas de tela deste README
├── HISTORIA_E_DESIGN.md     # mundo, história e planejamento do jogo
├── requirements.txt         # dependências (pygame-ce)
├── JOGAR.bat                # atalho para Windows
└── jogar.sh                 # atalho para Linux/macOS
```

O progresso fica salvo em `~/.clash_of_legends.json`, na pasta do seu usuário.

---

## 🛣️ Próximos passos

- [ ] Arte desenhada à mão para todos os heróis
- [ ] Trilha sonora
- [ ] Modo torneio e arena para 4 jogadores
- [ ] Mais atos no Modo História
- [ ] Suporte a controle (gamepad)

---

## 🙏 Créditos

- **Ideia, história e direção:** [Allysson](https://github.com/AllyssonM).
- **Arte do herói Bigode:** *"Fighter Moustache Man"*, por **nemezes**, no [OpenGameArt](https://opengameart.org/node/79292), com licença **CC0** (domínio público).
- **Biblioteca:** [pygame-ce](https://pyga.me/).
- **Personagens e história:** todos são originais, criados para este jogo.

<div align="center">

Se você curtiu o projeto, deixe uma ⭐ no repositório!

</div>
