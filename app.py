"""
Tem na Feira – App completo em Streamlit
Funcionalidades:
  - Listagem e filtros de feiras livres de SP
  - Geolocalização: botão "Como Chegar" via Google Maps
  - Barracas com contato WhatsApp
  - Carrinho de pedidos
  - Dashboard de uso (SQLite)
  - Previsão de demanda (Prophet / fallback linear)
"""

import streamlit as st
import sqlite3
import pandas as pd
import random
from datetime import datetime, timedelta
from urllib.parse import quote

# ─── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tem na Feira",
    page_icon="🥬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── ESTILOS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');
  html, body, [class*="css"] { font-family: 'Nunito', sans-serif; }

  .main-header {
    background: linear-gradient(135deg, #1e6b35, #2d8c47);
    padding: 28px 32px 20px;
    border-radius: 16px;
    margin-bottom: 24px;
    color: white;
  }
  .main-header h1 { font-size: 2.4rem; font-weight: 900; margin: 0; }
  .main-header p  { opacity: .8; margin: 6px 0 0; font-size: 1rem; }

  .feira-card {
    background: white;
    border-radius: 16px;
    border: 1px solid #e8e4dc;
    box-shadow: 0 2px 12px rgba(30,107,53,.08);
    padding: 20px;
    margin-bottom: 16px;
    transition: box-shadow .2s;
  }
  .feira-card:hover { box-shadow: 0 8px 28px rgba(30,107,53,.15); }
  .feira-nome  { font-size: 1.2rem; font-weight: 900; color: #1c1c1c; }
  .feira-bairro { font-size: .85rem; font-weight: 700; color: #2d8c47; text-transform: uppercase; margin: 3px 0 10px; }

  .pill {
    display: inline-block;
    padding: 4px 12px; border-radius: 20px;
    font-size: .78rem; font-weight: 700; margin: 2px;
  }
  .pill-verde  { background: #edf7f0; color: #1e6b35; border: 1px solid rgba(30,107,53,.2); }
  .pill-amarelo { background: #fff8dc; color: #7a5c00; border: 1px solid rgba(245,200,66,.4); }
  .pill-laranja { background: #fff3ec; color: #8a3800; border: 1px solid rgba(232,114,42,.3); }

  .barraca-card {
    background: #f0f7f2;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
    border: 1px solid rgba(30,107,53,.15);
  }
  .barraca-nome { font-weight: 800; font-size: 1rem; color: #1c1c1c; }
  .barraca-feirante { font-size: .82rem; color: #5a5a5a; margin: 2px 0 6px; }

  .metric-card {
    background: white;
    border-radius: 14px;
    padding: 20px;
    text-align: center;
    border: 1px solid #e8e4dc;
    box-shadow: 0 2px 10px rgba(0,0,0,.05);
  }
  .metric-num  { font-size: 2rem; font-weight: 900; color: #1e6b35; }
  .metric-label { font-size: .82rem; color: #5a5a5a; text-transform: uppercase; letter-spacing: .06em; }

  div[data-testid="stButton"] > button {
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-family: 'Nunito', sans-serif !important;
  }
  .stSelectbox label, .stTextInput label, .stMultiSelect label {
    font-weight: 700 !important; font-size: .82rem !important;
    text-transform: uppercase; letter-spacing: .06em; color: #5a5a5a !important;
  }
  footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── BANCO DE DADOS ────────────────────────────────────────────────────────────
DB = "tem_na_feira.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        DATETIME DEFAULT CURRENT_TIMESTAMP,
            tipo      TEXT,   -- 'busca','clique_feira','clique_barraca','pedido','como_chegar'
            feira     TEXT,
            barraca   TEXT,
            produto   TEXT,
            bairro    TEXT,
            dia       TEXT,
            valor     REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        DATETIME DEFAULT CURRENT_TIMESTAMP,
            cliente   TEXT,
            endereco  TEXT,
            itens     TEXT,
            total     REAL,
            feira     TEXT
        )
    """)
    conn.commit()
    conn.close()

def registrar(tipo, feira="", barraca="", produto="", bairro="", dia="", valor=0.0):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO eventos (tipo,feira,barraca,produto,bairro,dia,valor) VALUES (?,?,?,?,?,?,?)",
        (tipo, feira, barraca, produto, bairro, dia, valor)
    )
    conn.commit()
    conn.close()

def salvar_pedido(cliente, endereco, itens, total, feira):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO pedidos (cliente,endereco,itens,total,feira) VALUES (?,?,?,?,?)",
        (cliente, endereco, str(itens), total, feira)
    )
    conn.commit()
    conn.close()

def carregar_eventos():
    conn = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM eventos", conn, parse_dates=["ts"])
    conn.close()
    return df

def carregar_pedidos():
    conn = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM pedidos", conn, parse_dates=["ts"])
    conn.close()
    return df

init_db()

# ─── DADOS DAS FEIRAS ──────────────────────────────────────────────────────────
FEIRAS = [
    {
        "id": 1, "nome": "Feira da Lapa", "bairro": "Lapa",
        "dia": "Sábado", "hora": "06h–12h", "turno": "Manhã",
        "endereco": "R. Catão, 612 – Lapa, São Paulo",
        "lat": -23.5229, "lon": -46.7017,
        "barracas": [
            {"nome":"Hortifrúti do Seu Zé","feirante":"José Oliveira","tipo":"Verduras","emoji":"🥬","produtos":["Alface","Rúcula","Cenoura","Beterraba"],"whatsapp":"5511991110001","preco":8.0},
            {"nome":"Frutas do Nordeste","feirante":"Maria das Graças","tipo":"Frutas","emoji":"🍋","produtos":["Manga","Cajá","Jaca","Graviola"],"whatsapp":"5511991110002","preco":12.0},
            {"nome":"Ovos Caipira Dona Ana","feirante":"Ana Souza","tipo":"Ovos","emoji":"🥚","produtos":["Ovos caipira","Manteiga","Nata"],"whatsapp":"5511991110003","preco":18.0},
            {"nome":"Mel e Própolis","feirante":"Pedro Alves","tipo":"Mel","emoji":"🍯","produtos":["Mel puro","Própolis","Pólen"],"whatsapp":"5511991110004","preco":35.0},
            {"nome":"Queijaria Mineira","feirante":"Carlos Minas","tipo":"Queijos","emoji":"🧀","produtos":["Queijo minas","Ricota","Mozzarella"],"whatsapp":"5511991110005","preco":22.0},
        ]
    },
    {
        "id": 2, "nome": "Feira de Pinheiros", "bairro": "Pinheiros",
        "dia": "Sábado", "hora": "07h–13h", "turno": "Manhã",
        "endereco": "R. Benedito Calixto – Pinheiros, São Paulo",
        "lat": -23.5632, "lon": -46.6814,
        "barracas": [
            {"nome":"Orgânicos Família Tanaka","feirante":"Kenji Tanaka","tipo":"Orgânicos","emoji":"🌱","produtos":["Tomate orgânico","Abobrinha","Pepino","Pimentão"],"whatsapp":"5511992220001","preco":15.0},
            {"nome":"Peixaria Mar Azul","feirante":"Raimundo Costa","tipo":"Pescados","emoji":"🐟","produtos":["Tilápia","Salmão","Camarão","Polvo"],"whatsapp":"5511992220002","preco":45.0},
            {"nome":"Flores Serra Gaúcha","feirante":"Fernanda Luz","tipo":"Flores","emoji":"💐","produtos":["Rosas","Girassóis","Orquídeas","Tulipas"],"whatsapp":"5511992220003","preco":25.0},
            {"nome":"Especiarias do Oriente","feirante":"Ibrahim Santos","tipo":"Temperos","emoji":"🌶️","produtos":["Açafrão","Curry","Za'atar","Cominho"],"whatsapp":"5511992220004","preco":20.0},
        ]
    },
    {
        "id": 3, "nome": "Feira da Liberdade", "bairro": "Liberdade",
        "dia": "Domingo", "hora": "10h–17h", "turno": "Tarde",
        "endereco": "Pça. da Liberdade – Liberdade, São Paulo",
        "lat": -23.5595, "lon": -46.6333,
        "barracas": [
            {"nome":"Sushi & Temaki Hanami","feirante":"Yuki Nakamura","tipo":"Japonesa","emoji":"🍱","produtos":["Sushi","Temaki","Onigiri","Yakisoba"],"whatsapp":"5511993330001","preco":32.0},
            {"nome":"Mochi e Doces","feirante":"Hana Watanabe","tipo":"Confeitaria","emoji":"🍡","produtos":["Mochi","Daifuku","Dorayaki"],"whatsapp":"5511993330002","preco":18.0},
            {"nome":"Temperos Yamamoto","feirante":"Ken Yamamoto","tipo":"Temperos","emoji":"🧉","produtos":["Missô","Shoyu artesanal","Dashi"],"whatsapp":"5511993330003","preco":28.0},
            {"nome":"Hortaliças Família Ito","feirante":"Shiro Ito","tipo":"Hortaliças","emoji":"🥬","produtos":["Nabo","Rabanete","Gengibre","Cebolinha"],"whatsapp":"5511993330004","preco":10.0},
        ]
    },
    {
        "id": 4, "nome": "Feira da Vila Madalena", "bairro": "Vila Madalena",
        "dia": "Sábado", "hora": "07h–13h", "turno": "Manhã",
        "endereco": "R. Harmonia – Vila Madalena, São Paulo",
        "lat": -23.5505, "lon": -46.6922,
        "barracas": [
            {"nome":"Pão Artesanal da Vila","feirante":"Bruno Padeiro","tipo":"Padaria","emoji":"🍞","produtos":["Sourdough","Focaccia","Brioche","Integral"],"whatsapp":"5511994440001","preco":28.0},
            {"nome":"Vinhos Naturais","feirante":"Diego Bebidas","tipo":"Bebidas","emoji":"🍷","produtos":["Vinho natural","Cerveja artesanal","Kombucha"],"whatsapp":"5511994440002","preco":55.0},
            {"nome":"Frutas Exóticas","feirante":"Roberto Tropical","tipo":"Frutas","emoji":"🍍","produtos":["Pitaya","Rambutan","Mangostão","Cupuaçu"],"whatsapp":"5511994440003","preco":20.0},
            {"nome":"Queijos Canastra","feirante":"Simone Queijos","tipo":"Queijaria","emoji":"🧀","produtos":["Canastra curado","Coalho defumado","Brie artesanal"],"whatsapp":"5511994440004","preco":42.0},
        ]
    },
    {
        "id": 5, "nome": "Feira do Pacaembu", "bairro": "Pacaembu",
        "dia": "Domingo", "hora": "06h–12h", "turno": "Manhã",
        "endereco": "Pça. Charles Miller – Pacaembu, São Paulo",
        "lat": -23.5355, "lon": -46.6630,
        "barracas": [
            {"nome":"Frango Caipira","feirante":"Jair Frango","tipo":"Aves","emoji":"🐔","produtos":["Frango inteiro","Cortes","Ovos caipira"],"whatsapp":"5511995550001","preco":38.0},
            {"nome":"Mel Sítio Verde","feirante":"Benedito","tipo":"Apicultura","emoji":"🍯","produtos":["Mel eucalipto","Mel silvestre","Geleia real"],"whatsapp":"5511995550002","preco":42.0},
            {"nome":"Legumes da Roça","feirante":"Toninho","tipo":"Legumes","emoji":"🥕","produtos":["Batata doce","Mandioca","Inhame","Cará"],"whatsapp":"5511995550003","preco":9.0},
        ]
    },
    {
        "id": 6, "nome": "Feira Noturna do Brás", "bairro": "Brás",
        "dia": "Sexta-feira", "hora": "18h–22h", "turno": "Noite",
        "endereco": "R. Oriente, 600 – Brás, São Paulo",
        "lat": -23.5441, "lon": -46.6197,
        "barracas": [
            {"nome":"Ervas da Vó","feirante":"Tereza","tipo":"Ervas","emoji":"🌿","produtos":["Alecrim","Manjericão","Tomilho","Sálvia"],"whatsapp":"5511996660001","preco":6.0},
            {"nome":"Frios Silva","feirante":"Paulo Silva","tipo":"Embutidos","emoji":"🥩","produtos":["Salame","Copa","Presunto","Linguiça"],"whatsapp":"5511996660002","preco":32.0},
            {"nome":"Laticínios Fazenda","feirante":"Rosa Leiteira","tipo":"Laticínios","emoji":"🥛","produtos":["Leite fresco","Iogurte","Manteiga"],"whatsapp":"5511996660003","preco":15.0},
            {"nome":"Frutas da Estação","feirante":"Clodoaldo","tipo":"Frutas","emoji":"🍌","produtos":["Banana","Laranja","Abacaxi","Melancia"],"whatsapp":"5511996660004","preco":11.0},
        ]
    },
    {
        "id": 7, "nome": "Feira da Aclimação", "bairro": "Aclimação",
        "dia": "Terça-feira", "hora": "06h–12h", "turno": "Manhã",
        "endereco": "Pça. Silvio Romero – Aclimação, São Paulo",
        "lat": -23.5663, "lon": -46.6344,
        "barracas": [
            {"nome":"Verduras Hidropônicas","feirante":"Marcos Bio","tipo":"Hidropônico","emoji":"🌱","produtos":["Alface hidro","Rúcula","Agrião","Manjericão"],"whatsapp":"5511997770001","preco":12.0},
            {"nome":"Ervas Medicinais","feirante":"Conceição","tipo":"Plantas","emoji":"🌼","produtos":["Camomila","Hortelã","Boldo","Calêndula"],"whatsapp":"5511997770002","preco":8.0},
        ]
    },
    {
        "id": 8, "nome": "Feira do Ibirapuera", "bairro": "Ibirapuera",
        "dia": "Domingo", "hora": "08h–14h", "turno": "Manhã",
        "endereco": "Pça. Gal. Gentil Falcão – Ibirapuera, São Paulo",
        "lat": -23.5874, "lon": -46.6576,
        "barracas": [
            {"nome":"Orgânicos Verde Vida","feirante":"Patrícia","tipo":"Orgânicos","emoji":"🥦","produtos":["Cenoura orgânica","Beterraba","Tomate","Abobrinha"],"whatsapp":"5511998880001","preco":16.0},
            {"nome":"Sucos Fruta Fresca","feirante":"Claudinho","tipo":"Sucos","emoji":"🥤","produtos":["Laranja","Açaí","Caldo de cana","Vitamina"],"whatsapp":"5511998880002","preco":12.0},
            {"nome":"Pão Levain","feirante":"Alice","tipo":"Padaria","emoji":"🍞","produtos":["Centeio","Integral","Baguete","Challah"],"whatsapp":"5511998880003","preco":30.0},
            {"nome":"Mel do Cerrado","feirante":"Wander","tipo":"Mel","emoji":"🍯","produtos":["Mel cerrado","Geleia jabuticaba","Geleia goiaba"],"whatsapp":"5511998880004","preco":38.0},
        ]
    },
]

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
if "pagina"       not in st.session_state: st.session_state.pagina       = "feiras"
if "feira_atual"  not in st.session_state: st.session_state.feira_atual  = None
if "carrinho"     not in st.session_state: st.session_state.carrinho     = []

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def maps_url(endereco):
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(endereco)}"

def wa_url(numero, msg):
    return f"https://wa.me/{numero}?text={quote(msg)}"

def total_carrinho():
    return sum(i["preco"] for i in st.session_state.carrinho)

def seed_dados_demo():
    """Insere dados históricos fictícios para demonstrar os relatórios."""
    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    conn.close()
    if count > 0:
        return
    produtos_demo = ["Alface","Rúcula","Manga","Tomate","Ovos","Mel","Pão","Sushi","Banana","Cenoura"]
    feiras_demo   = [f["nome"] for f in FEIRAS]
    bairros_demo  = [f["bairro"] for f in FEIRAS]
    dias_demo     = ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira","Sábado","Domingo"]
    tipos_demo    = ["busca","clique_feira","clique_barraca","pedido","como_chegar"]
    conn = sqlite3.connect(DB)
    rows = []
    base = datetime.now() - timedelta(days=90)
    for i in range(600):
        ts      = base + timedelta(days=random.randint(0,89), hours=random.randint(7,21))
        tipo    = random.choices(tipos_demo, weights=[30,25,20,15,10])[0]
        feira   = random.choice(feiras_demo)
        bairro  = random.choice(bairros_demo)
        dia     = random.choice(dias_demo)
        produto = random.choice(produtos_demo)
        valor   = round(random.uniform(8, 55), 2) if tipo == "pedido" else 0
        rows.append((ts.strftime("%Y-%m-%d %H:%M:%S"), tipo, feira, "", produto, bairro, dia, valor))
    conn.executemany(
        "INSERT INTO eventos (ts,tipo,feira,barraca,produto,bairro,dia,valor) VALUES (?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    conn.close()

seed_dados_demo()

# ─── NAVEGAÇÃO ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🥬 Tem na Feira</h1>
  <p>Feiras Livres de São Paulo · Encontre, compre e chegue com facilidade</p>
</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["🏪 Feiras", "🗺️ Como Chegar", "🛒 Carrinho", "📊 Dashboard"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 – FEIRAS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    # Filtros
    col1, col2, col3, col4 = st.columns([2,1,1,2])
    with col1:
        busca = st.text_input("🔍 Buscar por nome ou bairro", placeholder="Ex: Pinheiros, Lapa…")
    with col2:
        dia_sel = st.selectbox("📅 Dia", ["Todos"] + sorted(set(f["dia"] for f in FEIRAS)))
    with col3:
        turno_sel = st.selectbox("🕐 Turno", ["Todos", "Manhã", "Tarde", "Noite"])
    with col4:
        produto_sel = st.text_input("🥦 Produto", placeholder="Ex: banana, peixe, orgânico…")

    # Registra busca
    if busca or produto_sel:
        registrar("busca", bairro=busca, produto=produto_sel)

    # Filtragem
    feiras_filtradas = []
    for f in FEIRAS:
        if busca and busca.lower() not in f["nome"].lower() and busca.lower() not in f["bairro"].lower():
            continue
        if dia_sel != "Todos" and f["dia"] != dia_sel:
            continue
        if turno_sel != "Todos" and f["turno"] != turno_sel:
            continue
        if produto_sel:
            todos_produtos = [p for b in f["barracas"] for p in b["produtos"]]
            if not any(produto_sel.lower() in p.lower() for p in todos_produtos):
                continue
        feiras_filtradas.append(f)

    st.markdown(f"**{len(feiras_filtradas)} feira(s) encontrada(s)**")

    # ── Listagem de feiras ──
    for f in feiras_filtradas:
        with st.expander(f"🥬 **{f['nome']}** · {f['bairro']} · {f['dia']} {f['hora']}", expanded=False):
            registrar("clique_feira", feira=f["nome"], bairro=f["bairro"], dia=f["dia"])

            c1, c2, c3 = st.columns([2,1,1])
            with c1:
                st.markdown(f"📌 `{f['endereco']}`")
            with c2:
                st.markdown(f"""
                <span class='pill pill-amarelo'>📅 {f['dia']}</span>
                <span class='pill pill-verde'>🕐 {f['hora']}</span>
                """, unsafe_allow_html=True)
            with c3:
                if st.button("🗺️ Como Chegar", key=f"mapa_{f['id']}"):
                    registrar("como_chegar", feira=f["nome"], bairro=f["bairro"])
                    st.markdown(f"[📍 Abrir no Google Maps]({maps_url(f['endereco'])})", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown(f"**🏪 {len(f['barracas'])} barracas nesta feira:**")

            for b in f["barracas"]:
                registrar("clique_barraca", feira=f["nome"], barraca=b["nome"])
                bc1, bc2, bc3 = st.columns([3, 2, 1])
                with bc1:
                    st.markdown(f"""
                    <div class="barraca-card">
                      <div class="barraca-nome">{b['emoji']} {b['nome']}</div>
                      <div class="barraca-feirante">👤 {b['feirante']} · <span class="pill pill-verde">{b['tipo']}</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                with bc2:
                    prods_selecionados = st.multiselect(
                        "Adicionar ao carrinho:",
                        b["produtos"],
                        key=f"prod_{f['id']}_{b['nome']}",
                        label_visibility="collapsed",
                        placeholder=f"Produtos de {b['nome']}…"
                    )
                    if prods_selecionados:
                        for p in prods_selecionados:
                            if st.button(f"➕ Adicionar {p}", key=f"add_{f['id']}_{b['nome']}_{p}"):
                                st.session_state.carrinho.append({
                                    "produto": p, "banca": b["nome"],
                                    "feira": f["nome"], "preco": b["preco"],
                                    "feirante": b["feirante"]
                                })
                                registrar("pedido", feira=f["nome"], barraca=b["nome"],
                                          produto=p, bairro=f["bairro"], valor=b["preco"])
                                st.success(f"✅ {p} adicionado!")
                with bc3:
                    msg_wa = f"Olá {b['feirante']}! Vi sua barraca \"{b['nome']}\" na {f['nome']} pelo Tem na Feira 🥬 Gostaria de mais informações!"
                    st.link_button("💬 WhatsApp", wa_url(b["whatsapp"], msg_wa))

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 – COMO CHEGAR
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("### 🗺️ Como Chegar nas Feiras")
    st.info("Clique em **Abrir Rota** para abrir o Google Maps com a rota calculada automaticamente a partir da sua localização.")

    busca_mapa = st.text_input("🔍 Filtrar feira", placeholder="Digite o nome ou bairro…", key="busca_mapa")

    feiras_mapa = [f for f in FEIRAS if not busca_mapa
                   or busca_mapa.lower() in f["nome"].lower()
                   or busca_mapa.lower() in f["bairro"].lower()]

    for f in feiras_mapa:
        col_a, col_b, col_c, col_d = st.columns([3, 1, 1, 1])
        with col_a:
            st.markdown(f"**{f['emoji'] if 'emoji' in f else '🥬'} {f['nome']}**  \n📌 {f['endereco']}")
        with col_b:
            st.markdown(f"<span class='pill pill-amarelo'>📅 {f['dia']}</span>", unsafe_allow_html=True)
        with col_c:
            st.markdown(f"<span class='pill pill-verde'>🕐 {f['hora']}</span>", unsafe_allow_html=True)
        with col_d:
            st.link_button("🗺️ Abrir Rota", maps_url(f["endereco"]), use_container_width=True)
            registrar("como_chegar", feira=f["nome"], bairro=f["bairro"])
        st.divider()

    # Mapa de pontos com st.map
    st.markdown("### 📍 Localização das Feiras em SP")
    df_map = pd.DataFrame([{"lat": f["lat"], "lon": f["lon"], "name": f["nome"]} for f in FEIRAS])
    st.map(df_map, zoom=11, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 – CARRINHO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("### 🛒 Seu Pedido")

    if not st.session_state.carrinho:
        st.info("Seu carrinho está vazio. Adicione produtos na aba **Feiras**.")
    else:
        df_cart = pd.DataFrame(st.session_state.carrinho)

        st.dataframe(
            df_cart[["produto","banca","feira","preco"]].rename(columns={
                "produto":"Produto","banca":"Barraca","feira":"Feira","preco":"Preço (R$)"
            }),
            use_container_width=True, hide_index=True
        )

        total = total_carrinho()
        st.markdown(f"### 💰 Total: **R$ {total:.2f}**")

        st.markdown("---")
        st.markdown("#### 📦 Dados para entrega")
        nome_cli = st.text_input("👤 Seu nome")
        end_cli  = st.text_input("📍 Endereço de entrega")

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            if st.button("📲 Enviar Pedido pelo WhatsApp", type="primary", use_container_width=True):
                if not nome_cli or not end_cli:
                    st.warning("Preencha nome e endereço!")
                else:
                    itens_txt = "\n".join([f"• {i['produto']} – {i['banca']}" for i in st.session_state.carrinho])
                    msg = f"*Novo Pedido – Tem na Feira* 🥬\n\n*Cliente:* {nome_cli}\n*Endereço:* {end_cli}\n\n*Itens:*\n{itens_txt}\n\n*Total: R$ {total:.2f}*"
                    salvar_pedido(nome_cli, end_cli, st.session_state.carrinho, total,
                                  st.session_state.carrinho[0]["feira"] if st.session_state.carrinho else "")
                    st.link_button("✅ Confirmar envio pelo WhatsApp", wa_url("5511999999999", msg))
        with col_e2:
            if st.button("🗑️ Limpar carrinho", use_container_width=True):
                st.session_state.carrinho = []
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# ABA 4 – DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    try:
        import plotly.express as px
        PLOTLY = True
    except ImportError:
        PLOTLY = False

    st.markdown("### 📊 Dashboard de Uso & Relatórios")

    df_ev = carregar_eventos()
    df_ped = carregar_pedidos()

    if df_ev.empty:
        st.info("Nenhum dado ainda. Use o app para gerar dados!")
    else:
        # ── Métricas gerais ──
        total_eventos = len(df_ev)
        total_pedidos = len(df_ped)
        receita_total = df_ped["total"].sum() if not df_ped.empty else 0
        feiras_unicas = df_ev["feira"].nunique()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("👆 Interações", f"{total_eventos:,}")
        m2.metric("🛒 Pedidos",    f"{total_pedidos:,}")
        m3.metric("💰 Receita",    f"R$ {receita_total:,.2f}")
        m4.metric("🏪 Feiras ativas", f"{feiras_unicas}")

        st.markdown("---")
        tab_d1, tab_d2, tab_d3 = st.tabs(["📈 Comportamento", "🥦 Produtos", "🔮 Previsão"])

        # ── TAB: Comportamento ──
        with tab_d1:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Acessos por Dia da Semana")
                df_dia = df_ev.groupby("dia").size().reset_index(name="acessos")
                ordem = ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira","Sábado","Domingo"]
                df_dia["dia"] = pd.Categorical(df_dia["dia"], categories=ordem, ordered=True)
                df_dia = df_dia.sort_values("dia")
                if PLOTLY:
                    fig = px.bar(df_dia, x="dia", y="acessos", color="acessos",
                                 color_continuous_scale="Greens", labels={"dia":"Dia","acessos":"Acessos"})
                    fig.update_layout(showlegend=False, coloraxis_showscale=False, height=300)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.bar_chart(df_dia.set_index("dia")["acessos"])

            with col2:
                st.markdown("#### Tipo de Interação")
                df_tipo = df_ev.groupby("tipo").size().reset_index(name="qtd")
                if PLOTLY:
                    fig2 = px.pie(df_tipo, values="qtd", names="tipo",
                                  color_discrete_sequence=px.colors.sequential.Greens_r)
                    fig2.update_layout(height=300)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.bar_chart(df_tipo.set_index("tipo")["qtd"])

            st.markdown("#### Acessos por Feira")
            df_feira = df_ev[df_ev["feira"] != ""].groupby("feira").size().reset_index(name="acessos")
            df_feira = df_feira.sort_values("acessos", ascending=False)
            if PLOTLY:
                fig3 = px.bar(df_feira, x="acessos", y="feira", orientation="h",
                              color="acessos", color_continuous_scale="Greens")
                fig3.update_layout(showlegend=False, coloraxis_showscale=False, height=350, yaxis_title="")
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.bar_chart(df_feira.set_index("feira")["acessos"])

            st.markdown("#### Evolução de Acessos (últimos 90 dias)")
            df_ev["data"] = df_ev["ts"].dt.date
            df_daily = df_ev.groupby("data").size().reset_index(name="acessos")
            if PLOTLY:
                fig4 = px.line(df_daily, x="data", y="acessos",
                               color_discrete_sequence=["#2d8c47"], markers=True)
                fig4.update_layout(height=280, xaxis_title="", yaxis_title="Acessos")
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.line_chart(df_daily.set_index("data")["acessos"])

        # ── TAB: Produtos ──
        with tab_d2:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🏆 Produtos Mais Buscados")
                df_prod = df_ev[df_ev["produto"] != ""].groupby("produto").size().reset_index(name="buscas")
                df_prod = df_prod.sort_values("buscas", ascending=False).head(10)
                if PLOTLY:
                    fig5 = px.bar(df_prod, x="buscas", y="produto", orientation="h",
                                  color="buscas", color_continuous_scale="Oranges")
                    fig5.update_layout(showlegend=False, coloraxis_showscale=False,
                                       height=350, yaxis_title="")
                    st.plotly_chart(fig5, use_container_width=True)
                else:
                    st.bar_chart(df_prod.set_index("produto")["buscas"])

            with col2:
                st.markdown("#### 📍 Bairros Mais Acessados")
                df_bairro = df_ev[df_ev["bairro"] != ""].groupby("bairro").size().reset_index(name="acessos")
                df_bairro = df_bairro.sort_values("acessos", ascending=False).head(8)
                if PLOTLY:
                    fig6 = px.pie(df_bairro, values="acessos", names="bairro",
                                  color_discrete_sequence=px.colors.sequential.Greens_r)
                    fig6.update_layout(height=350)
                    st.plotly_chart(fig6, use_container_width=True)
                else:
                    st.bar_chart(df_bairro.set_index("bairro")["acessos"])

            if not df_ped.empty:
                st.markdown("#### 💰 Relatório de Vendas por Feira")
                df_vend = df_ped.groupby("feira").agg(
                    pedidos=("id","count"), receita=("total","sum")
                ).reset_index().sort_values("receita", ascending=False)
                df_vend["ticket_medio"] = (df_vend["receita"] / df_vend["pedidos"]).round(2)
                st.dataframe(df_vend.rename(columns={
                    "feira":"Feira","pedidos":"Pedidos",
                    "receita":"Receita (R$)","ticket_medio":"Ticket Médio (R$)"
                }), use_container_width=True, hide_index=True)

        # ── TAB: Previsão ──
        with tab_d3:
            st.markdown("#### 🔮 Previsão de Demanda (próximos 30 dias)")
            st.caption("Usando dados históricos de acessos para prever tendência futura.")

            df_ev["data"] = df_ev["ts"].dt.date
            df_daily2 = df_ev.groupby("data").size().reset_index(name="y")
            df_daily2.columns = ["ds", "y"]
            df_daily2["ds"] = pd.to_datetime(df_daily2["ds"])

            try:
                from prophet import Prophet
                model = Prophet(yearly_seasonality=False, weekly_seasonality=True, daily_seasonality=False)
                model.fit(df_daily2)
                futuro = model.make_future_dataframe(periods=30)
                forecast = model.predict(futuro)
                df_plot = forecast[["ds","yhat","yhat_lower","yhat_upper"]].tail(60)
                if PLOTLY:
                    fig7 = px.line(df_plot, x="ds", y="yhat",
                                   labels={"ds":"Data","yhat":"Acessos previstos"},
                                   color_discrete_sequence=["#1e6b35"])
                    fig7.add_scatter(x=df_plot["ds"], y=df_plot["yhat_upper"],
                                     fill=None, mode="lines", line_color="rgba(45,140,71,.2)", name="Máx")
                    fig7.add_scatter(x=df_plot["ds"], y=df_plot["yhat_lower"],
                                     fill="tonexty", mode="lines", line_color="rgba(45,140,71,.2)",
                                     fillcolor="rgba(45,140,71,.1)", name="Mín")
                    fig7.update_layout(height=350, xaxis_title="", yaxis_title="Acessos")
                    st.plotly_chart(fig7, use_container_width=True)
                else:
                    st.line_chart(df_plot.set_index("ds")["yhat"])
                st.success("✅ Previsão gerada com Prophet (modelo de série temporal)")

            except ImportError:
                # Fallback: regressão linear simples
                import numpy as np
                df_daily2["t"] = (df_daily2["ds"] - df_daily2["ds"].min()).dt.days
                x = df_daily2["t"].values
                y = df_daily2["y"].values
                coef = np.polyfit(x, y, 1)
                future_t = np.arange(x.max() + 1, x.max() + 31)
                future_dates = [df_daily2["ds"].max() + timedelta(days=int(i - x.max())) for i in future_t]
                pred = np.polyval(coef, future_t).clip(0)
                df_prev = pd.DataFrame({"ds": future_dates, "previsao": pred.round(1)})
                if PLOTLY:
                    fig_hist = px.line(df_daily2, x="ds", y="y",
                                       labels={"ds":"Data","y":"Acessos reais"},
                                       color_discrete_sequence=["#5a5a5a"])
                    fig_prev2 = px.line(df_prev, x="ds", y="previsao",
                                        labels={"ds":"Data","previsao":"Previsão"},
                                        color_discrete_sequence=["#e8722a"])
                    fig_hist.add_traces(fig_prev2.data)
                    fig_hist.update_layout(height=350, xaxis_title="", yaxis_title="Acessos")
                    st.plotly_chart(fig_hist, use_container_width=True)
                else:
                    st.line_chart(pd.concat([
                        df_daily2.set_index("ds")["y"].rename("Histórico"),
                        df_prev.set_index("ds")["previsao"].rename("Previsão")
                    ], axis=1))
                st.info("💡 Previsão por regressão linear. Instale `prophet` para previsão avançada.")

            st.markdown("#### 📅 Produtos com Maior Tendência de Crescimento")
            df_prod_trend = df_ev[df_ev["produto"] != ""].copy()
            if not df_prod_trend.empty:
                df_prod_trend["semana"] = df_prod_trend["ts"].dt.isocalendar().week
                df_trend = df_prod_trend.groupby(["produto","semana"]).size().reset_index(name="qtd")
                top_prods = df_prod_trend["produto"].value_counts().head(6).index.tolist()
                df_trend = df_trend[df_trend["produto"].isin(top_prods)]
                if PLOTLY:
                    fig8 = px.line(df_trend, x="semana", y="qtd", color="produto",
                                   labels={"semana":"Semana","qtd":"Buscas","produto":"Produto"},
                                   color_discrete_sequence=px.colors.qualitative.Set2)
                    fig8.update_layout(height=320, xaxis_title="Semana do ano")
                    st.plotly_chart(fig8, use_container_width=True)
                else:
                    st.line_chart(df_trend.pivot(index="semana", columns="produto", values="qtd"))

    st.markdown("---")
    with st.expander("📥 Exportar dados brutos"):
        df_export = carregar_eventos()
        st.download_button(
            "⬇️ Baixar eventos CSV",
            df_export.to_csv(index=False).encode("utf-8"),
            "eventos_tem_na_feira.csv", "text/csv"
        )
        if not df_ped.empty:
            st.download_button(
                "⬇️ Baixar pedidos CSV",
                df_ped.to_csv(index=False).encode("utf-8"),
                "pedidos_tem_na_feira.csv", "text/csv"
            )
