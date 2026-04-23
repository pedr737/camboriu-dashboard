"""
Dashboard Camboriú — Carteira de Clientes
Streamlit + Plotly | Supabase PostgreSQL
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import psycopg2
import re
from datetime import date, timedelta
from html import unescape
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# Configuração da página
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Camboriú · Carteira",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_URL        = st.secrets.get("DB_URL", "")         # conexão direta (IPv6 em alguns ambientes)
DB_URL_POOLER = st.secrets.get("DB_URL_POOLER", "")  # Session Pooler IPv4 — preferido
_CONN_URL     = DB_URL_POOLER or DB_URL               # usa pooler se disponível

# ─────────────────────────────────────────────────────────────────────────────
# Autenticação simples
# ─────────────────────────────────────────────────────────────────────────────

def _check_password() -> bool:
    if st.session_state.get("_auth"):
        return True
    st.markdown("""
    <style>
    .auth-box { max-width: 340px; margin: 15vh auto 0; text-align: center; }
    .auth-box h2 { font-size: 1.3rem; font-weight: 700; margin-bottom: 1.5rem; color: #111; }
    </style>
    <div class="auth-box"><h2>Camboriú · Dashboard</h2></div>
    """, unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        pwd = st.text_input("Senha de acesso", type="password", label_visibility="collapsed",
                            placeholder="Senha de acesso")
        if st.button("Entrar", use_container_width=True):
            senha_correta = st.secrets.get("SENHA", "")
            if pwd == senha_correta:
                st.session_state["_auth"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

if not _check_password():
    st.stop()

# ── Teste de conexão (diagnóstico — remover depois de funcionar) ────────────
try:
    _test_conn = psycopg2.connect(_CONN_URL, connect_timeout=10)
    _test_conn.close()
except Exception as _e:
    st.error(f"Erro de conexão: **{type(_e).__name__}** — {_e}")
    _shown = _CONN_URL[:25] if _CONN_URL else "(vazio)"
    st.info(f"URL usada tem {len(_CONN_URL)} caracteres. Começa com: `{_shown}...`")
    st.stop()

# ── Fonte e estilos ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=block');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');

html, body, [class*="css"], [class*="st-"], .stApp {
    font-family: 'Inter', sans-serif !important;
}
h1 { font-size: 1.55rem !important; font-weight: 700 !important; color: #111 !important; }
h2 { font-size: 1.15rem !important; font-weight: 600 !important; color: #222 !important; }
h3 { font-size: 1.0rem  !important; font-weight: 600 !important; color: #333 !important; }
[data-testid="metric-container"] label { font-size: 0.78rem !important; color: #555 !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.5rem !important; font-weight: 700 !important;
}
.nota-status { font-size: 0.8rem; color: #666; line-height: 1.7; padding: 6px 0; }

/* Fallback CSS — se houver texto começando com _arrow no expander, esconde */
details summary [data-testid="stIconMaterial"],
details summary span.material-symbols-rounded,
details summary span.material-icons {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-feature-settings: 'liga' !important;
}
</style>
""", unsafe_allow_html=True)

# Injeta JS real via componente (st.markdown strip-a <script>)
components.html("""
<script>
(function () {
  const isArrowLeak = (t) => t && /^_?arrow/i.test(t.trim());
  function cleanup() {
    const doc = window.parent && window.parent.document;
    if (!doc) return;
    // Varre TODOS os elementos folha dentro de summary
    doc.querySelectorAll('details summary *').forEach(el => {
      if (el.children.length === 0 && isArrowLeak(el.textContent)) {
        el.style.cssText = 'display:none!important';
      }
    });
  }
  cleanup();
  setInterval(cleanup, 400);
  try {
    const obs = new MutationObserver(cleanup);
    obs.observe(window.parent.document.body, {childList: true, subtree: true, characterData: true});
  } catch (e) {}
})();
</script>
""", height=0)

# ── Paletas ───────────────────────────────────────────────────────────────────
CORES_SEG = {
    "1 - Atacado":    "#1A73E8",
    "2 - Varejo":     "#34A853",
    "5 - Atacarejo":  "#F9AB00",
    "E-COMMERCE":     "#E8453C",
    "Sem Segmento":   "#BDC1C6",
}

CORES_STATUS = {
    "ativo":               "#34A853",
    "em_risco":            "#F9AB00",
    "hibernando":          "#FA7B17",
    "hibernando_sazonal":  "#FF6D00",
    "perdido":             "#E8453C",
    "sem_compra":          "#BDC1C6",
}

LABEL_STATUS = {
    "ativo":               "Ativo",
    "em_risco":            "Em Risco",
    "hibernando":          "Hibernando",
    "hibernando_sazonal":  "Hibern. Sazonal",
    "perdido":             "Perdido",
    "sem_compra":          "Sem compra",
}

MESES_PT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
            7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers de formatação (pt-BR)
# ─────────────────────────────────────────────────────────────────────────────

def fmt_num(v, decimals=0):
    """Número pt-BR: 1.234.567,89"""
    if pd.isna(v):
        return "—"
    s = f"{float(v):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl(v, compact=False):
    """Valor em Reais pt-BR."""
    if pd.isna(v):
        return "—"
    v = float(v)
    if compact:
        if abs(v) >= 1_000_000:
            return f"R$ {fmt_num(v / 1_000_000, 1)}M"
        if abs(v) >= 1_000:
            return f"R$ {fmt_num(v / 1_000, 0)}K"
    return "R$ " + fmt_num(v, 0)


def apply_ptbr(fig):
    """Aplica separadores pt-BR a qualquer figura Plotly."""
    fig.update_layout(separators=",.")
    return fig


def botao_csv(df: pd.DataFrame, nome: str, label: str = "Exportar CSV", key: str | None = None):
    """Download em formato brasileiro (separador ;, decimal ,, UTF-8 BOM)."""
    csv = df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
    st.download_button(label, csv, f"{nome}.csv", "text/csv", key=key)


# Mapeamentos para o export Trello-ready
_TRELLO_STATUS_LABEL = {
    "em_risco":            "Em risco",
    "hibernando":          "Hibernando",
    "hibernando_sazonal":  "Hibernando",
    "perdido":             "Perdido",
    "ativo":               "Ativo",
}
_TRELLO_STATUS_ACAO = {
    "em_risco":            "Janela curta — ligar em 7 dias",
    "hibernando":          "Visita/call estruturada em 30 dias",
    "hibernando_sazonal":  "Acompanhar retorno na próxima temporada",
    "perdido":             "Oferta-âncora + carta executiva em 30 dias",
    "ativo":               "Manutenção no ciclo regular",
}


def _val(v) -> str:
    """String limpa ou '—' para nulos/vazios/NaN — para descrições Trello.
    Datas são reduzidas a AAAA-MM-DD (remove 00:00:00 supérfluo)."""
    if v is None:
        return "—"
    if isinstance(v, float) and pd.isna(v):
        return "—"
    if isinstance(v, (pd.Timestamp,)):
        return "—" if pd.isna(v) else v.strftime("%Y-%m-%d")
    s = str(v).strip()
    return s if s and s.lower() != "nan" else "—"


def montar_df_trello(df_fila: pd.DataFrame) -> pd.DataFrame:
    """Transforma uma fila (com id, nome_exibicao, vendedor, status_cliente,
    camada, valor_total_r, ticket_medio_r, total_compras, dias_sem_compra,
    ultima_compra, cidade, uf, documento_norm) no formato que o Blue Cat
    Imports (importer CSV do Trello) consome diretamente.

    Colunas de saída: Card Name, List Name, Labels, Members, Card Description.
    """
    if df_fila.empty:
        return pd.DataFrame(columns=[
            "Card Name", "List Name", "Labels", "Members", "Card Description"
        ])

    df = df_fila.copy()

    # Enriquecimento com contatos (via load_contatos, cache 1h)
    try:
        contatos = load_contatos()
        df = df.merge(contatos, on="id", how="left")
    except Exception:
        for c in ("email", "telefone", "celular", "whatsapp"):
            df[c] = ""

    def _melhor_tel(r):
        for col in ("whatsapp", "celular", "telefone"):
            v = r.get(col)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return "—"

    def _labels(r):
        st_lbl = _TRELLO_STATUS_LABEL.get(r.get("status_cliente"), "")
        cam    = str(r.get("camada", "")).split(" — ")[0].strip()  # "A — Alto valor" → "A"
        return ", ".join([x for x in [st_lbl, f"Camada {cam}" if cam else ""] if x])

    def _desc(r):
        tel = _melhor_tel(r)
        linhas = [
            f"Vendedor: {_val(r.get('vendedor'))}",
            f"Ação: {_TRELLO_STATUS_ACAO.get(r.get('status_cliente'), '—')}",
            "",
            f"LTV: R$ {float(r.get('valor_total_r') or 0):,.0f}".replace(",", "."),
            f"Ticket médio: R$ {float(r.get('ticket_medio_r') or 0):,.0f}".replace(",", "."),
            f"Total compras: {int(r.get('total_compras') or 0)}",
            f"Dias sem comprar: {int(r.get('dias_sem_compra') or 0)}",
            f"Última compra: {_val(r.get('ultima_compra'))}",
            "",
            f"Cidade: {_val(r.get('cidade'))}/{_val(r.get('uf'))}",
            f"Documento: {_val(r.get('documento_norm'))}",
            "",
            f"Contato principal: {tel}",
            f"E-mail: {_val(r.get('email'))}",
            f"Telefone: {_val(r.get('telefone'))}",
            f"Celular: {_val(r.get('celular'))}",
            f"WhatsApp: {_val(r.get('whatsapp'))}",
        ]
        return "\n".join(linhas)

    return pd.DataFrame({
        "Card Name":        df["nome_exibicao"],
        "List Name":        "A Contatar",        # todos entram na coluna inicial
        "Labels":           df.apply(_labels, axis=1),
        "Members":          "",                   # atribuição manual no Trello
        "Card Description": df.apply(_desc, axis=1),
    })


def botao_csv_trello(df_fila: pd.DataFrame, nome: str,
                     label: str = "Exportar para Trello (CSV)",
                     key: str | None = None):
    """Botão paralelo ao botao_csv. Gera CSV pronto para o Blue Cat Imports
    (power-up de import CSV do Trello). Requer que no board Trello existam:
    • Lista `A Contatar`
    • Labels `Em risco`, `Hibernando`, `Perdido`, `Camada A` (ou B/C)
    """
    df_trello = montar_df_trello(df_fila)
    # CSV padrão Trello: separador vírgula, UTF-8 BOM (Excel-friendly),
    # aspas automáticas para proteger descrições multilinha.
    csv = df_trello.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label, csv, f"{nome}_trello.csv", "text/csv", key=key,
        help=(
            "Formato pronto para o Blue Cat Imports. "
            "No Trello: •••  → Imports → upload do arquivo. "
            "Requer que o board já tenha a lista 'A Contatar' e as labels "
            "'Em risco', 'Hibernando', 'Perdido' e 'Camada A/B/C' criadas."
        ),
    )


def calcular_score_rfv(df: pd.DataFrame) -> pd.DataFrame:
    """Score VF composto (Valor + Frequência) aplicado sobre qualquer subset.

    Score = 0.7·V + 0.3·F
      - V = ticket_medio / média_do_segmento  (cap 3)
      - F = total_compras / mediana_do_segmento (cap 3)

    Modificador sazonal: +0.2 em Out–Dez para clientes com perfil "Sazonal".

    Camadas (percentis do score dentro do subset passado):
      - A — Alto valor (Top 5%)
      - B — Médio valor (6 a 20%)
      - C — Base (restante)

    Nota — antes essa função aplicava RFV clássico (0.5·V + 0.3·F + 0.2·R_inv).
    O R foi removido porque a matriz "camada × status" usa status como eixo, e
    status é 100% recência. Manter R no score causava dupla contagem parcial:
    clientes valiosos mas parados caíam de camada por terem R_inv baixo,
    esvaziando artificialmente células críticas como "A × Perdido". O nome
    `calcular_score_rfv` foi mantido para retrocompatibilidade de chamadas.
    """
    df = df.copy()
    if "segmento" not in df.columns or df.empty:
        df["score"] = 0.0
        df["camada"] = "C — Base"
        return df

    tm_seg = df.groupby("segmento")["ticket_medio_r"].transform("mean").replace(0, pd.NA)
    f_seg  = df.groupby("segmento")["total_compras"].transform("median").replace(0, pd.NA)

    df["v_norm"] = (df["ticket_medio_r"] / tm_seg).clip(upper=3).fillna(0)
    df["f_norm"] = (df["total_compras"] / f_seg).clip(upper=3).fillna(0)
    # r_inv mantido no DataFrame para compat com código que lê a coluna,
    # mas não entra mais no score. Ver nota na docstring.
    df["r_inv"]  = (1 - df["dias_sem_compra"] / 365).clip(lower=0).fillna(0)

    # ── Score atual (VF): V=70% + F=30%, sem recência ───────────────────────
    df["score"]  = 0.7 * df["v_norm"] + 0.3 * df["f_norm"]

    # ── Score antigo (RFV clássico) — mantido comentado para reversão ───────
    # df["score"]  = 0.5 * df["v_norm"] + 0.3 * df["f_norm"] + 0.2 * df["r_inv"]

    hoje = pd.Timestamp.now()
    if hoje.month in (10, 11, 12) and "perfil_sazonalidade" in df.columns:
        df.loc[df["perfil_sazonalidade"] == "Sazonal", "score"] += 0.2

    rank_pct = df["score"].rank(pct=True, ascending=False)
    df["camada"] = pd.cut(
        rank_pct,
        bins=[0, 0.05, 0.20, 1.01],
        labels=["A — Alto valor", "B — Médio valor", "C — Base"],
        include_lowest=True,
    )
    return df.sort_values("score", ascending=False)


# Alias retrocompatível — antigo nome ainda referenciado em alguns pontos.
calcular_score_reativacao = calcular_score_rfv


def aplicar_periodo(df: pd.DataFrame, periodo: str, col: str) -> pd.DataFrame:
    """Filtra df pela coluna de data conforme o período escolhido."""
    if periodo == "Desde o início" or col not in df.columns or df.empty:
        return df
    hoje = pd.Timestamp(date.today())
    if periodo == "Últimos 12 meses":
        ini = hoje - pd.DateOffset(months=12)
        return df[df[col] >= ini]
    if periodo == "Últimos 24 meses":
        ini = hoje - pd.DateOffset(months=24)
        return df[df[col] >= ini]
    if periodo == "Ano atual":
        return df[df[col].dt.year == hoje.year]
    if periodo == "Ano anterior":
        return df[df[col].dt.year == (hoje.year - 1)]
    return df


def limpar_descricao_item(valor) -> str:
    """Remove HTML/ruído do item e preserva um nome curto legível."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "Sem descrição"
    texto = unescape(str(valor))
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s*\(Ref\.[^)]+\)", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*REF:\s*[A-Z0-9\-\/]+\s*$", "", texto, flags=re.IGNORECASE)
    return texto or "Sem descrição"


def faixa_preco_item(valor: float | int | None) -> str:
    if valor is None or pd.isna(valor):
        return "Sem preço"
    v = float(valor)
    if v < 50:
        return "Até R$ 49"
    if v < 100:
        return "R$ 50–99"
    if v < 150:
        return "R$ 100–149"
    if v < 200:
        return "R$ 150–199"
    return "R$ 200+"


CORES_PRIORIDADE = {
    "Alta":  "#c0392b",
    "Média": "#b7791f",
    "Baixa": "#9aa0a6",
}


def calcular_gap_medio_segmento(df: pd.DataFrame) -> pd.Series:
    """Gap mediano entre compras por segmento, com fallback global."""
    if df.empty:
        return pd.Series(dtype=float)
    idade_rel = (df["ultima_compra"] - df["primeira_compra"]).dt.days.clip(lower=0)
    gap_cliente = idade_rel / (df["total_compras"] - 1).replace(0, pd.NA)
    gap_seg = gap_cliente.groupby(df["segmento"]).transform("median")
    gap_geral = gap_cliente.median()
    if pd.isna(gap_geral) or gap_geral <= 0:
        gap_geral = 45.0
    return gap_seg.fillna(gap_geral).clip(lower=15, upper=180)


def classificar_janela_segunda_compra(dias_desde_primeira) -> str:
    if dias_desde_primeira is None or pd.isna(dias_desde_primeira):
        return "Sem data"
    dias = float(dias_desde_primeira)
    if dias <= 14:
        return "Ainda cedo"
    if dias <= 60:
        return "Janela ideal"
    if dias <= 120:
        return "Atrasada"
    return "Esfriando"


def classificar_momento_expansao(dias_sem_compra, gap_medio_segmento) -> str:
    if dias_sem_compra is None or pd.isna(dias_sem_compra):
        return "Sem histórico"
    gap = gap_medio_segmento if pd.notna(gap_medio_segmento) and gap_medio_segmento > 0 else 45
    razao = float(dias_sem_compra) / float(gap)
    if razao < 0.75:
        return "Ainda no ciclo"
    if razao <= 1.35:
        return "Janela quente"
    if razao <= 2.00:
        return "Pede ação"
    return "Esfriando"


# ─────────────────────────────────────────────────────────────────────────────
# Conexão e cache
# ─────────────────────────────────────────────────────────────────────────────

def _new_conn():
    if not _CONN_URL:
        st.error("DB_URL vazio — configure em Settings → Secrets no Streamlit Cloud.")
        st.stop()
    return psycopg2.connect(_CONN_URL, connect_timeout=15,
                            options="-c statement_timeout=60000")


def qry(sql):
    conn = _new_conn()
    try:
        with conn.cursor() as c:
            c.execute(sql)
            cols = [d[0] for d in c.description]
            return pd.DataFrame(c.fetchall(), columns=cols)
    finally:
        conn.close()


@st.cache_data(ttl=3600, show_spinner=False)
def load_faturamento():
    df = qry("""
        SELECT mes, segmento, clientes_distintos, qtd_vendas,
               valor_total_r::float, novos_clientes_mes
        FROM vw_ls_faturamento_mensal
        WHERE mes >= '2024-01-01'
        ORDER BY mes
    """)
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_carteira():
    df = qry("""
        SELECT id, nome_exibicao, documento_norm, segmento, segmento_atual,
               perfil_sazonalidade, representante_principal, cidade, uf, origem,
               flag_origem_dapic, flag_origem_tray, total_compras,
               primeira_compra, ultima_compra,
               valor_total_r::float, ticket_medio_r::float,
               dias_sem_compra, status_cliente, faixa_ticket, faixa_frequencia
        FROM vw_ls_carteira
    """)
    df["primeira_compra"] = pd.to_datetime(df["primeira_compra"], errors="coerce")
    df["ultima_compra"]   = pd.to_datetime(df["ultima_compra"],   errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_reativacao():
    df = qry("""
        SELECT nome_exibicao, segmento, cidade, uf,
               representante_principal, status_cliente,
               ultima_compra, dias_sem_compra, total_compras,
               valor_total_r::float, ticket_medio_r::float,
               prioridade_reativacao
        FROM vw_ls_reativacao
        ORDER BY prioridade_reativacao, valor_total_r DESC
    """)
    df["ultima_compra"] = pd.to_datetime(df["ultima_compra"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_pagamentos():
    df = qry("""
        SELECT mes, segmento, forma_pagamento_norm, parcelas,
               qtd_vendas, valor_total_r::float, ticket_medio_r::float
        FROM vw_ls_pagamentos
        WHERE mes >= '2024-01-01'
        ORDER BY mes
    """)
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_cohort():
    df = qry("""
        SELECT mes_entrada, meses_desde_entrada,
               clientes_retidos, tamanho_cohort, pct_retencao::float
        FROM vw_ls_cohort_simples
        WHERE mes_entrada >= '2024-03-01' AND meses_desde_entrada <= 12
        ORDER BY mes_entrada, meses_desde_entrada
    """)
    df["mes_entrada"] = pd.to_datetime(df["mes_entrada"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_novos():
    df = qry("""
        SELECT mes_primeira_compra, segmento, uf, novos_clientes
        FROM vw_ls_novos_clientes
        WHERE mes_primeira_compra >= '2024-01-01'
        ORDER BY mes_primeira_compra
    """)
    df["mes_primeira_compra"] = pd.to_datetime(df["mes_primeira_compra"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_cidades_pe():
    df = qry("""
        SELECT dc.cidade_norm                      AS cidade,
               COALESCE(dc.segmento_predominante,
                        fv.tabela_preco,
                        'Sem Segmento')            AS segmento,
               COUNT(DISTINCT dc.id)               AS clientes,
               COUNT(fv.id)                        AS vendas,
               ROUND(SUM(fv.valor_total_liquido)::numeric/100,0)::float AS valor_r
        FROM dim_clientes dc
        JOIN fato_vendas fv ON fv.cliente_id = dc.id
        WHERE dc.estado_norm = 'PE'
          AND fv.status_venda IN ('Fechada','Fechado')
          AND dc.cidade_norm IS NOT NULL
        GROUP BY 1, 2
    """)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_vendedores():
    df = qry("""
        SELECT vendedor, mes, segmento,
               qtd_vendas, clientes_distintos,
               valor_total_r::float, ticket_medio_r::float
        FROM vw_ls_vendedores
        WHERE mes >= '2024-01-01'
        ORDER BY mes, valor_total_r DESC
    """)
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_carteira_demo():
    """Carteira com campos extras para o painel Demografia (requer migração 002)."""
    df = qry("""
        SELECT id, nome_exibicao, segmento, segmento_atual,
               tipo_pessoa, documento_tipo, grupo_cadastrado,
               cidade, uf, primeira_compra, ultima_compra,
               valor_total_r::float, ticket_medio_r::float,
               total_compras, dias_sem_compra, status_cliente
        FROM vw_ls_carteira
    """)
    df["primeira_compra"] = pd.to_datetime(df["primeira_compra"], errors="coerce")
    df["ultima_compra"]   = pd.to_datetime(df["ultima_compra"],   errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_carteira_geo_cached():
    """Carteira enriquecida com lat/lon IBGE e distância até a sede."""
    from geo import enriquecer_carteira_geo
    return enriquecer_carteira_geo(load_carteira_demo())


@st.cache_data(ttl=3600, show_spinner=False)
def load_vendas_geo():
    """Vendas mensais por cidade para análise geográfica-temporal."""
    df = qry("""
        SELECT
            DATE_TRUNC('month', fv.data_venda)::date         AS mes,
            dc.cidade_norm                                    AS cidade,
            dc.estado_norm                                    AS uf,
            COALESCE(fv.tabela_preco, 'Sem Segmento')        AS segmento,
            COUNT(fv.id)                                      AS qtd_vendas,
            ROUND(SUM(fv.valor_total_liquido)::numeric/100,2)::float AS valor_r,
            ROUND(AVG(fv.valor_total_liquido)::numeric/100,2)::float AS ticket_medio_r
        FROM fato_vendas fv
        JOIN dim_clientes dc ON dc.id = fv.cliente_id
        WHERE fv.status_venda IN ('Fechada','Fechado')
          AND fv.data_venda IS NOT NULL
          AND dc.cidade_norm IS NOT NULL
        GROUP BY 1, 2, 3, 4
        ORDER BY 1
    """)
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_itens_clientes():
    """Itens vendidos com atributos do cliente para análises de mix/produto."""
    df = qry("""
        SELECT
            fi.id                                            AS item_id,
            fi.origem,
            fi.sistema_venda_id,
            fi.sistema_item_id,
            fi.sku,
            fi.referencia,
            fi.descricao_produto,
            fi.quantidade::float                             AS quantidade,
            fi.preco_unitario::float                         AS preco_unitario_r,
            fi.valor_total_item::float                       AS valor_total_item_r,
            fv.data_venda,
            fv.status_venda,
            COALESCE(vc.segmento, fv.tabela_preco, 'Sem Segmento') AS segmento,
            fv.cliente_id,
            vc.nome_exibicao,
            dc.grupo_cadastrado,
            vc.cidade,
            vc.uf,
            vc.status_cliente,
            vc.total_compras,
            vc.valor_total_r::float                          AS cliente_ltv_r,
            vc.ticket_medio_r::float                         AS cliente_ticket_medio_r
        FROM fato_itens_venda fi
        LEFT JOIN fato_vendas fv
               ON fv.id = fi.venda_id
        LEFT JOIN vw_ls_carteira vc
               ON vc.id = fv.cliente_id
        LEFT JOIN dim_clientes dc
               ON dc.id = fv.cliente_id
        ORDER BY fv.data_venda DESC NULLS LAST, fi.id DESC
    """)
    if df.empty:
        return df
    df["data_venda"] = pd.to_datetime(df["data_venda"], errors="coerce")
    for c in ["quantidade", "preco_unitario_r", "valor_total_item_r",
              "cliente_ltv_r", "cliente_ticket_medio_r"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["produto"] = df["descricao_produto"].map(limpar_descricao_item)
    df["faixa_preco_item"] = df["preco_unitario_r"].map(faixa_preco_item)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_orfas():
    df = qry("""
        SELECT
            DATE_TRUNC('month', data_venda)::date          AS mes,
            COALESCE(tabela_preco, 'Sem Segmento')         AS segmento,
            COUNT(*)                                        AS total_vendas,
            COUNT(*) FILTER (WHERE venda_orfa = true)       AS vendas_orfas,
            ROUND(SUM(valor_total_liquido)::numeric / 100, 2)          AS valor_total_r,
            ROUND((SUM(valor_total_liquido)
                   FILTER (WHERE venda_orfa = true))::numeric / 100, 2) AS valor_orfas_r
        FROM fato_vendas
        WHERE status_venda IN ('Fechada','Fechado')
          AND data_venda IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1
    """)
    df["mes"] = pd.to_datetime(df["mes"])
    for c in ["total_vendas","vendas_orfas"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in ["valor_total_r","valor_orfas_r"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(float)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_cliente_vendedor():
    """Vendedor predominante por cliente — maior nº de vendas fechadas."""
    df = qry("""
        WITH v AS (
            SELECT cliente_id,
                   funcionario_vendedor,
                   COUNT(*)                          AS n_vendas,
                   SUM(valor_total_liquido)::float   AS valor
            FROM fato_vendas
            WHERE cliente_id IS NOT NULL
              AND funcionario_vendedor IS NOT NULL
              AND status_venda IN ('Fechada','Fechado')
            GROUP BY 1, 2
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY cliente_id
                       ORDER BY n_vendas DESC, valor DESC, funcionario_vendedor
                   ) AS rn
            FROM v
        )
        SELECT cliente_id,
               funcionario_vendedor AS vendedor_principal
        FROM ranked WHERE rn = 1
    """)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_cohort_segmento():
    df = qry("""
        WITH primeira AS (
            SELECT fv.cliente_id,
                   COALESCE(dc.segmento_predominante,
                            fv.tabela_preco, 'Sem Segmento')  AS segmento,
                   DATE_TRUNC('month', MIN(fv.data_venda))::date AS mes_entrada
            FROM fato_vendas fv
            LEFT JOIN dim_clientes dc ON dc.id = fv.cliente_id
            WHERE fv.cliente_id IS NOT NULL
              AND fv.status_venda IN ('Fechada','Fechado')
            GROUP BY 1, 2
        ),
        cohort_size AS (
            SELECT segmento, mes_entrada,
                   COUNT(DISTINCT cliente_id) AS tamanho
            FROM primeira GROUP BY 1, 2
        ),
        meses_compra AS (
            SELECT DISTINCT fv.cliente_id,
                   DATE_TRUNC('month', fv.data_venda)::date AS mes
            FROM fato_vendas fv
            WHERE fv.cliente_id IS NOT NULL
              AND fv.status_venda IN ('Fechada','Fechado')
        ),
        retencao AS (
            SELECT p.segmento, p.mes_entrada,
                   (EXTRACT(YEAR FROM AGE(mc.mes, p.mes_entrada))*12
                    + EXTRACT(MONTH FROM AGE(mc.mes, p.mes_entrada)))::int
                        AS meses_desde_entrada,
                   COUNT(DISTINCT mc.cliente_id) AS clientes_retidos
            FROM primeira p
            JOIN meses_compra mc
              ON mc.cliente_id = p.cliente_id AND mc.mes >= p.mes_entrada
            GROUP BY 1, 2, 3
        )
        SELECT r.segmento, r.mes_entrada, r.meses_desde_entrada,
               r.clientes_retidos, cs.tamanho AS tamanho_cohort,
               ROUND(r.clientes_retidos * 100.0
                     / NULLIF(cs.tamanho, 0), 1)::float AS pct_retencao
        FROM retencao r
        JOIN cohort_size cs
          ON cs.segmento = r.segmento AND cs.mes_entrada = r.mes_entrada
        WHERE r.mes_entrada >= '2024-03-01'
          AND r.meses_desde_entrada <= 12
        ORDER BY 1, 2, 3
    """)
    df["mes_entrada"] = pd.to_datetime(df["mes_entrada"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_contatos() -> pd.DataFrame:
    """Email/telefone/celular/whatsapp por cliente. Usado na exportação
    Trello-ready — não entra na carteira principal (evita poluir o df em memória)."""
    return qry("""
        SELECT id, email, telefone, celular, whatsapp
        FROM dim_clientes
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

PAINEIS = ["Executivo", "Recorrência", "Sazonalidade", "Estratégia de Carteira",
           "Demografia", "Itens", "Vendedores", "Qualidade de Dados"]

if "painel" not in st.session_state:
    st.session_state["painel"] = "Executivo"
if "seg_filter" not in st.session_state:
    st.session_state["seg_filter"] = "Todos"
if "periodo" not in st.session_state:
    st.session_state["periodo"] = "Últimos 24 meses"

# Navegação entre painéis via botões: consumir _nav_target ANTES do radio
# (Streamlit não permite alterar session_state[key] após o widget existir).
if "_nav_target" in st.session_state:
    _target = st.session_state.pop("_nav_target")
    if _target in PAINEIS:
        st.session_state["painel"] = _target

with st.sidebar:
    st.markdown("## Camboriú")
    st.caption("Gestão de Carteira · 2024–2026")
    st.divider()

    painel = st.radio(
        "Painel", PAINEIS, key="painel",
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Filtros")

    seg_options = ["Todos", "1 - Atacado", "2 - Varejo", "5 - Atacarejo"]
    seg_filter = st.selectbox("Segmento", seg_options, key="seg_filter")

    periodo = st.selectbox(
        "Período",
        ["Últimos 12 meses", "Últimos 24 meses", "Ano atual",
         "Ano anterior", "Desde o início"],
        key="periodo",
    )

    st.divider()
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache atualizado a cada 1h")


# ─────────────────────────────────────────────────────────────────────────────
# Carrega dados
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Carregando..."):
    df_fat_full   = load_faturamento()
    df_cart       = load_carteira()
    df_reat       = load_reativacao()
    df_pag_full   = load_pagamentos()
    df_cohort     = load_cohort()
    df_novos_full = load_novos()
    df_pe         = load_cidades_pe()
    df_vend_full  = load_vendedores()
    df_orfas_full = load_orfas()
    df_cohort_seg = load_cohort_segmento()
    df_cli_vend   = load_cliente_vendedor()

df_fat   = aplicar_periodo(df_fat_full,   periodo, "mes")
df_pag   = aplicar_periodo(df_pag_full,   periodo, "mes")
df_novos = aplicar_periodo(df_novos_full, periodo, "mes_primeira_compra")
df_vend  = aplicar_periodo(df_vend_full,  periodo, "mes")
df_orfas = aplicar_periodo(df_orfas_full, periodo, "mes")


def seg(df, col="segmento"):
    if seg_filter == "Todos" or col not in df.columns:
        return df
    return df[df[col] == seg_filter]


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 1 — EXECUTIVO
# ═════════════════════════════════════════════════════════════════════════════

if painel == "Executivo":

    st.title("Visão Executiva")

    # ── Cálculos-base para headline e KPIs ────────────────────────────────
    cart_ativa = df_cart[df_cart["status_cliente"] != "sem_compra"]
    cart_seg   = seg(cart_ativa)

    total_base   = len(cart_seg)
    ativos       = (cart_seg["status_cliente"] == "ativo").sum()
    em_risco     = (cart_seg["status_cliente"] == "em_risco").sum()
    hibernando   = cart_seg["status_cliente"].isin(["hibernando","hibernando_sazonal"]).sum()
    perdidos     = (cart_seg["status_cliente"] == "perdido").sum()
    pct_fora     = ((em_risco + hibernando + perdidos) / total_base * 100) if total_base else 0

    # Retenção m+1 dos últimos 6 cohorts (só para leitura de tese)
    coh_m1 = df_cohort[df_cohort["meses_desde_entrada"] == 1].sort_values("mes_entrada")
    retm1_recent = coh_m1.tail(6)["pct_retencao"].mean() if not coh_m1.empty else None
    retm1_prev   = coh_m1.iloc[-12:-6]["pct_retencao"].mean() if len(coh_m1) >= 12 else None

    # Valor em clientes recuperáveis (em risco + hibernando)
    valor_recup = cart_seg[cart_seg["status_cliente"].isin(
        ["em_risco","hibernando","hibernando_sazonal"]
    )]["valor_total_r"].sum()

    # ── Headline dinâmica ─────────────────────────────────────────────────
    parts = []
    parts.append(f"<b>{fmt_num(total_base)} clientes</b> na carteira, "
                 f"<b>{pct_fora:.0f}%</b> fora da janela de compra recente.")
    if retm1_recent is not None and retm1_prev is not None and retm1_recent < retm1_prev * 0.75:
        parts.append(f"Retenção m+1 caiu de <b>{retm1_prev:.0f}%</b> para "
                     f"<b>{retm1_recent:.0f}%</b> nos 6 cohorts mais recentes.")
    elif retm1_recent is not None:
        parts.append(f"Retenção m+1 média (últimos 6 cohorts): <b>{retm1_recent:.0f}%</b>.")
    parts.append(f"<b>{fmt_brl(valor_recup, compact=True)}</b> em clientes recuperáveis.")

    st.markdown(
        f"<div style='font-size:1.02rem; line-height:1.7; color:#222; "
        f"padding:14px 18px; background:#f8f9fa; border-left:4px solid #1A73E8; "
        f"border-radius:4px; margin-bottom:18px;'>"
        f"{' '.join(parts)}</div>",
        unsafe_allow_html=True,
    )

    # ── Cards de ação (navegação entre painéis) ──────────────────────────
    ca1, ca2, ca3, ca4 = st.columns(4)
    with ca1:
        if st.button("Top clientes para reativação →",
                     use_container_width=True, key="nav_reat"):
            st.session_state["_nav_target"] = "Estratégia de Carteira"
            st.rerun()
    with ca2:
        if st.button("Vendedores com carteira em risco →",
                     use_container_width=True, key="nav_vend"):
            st.session_state["_nav_target"] = "Vendedores"
            st.rerun()
    with ca3:
        if st.button("Cohorts e retenção →",
                     use_container_width=True, key="nav_cohort"):
            st.session_state["_nav_target"] = "Recorrência"
            st.rerun()
    with ca4:
        if st.button("Onde estão meus clientes →",
                     use_container_width=True, key="nav_demo"):
            st.session_state["_nav_target"] = "Demografia"
            st.rerun()

    st.divider()

    # Definições de status — expander discreto
    with st.expander("Definições de status de cliente", expanded=False):
        st.markdown("""
<div class="nota-status">
<b>Ativo</b> — última compra há menos de 90 dias<br>
<b>Em Risco</b> — última compra entre 91 e 180 dias<br>
<b>Hibernando</b> — última compra entre 181 e 365 dias<br>
<b>Hibernando Sazonal</b> — cliente sazonal que comprou na última temporada (out–mar) mas não nesta<br>
<b>Perdido</b> — última compra há mais de 365 dias<br>
<b>Sem compra</b> — cadastro sem nenhuma venda registrada
</div>
""", unsafe_allow_html=True)

    # ── KPIs com delta vs período anterior equivalente ────────────────────
    hoje = pd.Timestamp(date.today())
    fat_seg = seg(df_fat)
    fat_atual = fat_seg["valor_total_r"].sum()

    delta_fat_txt = None
    fat_full_seg = seg(df_fat_full)
    if not fat_seg.empty:
        mes_min = fat_seg["mes"].min()
        mes_max = fat_seg["mes"].max()
        meses_span = (mes_max.year - mes_min.year) * 12 + (mes_max.month - mes_min.month) + 1
        ant_max = mes_min - pd.DateOffset(months=1)
        ant_min = ant_max - pd.DateOffset(months=meses_span - 1)
        fat_ant = fat_full_seg[
            (fat_full_seg["mes"] >= ant_min) & (fat_full_seg["mes"] <= ant_max)
        ]["valor_total_r"].sum()
        if fat_ant > 0:
            delta_fat_txt = f"{(fat_atual - fat_ant) / fat_ant * 100:+.1f}% vs anterior"

    novos_30 = df_cart[(hoje - df_cart["primeira_compra"]).dt.days.between(0, 30)]
    novos_60 = df_cart[(hoje - df_cart["primeira_compra"]).dt.days.between(31, 60)]
    if seg_filter != "Todos":
        novos_30 = novos_30[novos_30["segmento"] == seg_filter]
        novos_60 = novos_60[novos_60["segmento"] == seg_filter]
    n_novos_30 = len(novos_30)
    n_novos_60 = len(novos_60)
    delta_novos_txt = f"{n_novos_30 - n_novos_60:+d} vs 30d anteriores" if n_novos_60 else None

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: st.metric("Ativos",         fmt_num(ativos))
    with c2: st.metric("Em Risco",        fmt_num(em_risco))
    with c3: st.metric("Hibernando",      fmt_num(hibernando))
    with c4: st.metric("Perdidos",        fmt_num(perdidos))
    with c5: st.metric("Faturamento (período)", fmt_brl(fat_atual, compact=True),
                       delta=delta_fat_txt)
    with c6: st.metric("Novos (30 dias)", fmt_num(n_novos_30),
                       delta=delta_novos_txt)

    # ── Faturamento mensal ─────────────────────────────────────────────────
    col_esq, col_dir = st.columns([3, 2])

    with col_esq:
        st.subheader("Faturamento mensal por segmento")
        fat_plot = seg(df_fat).groupby(["mes","segmento"], as_index=False)["valor_total_r"].sum()

        fig = px.area(
            fat_plot, x="mes", y="valor_total_r", color="segmento",
            color_discrete_map=CORES_SEG,
            labels={"mes":"","valor_total_r":"R$","segmento":"Segmento"},
        )
        fig.update_layout(
            height=300, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", y=-0.25, font_size=11),
            hovermode="x unified", plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_dir:
        st.subheader("Distribuição da carteira")
        status_counts = cart_seg.groupby("status_cliente").size().reset_index(name="n")
        status_val    = cart_seg.groupby("status_cliente")["valor_total_r"].sum().reset_index(name="valor")
        status_df     = status_counts.merge(status_val, on="status_cliente")
        status_df["label"] = status_df["status_cliente"].map(LABEL_STATUS)
        status_df["cor"]   = status_df["status_cliente"].map(CORES_STATUS)
        status_df = status_df.sort_values("n", ascending=True)

        status_df["rotulo"] = status_df.apply(
            lambda r: f"{fmt_num(r['n'])} · {fmt_brl(r['valor'], compact=True)}", axis=1
        )

        fig = go.Figure(go.Bar(
            x=status_df["n"],
            y=status_df["label"],
            orientation="h",
            marker_color=status_df["cor"],
            text=status_df["rotulo"],
            textposition="outside",
            cliponaxis=False,
        ))
        fig.update_layout(
            height=300, margin=dict(l=0, r=140, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            showlegend=False,
        )
        fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0", title_text="Clientes")
        fig.update_yaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    # ── Novos clientes ─────────────────────────────────────────────────────
    st.subheader("Novos clientes por mês")
    novos_plot = seg(df_novos).groupby(["mes_primeira_compra","segmento"], as_index=False)["novos_clientes"].sum()

    fig = px.bar(
        novos_plot, x="mes_primeira_compra", y="novos_clientes", color="segmento",
        color_discrete_map=CORES_SEG, barmode="stack",
        labels={"mes_primeira_compra":"","novos_clientes":"Novos clientes","segmento":"Segmento"},
    )
    fig.update_layout(
        height=260, margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h", y=-0.3, font_size=11),
        hovermode="x unified", plot_bgcolor="#fff", paper_bgcolor="#fff",
    )
    fig.update_yaxes(gridcolor="#f0f0f0")
    fig.update_xaxes(showgrid=False)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Concentração por UF e Ticket ──────────────────────────────────────
    col_uf, col_tkt = st.columns(2)

    with col_uf:
        st.subheader("Faturamento por UF — Top 12")
        uf_data = seg(cart_ativa)[["uf","id","valor_total_r"]].copy()
        uf_agg  = uf_data.groupby("uf", as_index=False).agg(
            clientes=("id","count"), valor=("valor_total_r","sum")
        )
        uf_agg = uf_agg[uf_agg["uf"].notna() & (uf_agg["uf"].str.len()==2)]
        uf_agg = uf_agg.nlargest(12,"valor")

        fig = px.bar(
            uf_agg.sort_values("valor"), x="valor", y="uf",
            orientation="h", color="valor",
            color_continuous_scale=[[0,"#d2e3fc"],[1,"#1A73E8"]],
            labels={"valor":"R$","uf":"UF"},
            text="clientes",
        )
        fig.update_traces(texttemplate="%{text} cli.", textposition="outside")
        fig.update_layout(
            height=340, margin=dict(l=0,r=60,t=10,b=0),
            coloraxis_showscale=False,
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_yaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_tkt:
        st.subheader("Distribuição de ticket médio")
        tkt_data = seg(cart_ativa).dropna(subset=["ticket_medio_r"])
        tkt_data = tkt_data[tkt_data["ticket_medio_r"] > 0]

        fig = px.histogram(
            tkt_data, x="ticket_medio_r", color="segmento",
            nbins=35, color_discrete_map=CORES_SEG,
            log_y=True, barmode="overlay",
            labels={"ticket_medio_r":"Ticket Médio (R$)","segmento":"Segmento"},
        )
        fig.update_traces(opacity=0.72)
        fig.update_layout(
            height=340, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", y=-0.3, font_size=11),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_xaxes(tickprefix="R$ ", showgrid=False)
        fig.update_yaxes(gridcolor="#f0f0f0")
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    # ── Cidades PE ────────────────────────────────────────────────────────
    st.subheader("Distribuição de clientes em Pernambuco — Top 20 cidades")
    _df_pe_filt = seg(df_pe)  # aplica filtro global de segmento
    _df_pe_agg = (
        _df_pe_filt.groupby("cidade", as_index=False)
        .agg(clientes=("clientes", "sum"),
             vendas=("vendas", "sum"),
             valor_r=("valor_r", "sum"))
        .sort_values("vendas", ascending=False)
    )
    pe_top = _df_pe_agg.head(20)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            name="Vendas", x=pe_top["cidade"], y=pe_top["vendas"],
            marker_color="#1A73E8", opacity=0.85,
        ), secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Faturamento", x=pe_top["cidade"], y=pe_top["valor_r"],
            mode="lines+markers", line=dict(color="#E8453C", width=2),
            marker=dict(size=6),
        ), secondary_y=True,
    )
    fig.update_layout(
        height=330, margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h", y=-0.35, font_size=11),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        xaxis_tickangle=-35, hovermode="x unified",
    )
    fig.update_yaxes(title_text="Vendas",        gridcolor="#f0f0f0", secondary_y=False)
    fig.update_yaxes(title_text="Faturamento R$", tickprefix="R$ ", secondary_y=True)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════
    # Alto valor (LTV) — patrimônio da carteira
    # ═══════════════════════════════════════════════════════════════════════
    st.subheader("Alto valor — patrimônio da carteira")

    with st.expander("O que é LTV e como interpretar", expanded=False):
        st.markdown("""
<div style='font-size:0.88rem; line-height:1.6; color:#333;'>
<b>LTV</b> = faturamento histórico total de cada cliente. Não decai com o tempo (diferente do RFV) — mede patrimônio.<br>
<b>Pareto</b>: quanto mais inclinada a curva no início, maior a dependência de poucos clientes. LTV alto + status fora de "Ativo" = patrimônio em risco.
</div>
""", unsafe_allow_html=True)

    ltv_base = df_cart[df_cart["status_cliente"] != "sem_compra"].copy()
    if seg_filter != "Todos":
        ltv_base = ltv_base[ltv_base["segmento"] == seg_filter]

    if ltv_base.empty:
        st.info("Sem clientes na base para o filtro atual.")
    else:
        ltv_base = ltv_base.sort_values("valor_total_r", ascending=False).reset_index(drop=True)
        ltv_total = ltv_base["valor_total_r"].sum()
        n_cli     = len(ltv_base)

        # Concentração Pareto: Top 20%
        n_top20 = max(1, int(round(n_cli * 0.20)))
        val_top20 = ltv_base.head(n_top20)["valor_total_r"].sum()
        pct_top20 = (val_top20 / ltv_total * 100) if ltv_total else 0

        # Patrimônio fora de ativo
        fora = ltv_base[ltv_base["status_cliente"] != "ativo"]
        val_fora = fora["valor_total_r"].sum()
        pct_fora = (val_fora / ltv_total * 100) if ltv_total else 0
        n_fora = len(fora)

        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric(
                "LTV total da carteira",
                fmt_brl(ltv_total, compact=True),
                help="Soma do faturamento histórico de todos os clientes que já compraram",
            )
        with k2:
            st.metric(
                "Concentração Top 20%",
                f"{pct_top20:.0f}%".replace(".", ","),
                help=f"% do LTV concentrado nos {fmt_num(n_top20)} maiores clientes",
            )
        with k3:
            st.metric(
                "Patrimônio fora de ativo",
                fmt_brl(val_fora, compact=True),
                delta=f"{fmt_num(n_fora)} clientes · {pct_fora:.0f}%".replace(".", ","),
                delta_color="inverse",
                help="LTV dos clientes em risco, hibernando ou perdidos",
            )

        # ── Top N clientes por LTV ────────────────────────────────────────
        top_n = 20
        topLTV = ltv_base.head(top_n).copy()
        topLTV["Status"]       = topLTV["status_cliente"].map(LABEL_STATUS)
        topLTV["LTV"]          = topLTV["valor_total_r"].apply(fmt_brl)
        topLTV["Ticket Medio"] = topLTV["ticket_medio_r"].apply(fmt_brl)
        topLTV["Ult. Compra"]  = topLTV["ultima_compra"].dt.strftime("%d/%m/%Y")

        def cor_status(val):
            m = {
                "Ativo":           "background-color:#e8f1ea;color:#2f5d3b",
                "Em Risco":        "background-color:#fbf3e0;color:#7a5a1f",
                "Hibernando":      "background-color:#f5e7d8;color:#7a4b20",
                "Perdido":         "background-color:#f2e3e2;color:#6b3a37",
                "Hibern. Sazonal": "background-color:#f5e7d8;color:#7a4b20",
            }
            return m.get(val, "")

        exib = topLTV.rename(columns={
            "nome_exibicao": "Cliente", "segmento": "Segmento",
            "cidade": "Cidade", "uf": "UF", "total_compras": "Compras",
        })[["Cliente", "Segmento", "Cidade", "UF", "Compras",
            "Ult. Compra", "LTV", "Ticket Medio", "Status"]]

        st.markdown(f"##### Top {top_n} clientes por LTV")
        st.dataframe(
            exib.style.map(cor_status, subset=["Status"]),
            use_container_width=True, height=430, hide_index=True,
        )
        botao_csv(
            ltv_base[["nome_exibicao", "segmento", "cidade", "uf", "status_cliente",
                      "total_compras", "ultima_compra",
                      "valor_total_r", "ticket_medio_r"]],
            "ltv_carteira_camboriu",
            "Exportar carteira completa por LTV (CSV)",
            key="csv_ltv_full",
        )

        # ── Curva de Pareto inline (linha fina) ───────────────────────────
        pareto = ltv_base[["valor_total_r"]].copy()
        pareto["cum_val"] = pareto["valor_total_r"].cumsum()
        pareto["pct_cum_val"] = pareto["cum_val"] / ltv_total * 100
        pareto["pct_cum_cli"] = (pareto.index + 1) / n_cli * 100

        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(
            x=pareto["pct_cum_cli"], y=pareto["pct_cum_val"],
            mode="lines", line=dict(color="#1A73E8", width=2.5),
            fill="tozeroy", fillcolor="rgba(26,115,232,0.08)",
            hovertemplate="Top %{x:.0f}% dos clientes → "
                          "%{y:.0f}% do LTV<extra></extra>",
            name="Curva de Pareto",
        ))
        # Linha diagonal (distribuição uniforme teórica)
        fig_p.add_trace(go.Scatter(
            x=[0, 100], y=[0, 100], mode="lines",
            line=dict(color="#ccc", dash="dot", width=1.2),
            hoverinfo="skip", showlegend=False,
        ))
        fig_p.add_vline(
            x=20, line_dash="dot", line_color="#888",
            annotation_text="Top 20%", annotation_position="top right",
        )
        fig_p.update_layout(
            height=240, margin=dict(l=0, r=0, t=24, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            showlegend=False,
            title=dict(
                text="<b>Curva de concentração (Pareto)</b> · "
                     "% acumulado de clientes × % acumulado de LTV",
                font=dict(size=12, color="#444"), x=0, xanchor="left", y=0.98,
            ),
        )
        fig_p.update_xaxes(range=[0, 100], ticksuffix="%",
                           gridcolor="#f0f0f0",
                           title_text="% acumulado de clientes (ordenados por LTV)")
        fig_p.update_yaxes(range=[0, 100], ticksuffix="%",
                           gridcolor="#f0f0f0",
                           title_text="% acumulado de LTV")
        apply_ptbr(fig_p)
        st.plotly_chart(fig_p, use_container_width=True)

        st.caption(
            f"Leitura: **os {fmt_num(n_top20)} maiores clientes (Top 20%) concentram "
            f"{pct_top20:.0f}% do LTV da carteira**. ".replace(".0%", "%")
            + f"Destes, **{fmt_brl(val_fora, compact=True)}** estão fora de ativo — é o "
              "patrimônio em risco que merece cuidado prioritário. Para acionar, "
              "veja o painel **Estratégia de Carteira**."
        )


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 2 — RECORRÊNCIA
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Recorrência":

    st.title("Recorrência e Comportamento")

    # ── KPIs de topo ─────────────────────────────────────────────────────
    cart_ativa = df_cart[df_cart["status_cliente"] != "sem_compra"]
    cart_seg_r = seg(cart_ativa)

    # Retenção m+1 (últimos 6 cohorts) — do df_cohort global
    coh_m1 = df_cohort[df_cohort["meses_desde_entrada"] == 1].sort_values("mes_entrada")
    retm1_atual  = coh_m1.tail(6)["pct_retencao"].mean() if len(coh_m1) >= 1 else None
    retm1_passado = coh_m1.iloc[-12:-6]["pct_retencao"].mean() if len(coh_m1) >= 12 else None
    delta_retm1 = (
        f"{retm1_atual - retm1_passado:+.1f}pp vs 6 cohorts anteriores"
        if (retm1_atual is not None and retm1_passado is not None) else None
    )

    # % clientes com 3+ compras
    n_total = len(cart_seg_r)
    n_3mais = (cart_seg_r["total_compras"] >= 3).sum()
    pct_3mais = (n_3mais / n_total * 100) if n_total else 0

    # Gap mediano entre compras (estimado: (ultima - primeira) / (compras - 1))
    rec_df = cart_seg_r[cart_seg_r["total_compras"] >= 2].copy()
    if not rec_df.empty:
        rec_df["gap"] = (
            (rec_df["ultima_compra"] - rec_df["primeira_compra"]).dt.days
            / (rec_df["total_compras"] - 1)
        )
        gap_mediana = rec_df["gap"].median()
    else:
        gap_mediana = None

    # Clientes com 1 compra só (nunca voltaram)
    n_unica = (cart_seg_r["total_compras"] == 1).sum()
    pct_unica = (n_unica / n_total * 100) if n_total else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Retenção m+1 (últimos 6 cohorts)",
            f"{retm1_atual:.1f}%".replace(".", ",") if retm1_atual is not None else "—",
            delta=delta_retm1,
        )
    with c2:
        st.metric("Clientes com 3+ compras", fmt_num(n_3mais),
                  delta=f"{pct_3mais:.1f}% da base".replace(".", ","))
    with c3:
        st.metric(
            "Gap mediano entre compras",
            f"{int(gap_mediana)} dias" if gap_mediana is not None else "—",
        )
    with c4:
        st.metric("Compraram 1 vez e não voltaram", fmt_num(n_unica),
                  delta=f"{pct_unica:.1f}% da base".replace(".", ","))

    st.divider()

    # ── Cohort ────────────────────────────────────────────────────────────
    st.subheader("Retenção por cohort — % de clientes que voltaram a comprar")
    st.caption("Cada linha = grupo pelo mês da 1ª compra · Coluna 0 = mês de entrada · +N = N meses depois")

    with st.expander("Como ler a matriz de cohort", expanded=False):
        st.markdown("""
<div style='font-size:0.88rem; line-height:1.6; color:#333;'>

<b>Cohort</b> é um grupo de clientes que entrou na carteira no mesmo mês (1ª compra).
A matriz mostra, para cada cohort, quantos <b>voltaram a comprar</b> nos meses seguintes.

<b>Exemplo:</b> se em <i>mar/2024</i> entraram 100 clientes e 40 deles compraram
novamente em algum momento de <i>abr/2024</i>, a retenção m+1 do cohort de mar/2024
é <b>40%</b>.

<b>Leitura da matriz:</b>

<ul style='margin-top:6px;'>
<li><b>Cada linha</b> = um cohort (mês de entrada na carteira)</li>
<li><b>Cada coluna</b> = meses decorridos desde a entrada (m0, m+1, m+2, …)</li>
<li><b>Cor mais escura</b> = retenção maior naquele ponto</li>
</ul>

<b>Por que m+1 importa tanto?</b> É o primeiro teste de fidelização. Se o cliente
não volta no mês seguinte, a probabilidade dele voltar depois cai muito. Uma
retenção m+1 crescente ao longo dos cohorts indica que a qualidade dos novos
clientes está melhorando; uma queda indica o oposto.

<b>Observação:</b> a retenção aqui é <b>não-acumulada</b> (cada célula conta só
quem comprou <i>naquele</i> mês específico). Por isso os números não somam 100%
entre colunas.

</div>
""", unsafe_allow_html=True)

    st.info(
        "Cohorts anteriores a mar/2024 foram omitidos — os primeiros meses da base "
        "incluíam clientes com histórico anterior ao período importado, o que inflava "
        "artificialmente a retenção e distorcia a comparação."
    )

    # Override local do segmento (explícito), default = filtro global da sidebar
    with st.expander("Segmento do cohort (opcional — sobrepõe o filtro global)", expanded=False):
        cohort_seg_sel = st.selectbox(
            "Segmento (cohort)",
            ["Usar filtro global", "Todos", "1 - Atacado", "2 - Varejo", "5 - Atacarejo"],
            key="cohort_seg_filter",
        )

    if cohort_seg_sel == "Usar filtro global":
        seg_efetivo = seg_filter
    else:
        seg_efetivo = cohort_seg_sel

    if seg_efetivo == "Todos":
        cohort_data = df_cohort
    else:
        cohort_data = df_cohort_seg[df_cohort_seg["segmento"] == seg_efetivo]
        orf_seg = df_orfas[df_orfas["segmento"] == seg_efetivo]
        if not orf_seg.empty:
            _tv = orf_seg["total_vendas"].sum()
            _to = orf_seg["vendas_orfas"].sum()
            _pct = (_to / _tv * 100) if _tv else 0
            if _pct > 20:
                st.warning(
                    f"{_pct:.0f}% das vendas de {seg_efetivo} são órfãs e não entram "
                    f"na análise de cohort. A retenção exibida reflete apenas clientes "
                    f"com CPF/CNPJ identificado."
                )

    if cohort_data.empty:
        st.info("Sem dados de cohort para este segmento.")
    else:
        pivot = cohort_data.pivot_table(
            index="mes_entrada", columns="meses_desde_entrada",
            values="pct_retencao", aggfunc="mean",
        )
        pivot_raw = pivot.copy()
        pivot.index = pd.to_datetime(pivot.index).strftime("%b/%Y")
        pivot = pivot.iloc[::-1]
        z_text = pivot.map(lambda v: f"{v:.0f}%" if pd.notna(v) else "")

        fig = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[f"+{c}m" for c in pivot.columns],
            y=pivot.index.tolist(),
            text=z_text.values,
            texttemplate="%{text}",
            colorscale=[[0,"#EA4335"],[0.15,"#FBBC04"],[0.40,"#34A853"],[1.0,"#1A73E8"]],
            zmin=0, zmax=100,
            colorbar=dict(title="% ret."),
        ))
        fig.update_layout(
            height=max(320, len(pivot)*30),
            margin=dict(l=0,r=0,t=10,b=0),
            xaxis_title="Meses desde 1ª compra",
            paper_bgcolor="#fff",
        )
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

        # ── Linha-resumo: retenção média por trimestre de entrada ─────────
        resumo_tri = cohort_data.assign(
            tri=pd.to_datetime(cohort_data["mes_entrada"]).dt.to_period("Q").astype(str)
        ).groupby(["tri","meses_desde_entrada"])["pct_retencao"].mean().unstack()

        if not resumo_tri.empty:
            st.markdown("**Retenção média por trimestre de entrada — leitura de tendência**")
            fig = go.Figure()
            cores_m = {1: "#1A73E8", 3: "#34A853", 6: "#F9AB00"}
            for m in [1, 3, 6]:
                if m in resumo_tri.columns:
                    fig.add_trace(go.Scatter(
                        x=resumo_tri.index, y=resumo_tri[m],
                        name=f"m+{m}", mode="lines+markers",
                        line=dict(color=cores_m[m], width=2.5),
                        marker=dict(size=8),
                    ))
            fig.update_layout(
                height=260, margin=dict(l=0,r=0,t=10,b=0),
                hovermode="x unified",
                plot_bgcolor="#fff", paper_bgcolor="#fff",
                legend=dict(orientation="h", y=-0.3, font_size=11),
                xaxis_title="Trimestre de entrada do cohort",
                yaxis_title="% retenção média",
            )
            fig.update_yaxes(ticksuffix="%", gridcolor="#f0f0f0", rangemode="tozero")
            fig.update_xaxes(showgrid=False)
            apply_ptbr(fig)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Frequência e dispersão ────────────────────────────────────────────
    col_freq, col_disp = st.columns(2)

    with col_freq:
        st.subheader("Frequência de compra por segmento")
        freq_d = seg(df_cart[df_cart["status_cliente"]!="sem_compra"])
        freq_agg = freq_d.groupby(["faixa_frequencia","segmento"], as_index=False).size()

        fig = px.bar(
            freq_agg.sort_values("faixa_frequencia"),
            x="faixa_frequencia", y="size", color="segmento",
            color_discrete_map=CORES_SEG, barmode="group",
            labels={"faixa_frequencia":"","size":"Clientes","segmento":"Segmento"},
        )
        fig.update_layout(
            height=300, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h",y=-0.35,font_size=11),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis_tickangle=-15,
        )
        fig.update_yaxes(gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_disp:
        st.subheader("Ticket mediano × Frequência")
        disp_d = seg(df_cart[
            (df_cart["status_cliente"]!="sem_compra") &
            df_cart["ticket_medio_r"].notna() &
            (df_cart["ticket_medio_r"]>0)
        ])
        disp_agg = disp_d.groupby(["total_compras","segmento"], as_index=False).agg(
            clientes=("id","count"), ticket=("ticket_medio_r","median"),
        )
        disp_agg = disp_agg[disp_agg["total_compras"]<=25]

        fig = px.scatter(
            disp_agg, x="total_compras", y="ticket",
            color="segmento", size="clientes",
            color_discrete_map=CORES_SEG,
            labels={"total_compras":"Nº de compras","ticket":"Ticket mediano (R$)","segmento":""},
        )
        fig.update_layout(
            height=300, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h",y=-0.35,font_size=11),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_yaxes(tickprefix="R$ ", gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Mix de pagamento — simplificado ───────────────────────────────────
    st.subheader("Mix de forma de pagamento")

    # Consolida: top 4 + MISTO (todos) + OUTROS
    def _consolidar_pag(forma):
        principais = {"CARTÃO CRÉDITO","PIX","DINHEIRO","CARTÃO DÉBITO"}
        if forma in principais:
            return forma
        if str(forma).startswith("MISTO"):
            return "MISTO"
        return "OUTROS"

    pag_d = seg(df_pag).copy()
    pag_d["metodo"] = pag_d["forma_pagamento_norm"].apply(_consolidar_pag)

    ORDEM_PAG = ["CARTÃO CRÉDITO","PIX","DINHEIRO","CARTÃO DÉBITO","MISTO","OUTROS"]
    CORES_PAG  = {
        "CARTÃO CRÉDITO": "#1A73E8",
        "PIX":            "#34A853",
        "DINHEIRO":       "#F9AB00",
        "CARTÃO DÉBITO":  "#E8453C",
        "MISTO":          "#9C27B0",
        "OUTROS":         "#BDC1C6",
    }

    col_pie, col_evo = st.columns([1,2])

    with col_pie:
        pag_tot = pag_d.groupby("metodo", as_index=False)["valor_total_r"].sum()
        pag_tot["ord"] = pag_tot["metodo"].map({v:i for i,v in enumerate(ORDEM_PAG)})
        pag_tot = pag_tot.sort_values("ord")

        fig = go.Figure(go.Pie(
            labels=pag_tot["metodo"], values=pag_tot["valor_total_r"],
            marker_colors=[CORES_PAG[m] for m in pag_tot["metodo"]],
            hole=0.42, textinfo="label+percent",
        ))
        fig.update_layout(
            height=320, margin=dict(l=0,r=0,t=10,b=0),
            showlegend=False, paper_bgcolor="#fff",
        )
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_evo:
        pag_evo = pag_d.groupby(["mes","metodo"], as_index=False)["qtd_vendas"].sum()
        pag_evo["ord"] = pag_evo["metodo"].map({v:i for i,v in enumerate(ORDEM_PAG)})
        pag_evo = pag_evo.sort_values(["mes","ord"])

        fig = px.bar(
            pag_evo, x="mes", y="qtd_vendas", color="metodo",
            color_discrete_map=CORES_PAG,
            category_orders={"metodo": ORDEM_PAG},
            barmode="stack",
            labels={"mes":"","qtd_vendas":"Vendas","metodo":"Método"},
        )
        fig.update_layout(
            height=320, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h",y=-0.35,font_size=11),
            hovermode="x unified",
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_yaxes(gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    # ── Parcelas ──────────────────────────────────────────────────────────
    st.subheader("Distribuição de parcelas — Cartão de crédito")
    parc_d = seg(pag_d[
        pag_d["forma_pagamento_norm"].str.contains("CRÉDITO", na=False) &
        pag_d["parcelas"].notna()
    ])
    parc_agg = parc_d.groupby("parcelas", as_index=False).agg(
        vendas=("qtd_vendas","sum"), valor=("valor_total_r","sum"),
    )

    fig = make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_trace(go.Bar(
        x=parc_agg["parcelas"], y=parc_agg["vendas"],
        name="Vendas", marker_color="#1A73E8",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=parc_agg["parcelas"], y=parc_agg["valor"],
        name="Valor R$", mode="lines+markers",
        line=dict(color="#E8453C", width=2), marker=dict(size=6),
    ), secondary_y=True)
    fig.update_layout(
        height=270, margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h",y=-0.3,font_size=11),
        hovermode="x unified",
        plot_bgcolor="#fff", paper_bgcolor="#fff",
    )
    fig.update_xaxes(title_text="Parcelas", dtick=1, showgrid=False)
    fig.update_yaxes(title_text="Qtd vendas", gridcolor="#f0f0f0", secondary_y=False)
    fig.update_yaxes(title_text="Valor R$",   tickprefix="R$ ",    secondary_y=True)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 3 — SAZONALIDADE
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Sazonalidade":

    st.title("Análise de Sazonalidade")
    st.caption("Moda praia tem pico de out–jan. Esta seção mostra como isso se reflete nas vendas e na carteira.")

    fat_saz = seg(df_fat).copy()
    fat_saz["mes_num"] = fat_saz["mes"].dt.month
    fat_saz["ano"]     = fat_saz["mes"].dt.year
    fat_saz["mes_abr"] = fat_saz["mes_num"].map(MESES_PT)

    # ── Heatmap faturamento mês × ano ─────────────────────────────────────
    st.subheader("Faturamento mensal — mapa de calor por mês e ano")

    heat_agg = fat_saz.groupby(["mes_num","mes_abr","ano"], as_index=False)["valor_total_r"].sum()
    pivot_h  = heat_agg.pivot_table(index="mes_num", columns="ano", values="valor_total_r", aggfunc="sum")
    pivot_h.index = [MESES_PT[i] for i in pivot_h.index]

    # Texto formatado pt-BR para o heatmap
    z_text_h = pivot_h.map(
        lambda v: fmt_brl(v, compact=True) if pd.notna(v) else ""
    )

    fig = go.Figure(go.Heatmap(
        z=pivot_h.values,
        x=[str(int(c)) for c in pivot_h.columns],
        y=pivot_h.index.tolist(),
        text=z_text_h.values,
        texttemplate="%{text}",
        colorscale=[[0,"#f8f9fa"],[0.3,"#d2e3fc"],[0.65,"#4285F4"],[1,"#0d47a1"]],
        colorbar=dict(title="R$"),
    ))
    fig.update_layout(
        height=380, margin=dict(l=0,r=0,t=10,b=0),
        xaxis_title="Ano",
        yaxis_title="",
        paper_bgcolor="#fff",
    )
    # Ordena eixo Y: Jan no topo (mês 1 → índice mais alto)
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(list(MESES_PT.values()))))
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)

    # ── Média por mês (índice de sazonalidade) ───────────────────────────
    col_idx, col_lin = st.columns(2)

    with col_idx:
        st.subheader("Faturamento médio por mês (2024–2025)")
        med_mes = fat_saz[fat_saz["ano"].isin([2024,2025])].groupby(
            ["mes_num","mes_abr"], as_index=False
        )["valor_total_r"].mean().sort_values("mes_num")

        media_geral = med_mes["valor_total_r"].mean()
        med_mes["indice"] = (med_mes["valor_total_r"] / media_geral * 100).round(1)
        med_mes["cor"] = med_mes["indice"].apply(
            lambda x: "#1A73E8" if x >= 110 else ("#F9AB00" if x >= 85 else "#E8453C")
        )

        fig = go.Figure(go.Bar(
            x=med_mes["mes_abr"],
            y=med_mes["valor_total_r"],
            marker_color=med_mes["cor"],
            text=med_mes["indice"].apply(lambda x: f"{fmt_num(x,0)}"),
            textposition="outside",
        ))
        fig.add_hline(y=media_geral, line_dash="dot", line_color="#999",
                      annotation_text="Média", annotation_position="right")
        fig.update_layout(
            height=310, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Números = índice de sazonalidade (100 = média) | Azul ≥ 110 (acima) · Amarelo 85–110 (próximo) · Vermelho < 85 (abaixo)")

    with col_lin:
        st.subheader("Evolução mês a mês — 2024 vs 2025")
        comp = fat_saz[fat_saz["ano"].isin([2024,2025])].groupby(
            ["mes_num","mes_abr","ano"], as_index=False
        )["valor_total_r"].sum().sort_values("mes_num")

        fig = go.Figure()
        for ano, cor in [(2024,"#BDC1C6"),(2025,"#1A73E8")]:
            d = comp[comp["ano"]==ano]
            fig.add_trace(go.Scatter(
                x=d["mes_abr"], y=d["valor_total_r"],
                name=str(ano), mode="lines+markers",
                line=dict(color=cor, width=2.5),
                marker=dict(size=7),
            ))
        fig.update_layout(
            height=310, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h",y=-0.3),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            hovermode="x unified",
        )
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Clientes sazonais vs regulares ────────────────────────────────────
    st.subheader("Clientes sazonais vs regulares")
    st.caption("Cliente sazonal: 80%+ das compras concentradas nos meses de pico (out–mar)")

    cart_ativa = df_cart[df_cart["status_cliente"] != "sem_compra"]
    cart_seg_s = seg(cart_ativa)

    col_s1, col_s2, col_s3 = st.columns(3)
    n_saz = (cart_seg_s["perfil_sazonalidade"]=="Sazonal").sum()
    n_reg = (cart_seg_s["perfil_sazonalidade"]=="Regular").sum()
    tkt_saz = cart_seg_s[cart_seg_s["perfil_sazonalidade"]=="Sazonal"]["ticket_medio_r"].mean()
    tkt_reg = cart_seg_s[cart_seg_s["perfil_sazonalidade"]=="Regular"]["ticket_medio_r"].mean()
    freq_saz = cart_seg_s[cart_seg_s["perfil_sazonalidade"]=="Sazonal"]["total_compras"].mean()
    freq_reg = cart_seg_s[cart_seg_s["perfil_sazonalidade"]=="Regular"]["total_compras"].mean()

    with col_s1:
        st.metric("Clientes sazonais", fmt_num(n_saz))
        st.metric("Clientes regulares", fmt_num(n_reg))
    with col_s2:
        st.metric("Ticket médio sazonal",  fmt_brl(tkt_saz))
        st.metric("Ticket médio regular",  fmt_brl(tkt_reg))
    with col_s3:
        st.metric("Freq. média sazonal",  f"{freq_saz:.1f} compras".replace(".",",") if pd.notna(freq_saz) else "—")
        st.metric("Freq. média regular",  f"{freq_reg:.1f} compras".replace(".",",") if pd.notna(freq_reg) else "—")

    # Barras: status por perfil
    saz_status = cart_seg_s.groupby(["perfil_sazonalidade","status_cliente"], as_index=False).size()
    saz_status["label"] = saz_status["status_cliente"].map(LABEL_STATUS)

    fig = px.bar(
        saz_status, x="perfil_sazonalidade", y="size", color="label",
        color_discrete_map={v:CORES_STATUS[k] for k,v in LABEL_STATUS.items()},
        barmode="group",
        labels={"perfil_sazonalidade":"Perfil","size":"Clientes","label":"Status"},
        category_orders={"label":["Ativo","Em Risco","Hibernando","Hibern. Sazonal","Perdido"]},
    )
    fig.update_layout(
        height=300, margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h",y=-0.35,font_size=11),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
    )
    fig.update_yaxes(gridcolor="#f0f0f0")
    fig.update_xaxes(showgrid=False)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 4 — ESTRATÉGIA DE CARTEIRA
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Estratégia de Carteira":

    st.title("Estratégia de Carteira")
    st.caption(
        "Decide onde investir atenção: quem manter, quem reativar, quem recuperar "
        "e quem monitorar. Cruza o valor do cliente (score VF) com o status atual."
    )

    # ── Calcula score RFV sobre TODA a carteira ativa ────────────────────
    base_rfv = df_cart[df_cart["status_cliente"] != "sem_compra"].copy()
    if seg_filter != "Todos":
        base_rfv = base_rfv[base_rfv["segmento"] == seg_filter]

    vend_map = (
        df_cart[["id", "nome_exibicao"]]
        .merge(df_cli_vend, left_on="id", right_on="cliente_id", how="inner")
        .drop_duplicates("nome_exibicao")
        .set_index("nome_exibicao")["vendedor_principal"]
    )

    if base_rfv.empty:
        st.info("Sem clientes na carteira ativa para o filtro atual.")
        st.stop()

    base_rfv = calcular_score_rfv(base_rfv)
    base_rfv["vendedor"] = base_rfv["nome_exibicao"].map(vend_map)

    # ── KPIs de topo ─────────────────────────────────────────────────────
    n_total     = len(base_rfv)
    val_total   = base_rfv["valor_total_r"].sum()
    fora_ativo  = base_rfv[base_rfv["status_cliente"] != "ativo"]
    val_risco   = fora_ativo["valor_total_r"].sum()
    n_risco     = len(fora_ativo)
    pct_val_risco = (val_risco / val_total * 100) if val_total else 0

    # Valor histórico concentrado em Camada A (patrimônio sensível)
    val_cam_a   = base_rfv[base_rfv["camada"] == "A — Alto valor"]["valor_total_r"].sum()
    pct_cam_a   = (val_cam_a / val_total * 100) if val_total else 0

    # ── Snapshot da carteira ativa (KPIs neutros, contexto de tudo que vem) ──
    st.markdown(
        "<div style='font-size:0.72rem; font-weight:700; letter-spacing:0.1em; "
        "text-transform:uppercase; color:#5f6368; margin:20px 0 4px;'>"
        "Carteira ativa · snapshot atual</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Clientes ativos na base", fmt_num(n_total))
    with c2: st.metric("Valor histórico total", fmt_brl(val_total, compact=True))
    with c3:
        st.metric(
            "Patrimônio fora de ativo",
            fmt_brl(val_risco, compact=True),
            delta=f"{pct_val_risco:.0f}% da carteira".replace(".", ","),
            delta_color="inverse",
            help="Valor histórico acumulado dos clientes em risco, hibernando ou perdidos",
        )
    with c4:
        st.metric(
            "Concentração na Camada A",
            f"{pct_cam_a:.0f}%".replace(".", ","),
            help="% do valor histórico concentrado nos Top 5% de clientes",
        )
    st.markdown(
        "<div style='border-bottom:1px solid #e6e8eb; margin:8px 0 0;'></div>",
        unsafe_allow_html=True,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCO 1 · DEFENDER A CARTEIRA (matriz RFV × status)
    # ═══════════════════════════════════════════════════════════════════════
    st.markdown(
        "<div style='margin:32px 0 16px; padding:14px 18px; background:#fff; "
        "border-left:4px solid #1A73E8; border-top:1px solid #eef0f2; "
        "border-right:1px solid #eef0f2; border-bottom:1px solid #eef0f2; "
        "border-radius:4px;'>"
        "<div style='font-size:0.7rem; font-weight:700; letter-spacing:0.12em; "
        "text-transform:uppercase; color:#1A73E8;'>Bloco 1 · Proteger e reativar</div>"
        "<div style='font-size:1.35rem; font-weight:700; margin-top:2px; line-height:1.2; color:#111;'>"
        "Carteira atual</div>"
        "<div style='font-size:0.88rem; color:#5f6368; margin-top:2px;'>"
        "Receita que já existe e risco de fuga.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Metodologia: score de valor, status e matriz de ação", expanded=False):
        st.markdown("""
<div style='font-size:0.88rem; line-height:1.6; color:#333;'>

<b>Score de valor</b> mede o quanto um cliente vale para a empresa,
independentemente de quando ele comprou pela última vez:

<ul style='margin-top:6px; margin-bottom:10px;'>
<li><b>Valor (peso 70%)</b> — quanto ele gasta por compra, comparado à média do segmento dele</li>
<li><b>Frequência (peso 30%)</b> — quantas compras fez, comparado à mediana do segmento</li>
</ul>

A recência <b>não</b> entra aqui — fica no eixo de status da matriz. Assim, um
cliente de alto ticket que ficou parado não "perde pontos de valor" por estar
parado: ele aparece em <b>A × Perdido</b>, que é exatamente o alvo da
recuperação prioritária.

Em Out–Dez, clientes com perfil sazonal ganham bônus de prioridade — é a janela
natural de compra deles.

O score é <b>relativo à carteira ativa atual</b> e separa os clientes em três camadas:
<b>A — Alto valor (Top 5%)</b>, <b>B — Médio valor (6 a 20%)</b> e <b>C — Base (restante)</b>.

<div style='margin-top:14px; padding-top:10px; border-top:1px solid #eee;'>
<b>Status de cliente</b> (baseado na recência da última compra):
<ul style='margin-top:6px; margin-bottom:10px;'>
<li><b>Ativo</b> — última compra há menos de 90 dias</li>
<li><b>Em Risco</b> — última compra entre 91 e 180 dias</li>
<li><b>Hibernando</b> — última compra entre 181 e 365 dias</li>
<li><b>Hibernando Sazonal</b> — cliente sazonal que comprou na última temporada mas não na atual</li>
<li><b>Perdido</b> — última compra há mais de 365 dias</li>
</ul>
</div>

<div style='margin-top:14px; padding-top:10px; border-top:1px solid #eee;'>
<b>Matriz de ação</b> combina a camada RFV (linhas) com o status comercial (colunas).
Cada célula corresponde a uma ação diferente:

<ul style='margin-top:6px;'>
<li><b>Manutenção</b> (clientes ativos) — cuidar para não perder, fidelizar</li>
<li><b>Reativação</b> (em risco, 91–180 dias) — contato rápido, janela quente</li>
<li><b>Recuperação</b> (hibernando, 181–365 dias) — abordagem estruturada</li>
<li><b>Monitoramento</b> (perdidos, +365 dias) — avaliar se vale o esforço</li>
</ul>

A prioridade dentro de cada ação segue a camada: <b>A</b> é prioritária, <b>B</b> é
padrão e <b>C</b> é baixa prioridade (normalmente resolvido com automação).
</div>

</div>
""", unsafe_allow_html=True)

    CAMADAS_ORD = ["A — Alto valor", "B — Médio valor", "C — Base"]
    STATUS_ORD  = ["ativo", "em_risco", "hibernando", "hibernando_sazonal", "perdido"]
    STATUS_LBL  = {
        "ativo":              "Ativo",
        "em_risco":           "Em Risco",
        "hibernando":         "Hibernando",
        "hibernando_sazonal": "Hibern. Sazonal",
        "perdido":            "Perdido",
    }
    # Agrupa Hibernando + Hibern. Sazonal na mesma coluna da matriz (ação idêntica)
    base_rfv["status_matriz"] = base_rfv["status_cliente"].replace(
        {"hibernando_sazonal": "hibernando"}
    )
    STATUS_MATRIZ = ["ativo", "em_risco", "hibernando", "perdido"]
    STATUS_MATRIZ_LBL = {
        "ativo":      "Ativo",
        "em_risco":   "Em Risco",
        "hibernando": "Hibernando",
        "perdido":    "Perdido",
    }
    # Rótulos estratégicos (camada, status) → ação
    ACAO_MATRIZ = {
        ("A — Alto valor",  "ativo"):      "Manutenção prioritária",
        ("A — Alto valor",  "em_risco"):   "Reativação prioritária",
        ("A — Alto valor",  "hibernando"): "Recuperação prioritária",
        ("A — Alto valor",  "perdido"):    "Ex-estratégicos",
        ("B — Médio valor", "ativo"):      "Manutenção",
        ("B — Médio valor", "em_risco"):   "Reativação",
        ("B — Médio valor", "hibernando"): "Recuperação",
        ("B — Médio valor", "perdido"):    "Perdidos relevantes",
        ("C — Base",        "ativo"):      "Monitoramento",
        ("C — Base",        "em_risco"):   "Atenção",
        ("C — Base",        "hibernando"): "Baixa prioridade",
        ("C — Base",        "perdido"):    "Baixa prioridade",
    }
    CORES_MATRIZ = {
        ("A — Alto valor",  "ativo"):      "#0d47a1",
        ("A — Alto valor",  "em_risco"):   "#b00020",
        ("A — Alto valor",  "hibernando"): "#d84315",
        ("A — Alto valor",  "perdido"):    "#5f6368",
        ("B — Médio valor", "ativo"):      "#1A73E8",
        ("B — Médio valor", "em_risco"):   "#E8453C",
        ("B — Médio valor", "hibernando"): "#F9AB00",
        ("B — Médio valor", "perdido"):    "#80868B",
        ("C — Base",        "ativo"):      "#80cbc4",
        ("C — Base",        "em_risco"):   "#ffcc80",
        ("C — Base",        "hibernando"): "#e0e0e0",
        ("C — Base",        "perdido"):    "#bdbdbd",
    }

    # ── Constrói a grade CSS 3×4 com contagem + valor por célula ──────────
    if "celula_selecionada" not in st.session_state:
        st.session_state["celula_selecionada"] = None

    # Header: status
    header_cols = st.columns([1.3] + [1] * len(STATUS_MATRIZ))
    with header_cols[0]:
        st.markdown(
            "<div style='font-size:0.75rem; color:#888; font-weight:600; "
            "text-transform:uppercase; letter-spacing:0.06em; padding:4px 0;'>"
            "Camada ↓ &nbsp;/&nbsp; Status →</div>",
            unsafe_allow_html=True,
        )
    for i, sx in enumerate(STATUS_MATRIZ):
        with header_cols[i + 1]:
            st.markdown(
                f"<div style='text-align:center; font-size:0.82rem; font-weight:600; "
                f"color:#222; padding:4px 0; border-bottom:1px solid #eee;'>"
                f"{STATUS_MATRIZ_LBL[sx]}</div>",
                unsafe_allow_html=True,
            )

    # Linhas da matriz
    for cam in CAMADAS_ORD:
        row = st.columns([1.3] + [1] * len(STATUS_MATRIZ))
        with row[0]:
            cor_cam = {"A — Alto valor": "#1A73E8",
                       "B — Médio valor": "#F9AB00",
                       "C — Base": "#BDC1C6"}[cam]
            st.markdown(
                f"<div style='padding:22px 10px 0 0; text-align:right; "
                f"border-right:4px solid {cor_cam};'>"
                f"<div style='font-size:0.88rem; font-weight:700; color:#222;'>{cam}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        for i, sx in enumerate(STATUS_MATRIZ):
            with row[i + 1]:
                sub = base_rfv[
                    (base_rfv["camada"] == cam) & (base_rfv["status_matriz"] == sx)
                ]
                n = len(sub)
                v = sub["valor_total_r"].sum()
                acao = ACAO_MATRIZ[(cam, sx)]
                cor = CORES_MATRIZ[(cam, sx)]
                selecionado = st.session_state["celula_selecionada"] == (cam, sx)
                borda = "2px solid #111" if selecionado else "1px solid #e0e0e0"
                bg    = "#fff"
                opacidade_barra = "0.12"

                st.markdown(
                    f"""<div style='position:relative; padding:12px 12px; border:{borda};
                        border-radius:6px; background:{bg}; min-height:96px;
                        margin-bottom:2px; overflow:hidden;'>
<div style='position:absolute; top:0; left:0; right:0; height:3px; background:{cor};'></div>
<div style='font-size:0.72rem; color:#666; font-weight:600; text-transform:uppercase;
    letter-spacing:0.03em; margin-top:2px;'>{acao}</div>
<div style='font-size:1.35rem; font-weight:700; color:#111; line-height:1.1; margin-top:4px;'>
    {fmt_num(n)}</div>
<div style='font-size:0.78rem; color:#555; margin-top:2px;'>
    {fmt_brl(v, compact=True)}</div>
</div>""",
                    unsafe_allow_html=True,
                )

                if n > 0:
                    key_btn = f"sel_{cam}_{sx}".replace(" ", "_").replace("—", "d")
                    if st.button(
                        "Filtrar fila ↓" if not selecionado else "✓ selecionado",
                        key=key_btn, use_container_width=True,
                    ):
                        if selecionado:
                            st.session_state["celula_selecionada"] = None
                        else:
                            st.session_state["celula_selecionada"] = (cam, sx)
                        st.rerun()

    # Botão para limpar seleção
    if st.session_state["celula_selecionada"] is not None:
        if st.button("Limpar seleção da matriz", key="limpar_matriz"):
            st.session_state["celula_selecionada"] = None
            st.rerun()

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════
    # Fila detalhada — filtrada por célula (se houver) + filtros auxiliares
    # ═══════════════════════════════════════════════════════════════════════
    sel = st.session_state["celula_selecionada"]
    if sel:
        cam_sel, st_sel_cell = sel
        acao_sel = ACAO_MATRIZ[sel]
        st.subheader(f"Fila · {acao_sel}")
        st.caption(
            f"Filtrado pela matriz: **{cam_sel}** × **{STATUS_MATRIZ_LBL[st_sel_cell]}**"
        )
    else:
        st.subheader("Fila completa — carteira ativa")
        st.caption("Toda a base ativa ordenada por score de valor (VF). Clique em uma "
                   "célula da matriz para filtrar.")

    fila = base_rfv.copy()
    if sel:
        cam_sel, st_sel_cell = sel
        fila = fila[
            (fila["camada"] == cam_sel) & (fila["status_matriz"] == st_sel_cell)
        ]

    # Filtros secundários
    f1, f2 = st.columns(2)
    with f1:
        ufs_opts = ["Todos"] + sorted(fila["uf"].dropna().unique().tolist())
        uf_sel = st.selectbox("UF", ufs_opts, key="fila_uf")
    with f2:
        vend_opts = ["Todos"] + sorted(fila["vendedor"].dropna().unique().tolist())
        vend_sel = st.selectbox("Vendedor", vend_opts, key="fila_vend")

    if uf_sel != "Todos":
        fila = fila[fila["uf"] == uf_sel]
    if vend_sel != "Todos":
        fila = fila[fila["vendedor"] == vend_sel]

    fila = fila.sort_values("score", ascending=False)

    if fila.empty:
        st.info("Sem clientes para os filtros atuais.")
    else:
        exib = fila.copy()
        exib["Fat. Total"]    = exib["valor_total_r"].apply(fmt_brl)
        exib["Ticket Medio"]  = exib["ticket_medio_r"].apply(fmt_brl)
        exib["Ult. Compra"]   = exib["ultima_compra"].dt.strftime("%d/%m/%Y")
        exib["Status"]        = exib["status_cliente"].map(LABEL_STATUS)
        exib["Score"]         = exib["score"].apply(
            lambda v: f"{float(v):.2f}".replace(".", ",") if pd.notna(v) else "—"
        )
        exib["Camada"] = exib["camada"].astype("object").fillna("—")
        exib["Vendedor"] = exib["vendedor"].fillna("—")
        exib = exib.rename(columns={
            "nome_exibicao": "Cliente",
            "segmento": "Segmento",
            "cidade": "Cidade",
            "uf": "UF",
            "total_compras": "Compras",
            "dias_sem_compra": "Dias s/comprar",
        })[["Cliente", "Segmento", "Cidade", "UF", "Vendedor",
            "Status", "Camada", "Score", "Ult. Compra",
            "Dias s/comprar", "Compras", "Fat. Total", "Ticket Medio"]]

        def _bg_status(val):
            m = {
                "Em Risco":         "background-color:#fbf3e0",
                "Hibernando":       "background-color:#f5e7d8",
                "Perdido":          "background-color:#f2e3e2",
                "Hibern. Sazonal":  "background-color:#f5e7d8",
                "Ativo":            "background-color:#e8f1ea",
            }
            return m.get(val, "")

        def _bg_cam(val):
            m = {
                "A — Alto valor":  "background-color:#e4ecf7;color:#1e3a5f;font-weight:600",
                "B — Médio valor": "background-color:#fbf3e0;color:#7a5a1f",
                "C — Base":        "background-color:#f4f5f6;color:#555",
            }
            return m.get(str(val), "")

        st.dataframe(
            exib.style.map(_bg_status, subset=["Status"]).map(_bg_cam, subset=["Camada"]),
            use_container_width=True, height=460, hide_index=True,
        )
        n_str = f"{len(exib):,}".replace(",", ".")
        val_fila = fila["valor_total_r"].sum()
        st.caption(
            f"{n_str} clientes · {fmt_brl(val_fila, compact=True)} em valor histórico "
            "· Vendedor = funcionário/vendedor predominante por nº de vendas fechadas"
        )

        csv_nome = "fila_estrategia"
        if sel:
            csv_nome = ("fila_" + ACAO_MATRIZ[sel]
                        .lower().replace(" ", "_").replace("ã","a").replace("é","e"))

        _col_csv1, _col_csv2 = st.columns([1, 1])
        with _col_csv1:
            botao_csv(
                fila[["nome_exibicao", "segmento", "cidade", "uf", "vendedor",
                      "status_cliente", "camada", "score", "ultima_compra",
                      "dias_sem_compra", "total_compras",
                      "valor_total_r", "ticket_medio_r"]],
                csv_nome, "Exportar fila (CSV)", key="csv_fila_estrat",
            )
        with _col_csv2:
            # Export Trello-ready precisa das colunas de identificação (id,
            # documento_norm) para enriquecimento com contatos.
            _fila_trello = fila[[
                "id", "nome_exibicao", "vendedor", "status_cliente", "camada",
                "valor_total_r", "ticket_medio_r", "total_compras",
                "dias_sem_compra", "ultima_compra", "cidade", "uf",
                "documento_norm",
            ]].copy()
            botao_csv_trello(
                _fila_trello, csv_nome,
                "Exportar para Trello (CSV)", key="csv_fila_estrat_trello",
            )

    # ── Maximização de receita ───────────────────────────────────────────
    st.markdown(
        "<div style='margin:48px 0 16px; padding:14px 18px; background:#fff; "
        "border-left:4px solid #2d6a4f; border-top:1px solid #eef0f2; "
        "border-right:1px solid #eef0f2; border-bottom:1px solid #eef0f2; "
        "border-radius:4px;'>"
        "<div style='font-size:0.7rem; font-weight:700; letter-spacing:0.12em; "
        "text-transform:uppercase; color:#2d6a4f;'>Bloco 2 · Expandir</div>"
        "<div style='font-size:1.35rem; font-weight:700; margin-top:2px; line-height:1.2; color:#111;'>"
        "Próxima receita</div>"
        "<div style='font-size:0.88rem; color:#5f6368; margin-top:2px;'>"
        "Converter compra pontual em recorrência.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    from geo import classificar_tipologia

    hoje = pd.Timestamp(date.today())
    base_estrat = df_cart[df_cart["status_cliente"] != "sem_compra"].copy()
    if seg_filter != "Todos":
        base_estrat = base_estrat[base_estrat["segmento"] == seg_filter]

    try:
        df_demo_estrat = load_carteira_demo()[["id", "grupo_cadastrado"]].drop_duplicates("id")
        base_estrat = base_estrat.merge(df_demo_estrat, on="id", how="left")
    except Exception:
        base_estrat["grupo_cadastrado"] = None

    base_estrat["tipologia"] = base_estrat["grupo_cadastrado"].map(classificar_tipologia)
    base_estrat["vendedor"] = base_estrat["nome_exibicao"].map(vend_map)
    base_estrat["dias_desde_primeira"] = (hoje - base_estrat["primeira_compra"]).dt.days
    base_estrat["gap_medio_segmento"] = calcular_gap_medio_segmento(base_estrat)

    ticket_seg = base_estrat.groupby("segmento")["ticket_medio_r"].transform("mean")
    ticket_global = base_estrat["ticket_medio_r"].median()
    if pd.isna(ticket_global) or ticket_global <= 0:
        ticket_global = 1.0
    base_estrat["ticket_media_segmento"] = ticket_seg.fillna(ticket_global).replace(0, ticket_global)
    base_estrat["indice_ticket_seg"] = (
        base_estrat["ticket_medio_r"] / base_estrat["ticket_media_segmento"].replace(0, pd.NA)
    ).fillna(0)

    ordem_prio = {"Alta": 0, "Média": 1, "Baixa": 2}

    # Matriz 2×2 — Virar recorrente
    segunda = base_estrat[
        (base_estrat["total_compras"] == 1)
        & base_estrat["dias_desde_primeira"].between(7, 180, inclusive="both")
    ].copy()
    segunda["janela_segunda_compra"] = segunda["dias_desde_primeira"].map(classificar_janela_segunda_compra)
    _ticket_ok = segunda["indice_ticket_seg"] >= 1.0
    _janela_ok = segunda["janela_segunda_compra"] == "Janela ideal"
    segunda["prioridade"] = "Baixa"
    segunda.loc[_ticket_ok | _janela_ok, "prioridade"] = "Média"
    segunda.loc[_ticket_ok & _janela_ok, "prioridade"] = "Alta"
    segunda["ord_prio"] = segunda["prioridade"].map(ordem_prio)
    segunda = segunda.sort_values(
        ["ord_prio", "indice_ticket_seg", "valor_total_r"],
        ascending=[True, False, False],
    )

    # Matriz 2×2 — Aumentar frequência
    expansao = base_estrat[
        base_estrat["total_compras"].between(2, 4, inclusive="both")
        & base_estrat["status_cliente"].isin(["ativo", "em_risco", "hibernando", "hibernando_sazonal"])
    ].copy()
    expansao["momento_expansao"] = expansao.apply(
        lambda r: classificar_momento_expansao(r["dias_sem_compra"], r["gap_medio_segmento"]),
        axis=1,
    )
    _ticket_ok = expansao["indice_ticket_seg"] >= 1.0
    _momento_ok = expansao["momento_expansao"].isin(["Janela quente", "Pede ação"])
    expansao["prioridade"] = "Baixa"
    expansao.loc[_ticket_ok | _momento_ok, "prioridade"] = "Média"
    expansao.loc[_ticket_ok & _momento_ok, "prioridade"] = "Alta"
    expansao["ord_prio"] = expansao["prioridade"].map(ordem_prio)
    expansao = expansao.sort_values(
        ["ord_prio", "indice_ticket_seg", "valor_total_r"],
        ascending=[True, False, False],
    )

    # Matriz 2×2 — Ancorar recém-chegados (com regra extra: já voltou = Alta sempre)
    novos_prioritarios = base_estrat[
        base_estrat["dias_desde_primeira"].between(0, 60, inclusive="both")
    ].copy()
    novos_prioritarios["janela_segunda_compra"] = novos_prioritarios["dias_desde_primeira"].map(
        classificar_janela_segunda_compra
    )
    novos_prioritarios["sinal_retencao"] = novos_prioritarios["total_compras"].apply(
        lambda v: "Já voltou" if pd.notna(v) and v >= 2 else "Ainda na 1ª compra"
    )
    _ja_voltou = novos_prioritarios["total_compras"] >= 2
    _ticket_ok = novos_prioritarios["indice_ticket_seg"] >= 1.0
    _janela_ok = novos_prioritarios["janela_segunda_compra"] == "Janela ideal"
    novos_prioritarios["prioridade"] = "Baixa"
    novos_prioritarios.loc[_ticket_ok | _janela_ok, "prioridade"] = "Média"
    novos_prioritarios.loc[_ticket_ok & _janela_ok, "prioridade"] = "Alta"
    novos_prioritarios.loc[_ja_voltou, "prioridade"] = "Alta"
    novos_prioritarios["ord_prio"] = novos_prioritarios["prioridade"].map(ordem_prio)
    novos_prioritarios = novos_prioritarios.sort_values(
        ["ord_prio", "indice_ticket_seg", "total_compras", "valor_total_r"],
        ascending=[True, False, False, False],
    )

    st.markdown(
        "<div style='margin:8px 0 18px; padding:10px 14px; background:#f8f9fa; "
        "border-left:3px solid #1A73E8; border-radius:4px; font-size:0.86rem; color:#333;'>"
        "<b>Prioridade</b> = cruzamento de dois sinais por cliente. "
        "<b style='color:#c0392b;'>Alta</b> se ticket ≥ média do segmento E timing dentro da janela da alavanca. "
        "<b style='color:#b7791f;'>Média</b> se apenas um bate. "
        "<b style='color:#666;'>Baixa</b> se nenhum bate."
        "</div>",
        unsafe_allow_html=True,
    )

    def _stat_card(
        titulo: str,
        elegibilidade: str,
        timing: str,
        df: pd.DataFrame,
        extra_label: str,
        extra_valor: str,
    ) -> str:
        alta = int((df["prioridade"] == "Alta").sum())
        media = int((df["prioridade"] == "Média").sum())
        baixa = int((df["prioridade"] == "Baixa").sum())
        total = max(alta + media + baixa, 1)
        p_alta = alta / total * 100
        p_media = media / total * 100
        p_baixa = baixa / total * 100
        df_alta = df[df["prioridade"] == "Alta"]
        ticket_alta = df_alta["ticket_medio_r"].mean() if not df_alta.empty else None
        ticket_txt = fmt_brl(ticket_alta) if ticket_alta and pd.notna(ticket_alta) else "—"

        return f"""
<div style='border:1px solid #e6e8eb; border-radius:8px; padding:18px 18px 16px;
            height:100%; background:#fff;'>
  <div style='font-size:0.72rem; font-weight:700; letter-spacing:0.1em;
              text-transform:uppercase; color:#1A73E8;'>{titulo}</div>
  <div style='font-size:0.78rem; color:#666; margin-top:2px;'>{elegibilidade}</div>

  <div style='display:flex; align-items:baseline; gap:8px; margin-top:14px;'>
    <div style='font-size:2.2rem; font-weight:700; line-height:1; color:#111;'>{fmt_num(alta)}</div>
    <div style='font-size:0.8rem; color:#c0392b; font-weight:600;'>Alta</div>
  </div>

  <div style='margin-top:10px; display:flex; height:8px; border-radius:4px;
              overflow:hidden; background:#f1f3f4;'>
    <div style='width:{p_alta:.2f}%; background:#c0392b;'></div>
    <div style='width:{p_media:.2f}%; background:#b7791f;'></div>
    <div style='width:{p_baixa:.2f}%; background:#9aa0a6;'></div>
  </div>
  <div style='display:flex; justify-content:space-between; font-size:0.75rem;
              color:#555; margin-top:4px;'>
    <span>Alta {fmt_num(alta)}</span>
    <span>Média {fmt_num(media)}</span>
    <span>Baixa {fmt_num(baixa)}</span>
  </div>

  <div style='margin-top:14px; padding-top:12px; border-top:1px solid #eef0f2;
              font-size:0.8rem; color:#444; line-height:1.5;'>
    <div><span style='color:#888;'>Timing:</span> {timing}</div>
    <div style='margin-top:4px;'><span style='color:#888;'>Ticket médio (Alta):</span> {ticket_txt}</div>
    <div style='margin-top:4px;'><span style='color:#888;'>{extra_label}:</span> {extra_valor}</div>
  </div>
</div>
"""

    alta_2a = segunda[segunda["prioridade"] == "Alta"]
    if not alta_2a.empty:
        uf_top = alta_2a["uf"].value_counts().head(1)
        if len(uf_top):
            pct_uf = f"{uf_top.iloc[0] / len(alta_2a) * 100:.0f}".replace(".", ",")
            extra_2a = f"{pct_uf}% em {uf_top.index[0]}"
        else:
            extra_2a = "—"
    else:
        extra_2a = "—"

    faixa_recompra = int(
        expansao["momento_expansao"].isin(["Janela quente", "Pede ação"]).sum()
    ) if not expansao.empty else 0
    ja_voltaram = int((novos_prioritarios["total_compras"] >= 2).sum()) if not novos_prioritarios.empty else 0

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            _stat_card(
                titulo="Virar recorrente",
                elegibilidade="1 compra, entre 7 e 180 dias atrás",
                timing="15 a 60 dias desde a 1ª compra",
                df=segunda,
                extra_label="Concentração geográfica",
                extra_valor=extra_2a,
            ),
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            _stat_card(
                titulo="Aumentar frequência",
                elegibilidade="2 a 4 compras, ativo ou em risco",
                timing="Intervalo sem comprar na faixa do segmento",
                df=expansao,
                extra_label="Na faixa de recompra",
                extra_valor=fmt_num(faixa_recompra),
            ),
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            _stat_card(
                titulo="Ancorar recém-chegados",
                elegibilidade="1ª compra nos últimos 60 dias",
                timing="15 a 60 dias desde a 1ª compra",
                df=novos_prioritarios,
                extra_label="Já voltaram 2+ vezes",
                extra_valor=fmt_num(ja_voltaram),
            ),
            unsafe_allow_html=True,
        )

    def _bg_prio(val):
        cor = CORES_PRIORIDADE.get(str(val))
        if not cor:
            return ""
        texto = "#111111" if val != "Alta" else "#ffffff"
        return f"background-color:{cor};color:{texto};font-weight:600"

    tab2a, tabexp, tabnov = st.tabs([
        "Virar recorrente",
        "Aumentar frequência",
        "Ancorar recém-chegados",
    ])

    with tab2a:
        if segunda.empty:
            st.info("Nenhum cliente de compra única dentro da janela operacional de 2ª compra.")
        else:
            st.caption("Clientes com uma única compra que ainda podem ser convertidos em recorrentes.")
            tb2 = segunda.copy()
            tb2["1ª compra"] = tb2["primeira_compra"].dt.strftime("%d/%m/%Y")
            tb2["Dias desde 1ª"] = tb2["dias_desde_primeira"].apply(lambda v: fmt_num(v, 0))
            tb2["Ticket médio"] = tb2["ticket_medio_r"].apply(fmt_brl)
            tb2["Ticket vs seg."] = tb2["indice_ticket_seg"].apply(
                lambda v: f"{fmt_num(v * 100, 0)}%"
            )
            tb2["Valor atual"] = tb2["valor_total_r"].apply(fmt_brl)
            tb2["Vendedor"] = tb2["vendedor"].fillna("—")
            exib_2a = tb2.rename(columns={
                "nome_exibicao": "Cliente",
                "segmento": "Segmento",
                "tipologia": "Perfil",
                "cidade": "Cidade",
                "uf": "UF",
                "janela_segunda_compra": "Janela",
                "prioridade": "Prioridade",
            })[[
                "Cliente", "Segmento", "Perfil", "Cidade", "UF", "Vendedor",
                "1ª compra", "Dias desde 1ª", "Ticket médio", "Ticket vs seg.",
                "Valor atual", "Janela", "Prioridade",
            ]]
            st.dataframe(
                exib_2a.style.map(_bg_prio, subset=["Prioridade"]),
                use_container_width=True,
                hide_index=True,
                height=340,
            )
            botao_csv(
                segunda[[
                    "nome_exibicao", "segmento", "tipologia", "cidade", "uf", "vendedor",
                    "primeira_compra", "dias_desde_primeira", "ticket_medio_r",
                    "indice_ticket_seg", "valor_total_r", "janela_segunda_compra",
                    "prioridade", "indice_ticket_seg",
                ]],
                "fila_segunda_compra",
                "Exportar fila 2ª compra (CSV)",
                key="csv_segunda_compra",
            )

    with tabexp:
        if expansao.empty:
            st.info("Nenhum cliente com 2–4 compras e ticket acima da média para trabalhar expansão.")
        else:
            st.caption("Clientes que já provaram valor por pedido, mas ainda compram pouco.")
            tbx = expansao.copy()
            tbx["Compras"] = tbx["total_compras"].apply(lambda v: fmt_num(v, 0))
            tbx["Ticket médio"] = tbx["ticket_medio_r"].apply(fmt_brl)
            tbx["Ticket vs seg."] = tbx["indice_ticket_seg"].apply(
                lambda v: f"{fmt_num(v * 100, 0)}%"
            )
            tbx["Dias s/comprar"] = tbx["dias_sem_compra"].apply(
                lambda v: fmt_num(v, 0) if pd.notna(v) else "—"
            )
            tbx["Ciclo típico"] = tbx["gap_medio_segmento"].apply(lambda v: f"{fmt_num(v, 0)} dias")
            tbx["Valor atual"] = tbx["valor_total_r"].apply(lambda v: fmt_brl(v, compact=True))
            tbx["Vendedor"] = tbx["vendedor"].fillna("—")
            exib_exp = tbx.rename(columns={
                "nome_exibicao": "Cliente",
                "segmento": "Segmento",
                "tipologia": "Perfil",
                "cidade": "Cidade",
                "uf": "UF",
                "momento_expansao": "Momento",
                "prioridade": "Prioridade",
            })[[
                "Cliente", "Segmento", "Perfil", "Cidade", "UF", "Vendedor",
                "Compras", "Ticket médio", "Ticket vs seg.", "Dias s/comprar",
                "Ciclo típico", "Valor atual", "Momento", "Prioridade",
            ]]
            st.dataframe(
                exib_exp.style.map(_bg_prio, subset=["Prioridade"]),
                use_container_width=True,
                hide_index=True,
                height=340,
            )
            botao_csv(
                expansao[[
                    "nome_exibicao", "segmento", "tipologia", "cidade", "uf", "vendedor",
                    "total_compras", "ticket_medio_r", "indice_ticket_seg",
                    "dias_sem_compra", "gap_medio_segmento", "valor_total_r",
                    "momento_expansao", "prioridade", "indice_ticket_seg",
                ]],
                "fila_expansao_frequencia",
                "Exportar fila expansão (CSV)",
                key="csv_expansao_freq",
            )

    with tabnov:
        if novos_prioritarios.empty:
            st.info("Nenhum novo cliente encontrado nos últimos 60 dias para o filtro atual.")
        else:
            st.caption("Priorização da retenção inicial: quem merece acompanhamento comercial mais próximo.")
            tbn = novos_prioritarios.copy()
            tbn["1ª compra"] = tbn["primeira_compra"].dt.strftime("%d/%m/%Y")
            tbn["Compras"] = tbn["total_compras"].apply(lambda v: fmt_num(v, 0))
            tbn["Dias desde 1ª"] = tbn["dias_desde_primeira"].apply(lambda v: fmt_num(v, 0))
            tbn["Ticket médio"] = tbn["ticket_medio_r"].apply(fmt_brl)
            tbn["Ticket vs seg."] = tbn["indice_ticket_seg"].apply(
                lambda v: f"{fmt_num(v * 100, 0)}%"
            )
            tbn["Valor atual"] = tbn["valor_total_r"].apply(fmt_brl)
            tbn["Vendedor"] = tbn["vendedor"].fillna("—")
            exib_nov = tbn.rename(columns={
                "nome_exibicao": "Cliente",
                "segmento": "Segmento",
                "tipologia": "Perfil",
                "cidade": "Cidade",
                "uf": "UF",
                "janela_segunda_compra": "Janela",
                "sinal_retencao": "Sinal",
                "prioridade": "Prioridade",
            })[[
                "Cliente", "Segmento", "Perfil", "Cidade", "UF", "Vendedor",
                "1ª compra", "Dias desde 1ª", "Compras", "Ticket médio",
                "Ticket vs seg.", "Valor atual", "Sinal", "Janela", "Prioridade",
            ]]
            st.dataframe(
                exib_nov.style.map(_bg_prio, subset=["Prioridade"]),
                use_container_width=True,
                hide_index=True,
                height=340,
            )
            botao_csv(
                novos_prioritarios[[
                    "nome_exibicao", "segmento", "tipologia", "cidade", "uf", "vendedor",
                    "primeira_compra", "dias_desde_primeira", "total_compras",
                    "ticket_medio_r", "indice_ticket_seg", "valor_total_r",
                    "sinal_retencao", "janela_segunda_compra", "prioridade", "indice_ticket_seg",
                ]],
                "fila_novos_prioritarios",
                "Exportar fila novos prioritários (CSV)",
                key="csv_novos_prioritarios",
            )

    with st.expander("Base completa — novos clientes dos últimos 60 dias", expanded=False):
        novos60 = base_estrat[base_estrat["dias_desde_primeira"].between(0, 60, inclusive="both")].copy()
        novos60 = novos60.sort_values("valor_total_r", ascending=False)
        novos60["Fat. Total"] = novos60["valor_total_r"].apply(fmt_brl)
        novos60["Ticket Medio"] = novos60["ticket_medio_r"].apply(fmt_brl)
        novos60["1a Compra"] = novos60["primeira_compra"].dt.strftime("%d/%m/%Y")
        exib_novos = novos60.rename(
            columns={"nome_exibicao": "Cliente", "total_compras": "Compras"}
        )[["Cliente", "segmento", "cidade", "uf", "1a Compra",
           "Compras", "Fat. Total", "Ticket Medio"]]
        st.dataframe(exib_novos, use_container_width=True, height=260, hide_index=True)
        st.caption(f"{fmt_num(len(novos60))} novos clientes nos últimos 60 dias")
        if not novos60.empty:
            botao_csv(exib_novos, "novos_clientes_60d", key="csv_novos60")

    st.caption(
        "Para acompanhamento do desempenho comercial por vendedor nessas filas, "
        "acesse o painel **Vendedores**."
    )


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 5 — DEMOGRAPHICS
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Demografia":

    st.title("Demografia e Distribuição")
    st.caption("Quem são os clientes, onde estão e quão longe a marca chega.")

    from geo import (
        enriquecer_carteira_geo, classificar_faixa, classificar_tipologia,
        ORDEM_FAIXAS, ORDEM_TIPOLOGIAS, CORES_TIPOLOGIA, CORES_FAIXA,
        SEDE_LAT, SEDE_LON, circle_points_km, zonas_brancas_no_raio,
    )
    import math

    try:
        with st.spinner("Carregando dados geográficos..."):
            df_geo_full = load_carteira_geo_cached()
    except Exception as _e:
        st.error(
            f"Erro ao carregar dados para o painel Demografia: **{_e}**\n\n"
            "Verifique se a migração `sql/002_grupo_cadastrado.sql` foi aplicada no Supabase."
        )
        st.stop()

    df_geo = seg(df_geo_full)
    df_ativos = df_geo[df_geo["status_cliente"] != "sem_compra"].copy()

    if df_ativos.empty:
        st.warning("Nenhum cliente encontrado para o filtro selecionado.")
        st.stop()

    _tip_agg = (
        df_ativos
        .groupby("tipologia", as_index=False)
        .agg(
            n_clientes=("id", "count"),
            ltv=("valor_total_r", "sum"),
            ticket_medio=("ticket_medio_r", "mean"),
            dist_media=("distancia_km", "mean"),
        )
        .round({"ltv": 0, "ticket_medio": 0, "dist_media": 0})
    )
    _ltv_total_tip = float(_tip_agg["ltv"].sum())
    _tip_agg["pct_ltv"] = (_tip_agg["ltv"] / _ltv_total_tip * 100).round(1)
    _tip_agg["ltv_por_cliente"] = (
        _tip_agg["ltv"] / _tip_agg["n_clientes"].replace(0, pd.NA)
    ).round(0)
    _tip_agg = _tip_agg.merge(
        pd.DataFrame({"tipologia": ORDEM_TIPOLOGIAS}), on="tipologia", how="right"
    ).fillna({
        "n_clientes": 0, "ltv": 0, "pct_ltv": 0, "ltv_por_cliente": 0,
        "ticket_medio": 0, "dist_media": 0,
    })
    _tip_agg = _tip_agg[_tip_agg["n_clientes"] > 0].sort_values("ltv", ascending=False)

    st.subheader("Perfis da carteira")
    _col_t1, _col_t2 = st.columns([1.15, 1.85])

    with _col_t1:
        _fig_tip = go.Figure(go.Bar(
            y=_tip_agg["tipologia"],
            x=_tip_agg["n_clientes"],
            orientation="h",
            marker_color=[CORES_TIPOLOGIA.get(t, "#ccc") for t in _tip_agg["tipologia"]],
            text=_tip_agg.apply(
                lambda r: f"{fmt_num(r['n_clientes'])} · {fmt_num(r['pct_ltv'], 1)}% do LTV",
                axis=1,
            ),
            textposition="outside",
            cliponaxis=False,
        ))
        _fig_tip.update_layout(
            height=320, margin=dict(l=0, r=120, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            showlegend=False,
        )
        _fig_tip.update_xaxes(title_text="Clientes", gridcolor="#f0f0f0")
        _fig_tip.update_yaxes(showgrid=False, categoryorder="total ascending")
        apply_ptbr(_fig_tip)
        st.plotly_chart(_fig_tip, use_container_width=True)

    with _col_t2:
        _fig_bubble = px.scatter(
            _tip_agg,
            x="ticket_medio",
            y="ltv_por_cliente",
            size="n_clientes",
            color="tipologia",
            color_discrete_map=CORES_TIPOLOGIA,
            text="tipologia",
            labels={
                "ticket_medio": "Ticket médio (R$)",
                "ltv_por_cliente": "LTV por cliente (R$)",
                "tipologia": "",
            },
        )
        _fig_bubble.update_traces(
            textposition="top center",
            marker=dict(line=dict(color="#ffffff", width=1.5), opacity=0.88),
        )
        _fig_bubble.update_layout(
            height=320, margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=-0.25),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        _fig_bubble.update_xaxes(tickprefix="R$ ", gridcolor="#f0f0f0")
        _fig_bubble.update_yaxes(tickprefix="R$ ", gridcolor="#f0f0f0")
        apply_ptbr(_fig_bubble)
        st.plotly_chart(_fig_bubble, use_container_width=True)

    _exib_tip = _tip_agg.copy()
    _exib_tip["Clientes"] = _exib_tip["n_clientes"].apply(lambda v: fmt_num(int(v)))
    _exib_tip["LTV total"] = _exib_tip["ltv"].apply(lambda v: fmt_brl(v, compact=True))
    _exib_tip["LTV / cliente"] = _exib_tip["ltv_por_cliente"].apply(
        lambda v: fmt_brl(v) if pd.notna(v) and v > 0 else "—"
    )
    _exib_tip["Ticket médio"] = _exib_tip["ticket_medio"].apply(
        lambda v: fmt_brl(v) if pd.notna(v) and v > 0 else "—"
    )
    _exib_tip["Distância média"] = _exib_tip["dist_media"].apply(
        lambda v: f"{fmt_num(v, 0)} km" if pd.notna(v) and v > 0 else "—"
    )
    st.dataframe(
        _exib_tip.rename(columns={"tipologia": "Tipologia"})[
            ["Tipologia", "Clientes", "LTV total", "LTV / cliente", "Ticket médio", "Distância média"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("Mapa de penetração")

    _mapa_base = df_ativos.dropna(subset=["lat", "lon"]).copy()
    if _mapa_base.empty:
        st.info("Nenhum cliente com geolocalização encontrada.")
    else:
        # ── controles do mapa ──────────────────────────────────────────────
        # Segmento é controlado exclusivamente pelo filtro global da sidebar
        # (antes havia radio local que sobrescrevia e gerava confusão).
        _ctrl_c1, _ctrl_c2 = st.columns([1, 1])
        with _ctrl_c1:
            _mapa_modo = st.radio(
                "Intensidade",
                ["Clientes", "LTV", "Ticket médio"],
                horizontal=True,
                key="radio_cor_mapa",
            )
        with _ctrl_c2:
            _viz_modo = st.radio(
                "Visualização",
                ["Ambos", "Calor", "Pontos"],
                horizontal=True,
                key="radio_viz_mapa",
                help=(
                    "Calor: densidade agregada (melhor para leitura panorâmica). "
                    "Pontos: um marcador por cidade (sempre visível, resistente a zoom). "
                    "Ambos: camadas sobrepostas."
                ),
            )

        _seg_label = (
            {"1 - Atacado": "Atacado", "2 - Varejo": "Varejo",
             "5 - Atacarejo": "Atacarejo"}.get(seg_filter, "Geral")
        )
        _mapa_filtrado = _mapa_base.copy()  # já veio filtrado via seg() no df_geo

        if _mapa_filtrado.empty:
            st.info(f"Nenhum cliente do segmento **{_seg_label}** com geolocalização.")
        else:
            # ── agregação por cidade (1 ponto por cidade, evita mancha) ────
            _mapa_agg = (
                _mapa_filtrado
                .groupby(["cidade", "uf", "lat", "lon"], as_index=False)
                .agg(
                    n_clientes=("id", "count"),
                    ltv=("valor_total_r", "sum"),
                    ticket_medio=("ticket_medio_r", "mean"),
                )
            )
            _tip_pred = (
                _mapa_filtrado.groupby(["cidade", "uf"])["tipologia"]
                .agg(lambda x: x.value_counts().index[0] if len(x) else "Sem classificação")
                .reset_index()
                .rename(columns={"tipologia": "tipologia_pred"})
            )
            _mapa_agg = _mapa_agg.merge(_tip_pred, on=["cidade", "uf"], how="left")

            # ── métricas de penetração ─────────────────────────────────────
            _pm1, _pm2, _pm3 = st.columns(3)
            _pm1.metric("Clientes mapeados", fmt_num(len(_mapa_filtrado)))
            _pm2.metric("Cidades alcançadas", fmt_num(_mapa_agg["cidade"].nunique()))
            _pm3.metric("Ticket médio", fmt_brl(_mapa_filtrado["ticket_medio_r"].mean()))

            # ── heatmap agregado por cidade ────────────────────────────────
            _z_map = {
                "Clientes":     ("n_clientes",   "Clientes"),
                "LTV":          ("ltv",          "LTV (R$)"),
                "Ticket médio": ("ticket_medio", "Ticket médio (R$)"),
            }
            _z_col, _z_title = _z_map[_mapa_modo]

            _raio_medio = (
                (_mapa_filtrado["distancia_km"] * _mapa_filtrado["valor_total_r"]).sum()
                / _mapa_filtrado["valor_total_r"].sum()
            ) if _mapa_filtrado["distancia_km"].notna().any() and _mapa_filtrado["valor_total_r"].sum() > 0 else None

            # Transformação log: comprime a escala para que cidades com poucos
            # clientes não caiam em ~0 numa escala dominada por Santa Cruz.
            _raw = _mapa_agg[_z_col].fillna(0).astype(float).clip(lower=0)
            _mapa_agg["_z_log"] = _raw.map(lambda v: math.log1p(v))
            _log_max = max(_mapa_agg["_z_log"].max(), 1e-9)

            _COLORSCALE = [
                [0.00, "#2b83ba"],
                [0.25, "#abdda4"],
                [0.50, "#ffffbf"],
                [0.75, "#fdae61"],
                [1.00, "#d7191c"],
            ]

            # Centro e zoom ajustados ao segmento exibido (em vez do BR inteiro,
            # que escondia dispersão fora de PE). Mantém dentro de faixa razoável.
            _lat_c = float(_mapa_agg["lat"].mean())
            _lon_c = float(_mapa_agg["lon"].mean())
            _lat_span = float(_mapa_agg["lat"].max() - _mapa_agg["lat"].min())
            _lon_span = float(_mapa_agg["lon"].max() - _mapa_agg["lon"].min())
            _span = max(_lat_span, _lon_span, 0.1)
            _zoom_inicial = max(3.2, min(7.0, 8.5 - math.log2(_span + 1) * 1.6))

            _fig_mapa = go.Figure()

            # ── CAMADA 1: calor (opcional) ─────────────────────────────────
            if _viz_modo in ("Ambos", "Calor"):
                _fig_mapa.add_trace(go.Densitymapbox(
                    lat=_mapa_agg["lat"],
                    lon=_mapa_agg["lon"],
                    z=_mapa_agg["_z_log"],
                    radius=28,
                    colorscale=_COLORSCALE,
                    zmin=0,
                    zmax=_log_max,
                    opacity=0.55 if _viz_modo == "Ambos" else 0.85,
                    showscale=(_viz_modo == "Calor"),
                    colorbar=dict(
                        title=f"{_z_title} (log)",
                        tickvals=[0, _log_max * 0.5, _log_max],
                        ticktext=["baixo", "médio", "alto"],
                    ),
                    hoverinfo="skip",
                    name="Densidade",
                ))

            # ── CAMADA 2: pontos por cidade (sempre visível, resistente a zoom)
            if _viz_modo in ("Ambos", "Pontos"):
                _size_base = _raw.pow(0.5)  # sqrt comprime sem zerar pequenos
                _size_max = max(_size_base.max(), 1e-9)
                _marker_size = 6 + (_size_base / _size_max) * 26  # 6–32 px

                _fig_mapa.add_trace(go.Scattermapbox(
                    lat=_mapa_agg["lat"],
                    lon=_mapa_agg["lon"],
                    mode="markers",
                    marker=dict(
                        size=_marker_size,
                        color=_mapa_agg["_z_log"],
                        colorscale=_COLORSCALE,
                        cmin=0,
                        cmax=_log_max,
                        opacity=0.78,
                        showscale=(_viz_modo == "Pontos"),
                        colorbar=dict(
                            title=f"{_z_title} (log)",
                            tickvals=[0, _log_max * 0.5, _log_max],
                            ticktext=["baixo", "médio", "alto"],
                        ) if _viz_modo == "Pontos" else None,
                    ),
                    text=_mapa_agg.apply(
                        lambda r: (
                            f"<b>{r['cidade']}/{r['uf']}</b><br>"
                            f"Clientes: {fmt_num(r['n_clientes'])}<br>"
                            f"LTV: {fmt_brl(r['ltv'], compact=True)}<br>"
                            f"Ticket médio: {fmt_brl(r['ticket_medio'])}<br>"
                            f"Perfil dominante: {r['tipologia_pred']}"
                        ),
                        axis=1,
                    ),
                    hovertemplate="%{text}<extra></extra>",
                    name="Cidades atendidas",
                    showlegend=False,
                ))
            else:
                # Hover invisível quando modo = Calor
                _fig_mapa.add_trace(go.Scattermapbox(
                    lat=_mapa_agg["lat"],
                    lon=_mapa_agg["lon"],
                    mode="markers",
                    marker=dict(size=16, color="rgba(0,0,0,0)"),
                    text=_mapa_agg.apply(
                        lambda r: (
                            f"<b>{r['cidade']}/{r['uf']}</b><br>"
                            f"Clientes: {fmt_num(r['n_clientes'])}<br>"
                            f"LTV: {fmt_brl(r['ltv'], compact=True)}"
                        ),
                        axis=1,
                    ),
                    hovertemplate="%{text}<extra></extra>",
                    showlegend=False,
                ))

            # ── CAMADA 3: zonas brancas dentro do raio ─────────────────────
            _mostra_brancas = st.session_state.get("_mostra_zonas_brancas", True)
            _pop_min = st.session_state.get("_pop_min_brancas", 10000)
            _df_brancas = pd.DataFrame()
            if _raio_medio and _raio_medio > 0:
                try:
                    _df_brancas = zonas_brancas_no_raio(
                        _mapa_agg[["cidade", "uf"]],
                        raio_km=float(_raio_medio),
                        pop_min=int(_pop_min),
                    )
                except Exception:
                    _df_brancas = pd.DataFrame()

            _tem_pop = (
                not _df_brancas.empty
                and _df_brancas["populacao"].notna().any()
            )
            if _mostra_brancas and not _df_brancas.empty:
                if _tem_pop:
                    _bsize_base = _df_brancas["populacao"].fillna(0).astype(float).pow(0.5)
                else:
                    # Sem população: tamanho fixo por distância inversa
                    _bsize_base = pd.Series([1.0] * len(_df_brancas))
                _bsize_max = max(_bsize_base.max(), 1e-9)
                _bmarker_size = 6 + (_bsize_base / _bsize_max) * 20  # 6–26 px

                def _hover_branca(r):
                    linhas = [f"<b>{r['cidade']}/{r['uf']}</b>"]
                    if pd.notna(r.get("populacao")):
                        linhas.append(f"População: {fmt_num(int(r['populacao']))}")
                    linhas.append(f"Distância sede: {fmt_num(r['distancia_km'], 0)} km")
                    linhas.append("<i>Oportunidade · cidade sem cliente</i>")
                    return "<br>".join(linhas)

                # Halo externo — anel translúcido que sugere "espaço vazio"
                _fig_mapa.add_trace(go.Scattermapbox(
                    lat=_df_brancas["lat"],
                    lon=_df_brancas["lon"],
                    mode="markers",
                    marker=dict(
                        size=_bmarker_size * 1.6,
                        color="rgba(107, 114, 128, 0.18)",  # cinza neutro
                        opacity=1.0,
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                ))
                # Miolo — marker âmbar (oportunidade, não alarme)
                _fig_mapa.add_trace(go.Scattermapbox(
                    lat=_df_brancas["lat"],
                    lon=_df_brancas["lon"],
                    mode="markers",
                    marker=dict(
                        size=_bmarker_size * 0.55,
                        color="rgba(245, 158, 11, 0.85)",  # âmbar = oportunidade
                        opacity=0.95,
                    ),
                    text=_df_brancas.apply(_hover_branca, axis=1),
                    hovertemplate="%{text}<extra></extra>",
                    name="Oportunidade (sem cliente)",
                    showlegend=True,
                ))

            if _raio_medio and _raio_medio > 0:
                _circle_lat, _circle_lon = circle_points_km(SEDE_LAT, SEDE_LON, float(_raio_medio))
                _fig_mapa.add_trace(go.Scattermapbox(
                    lat=_circle_lat,
                    lon=_circle_lon,
                    mode="lines",
                    line=dict(color="rgba(11,79,159,0.70)", width=2),
                    hovertemplate=f"Raio médio ponderado por LTV: {fmt_num(_raio_medio, 0)} km<extra></extra>",
                    name="Raio médio",
                ))

            _fig_mapa.add_trace(go.Scattermapbox(
                lat=[SEDE_LAT],
                lon=[SEDE_LON],
                mode="markers+text",
                text=["Sede"],
                textposition="top right",
                marker=dict(size=11, color="#111111"),
                hovertemplate="Santa Cruz do Capibaribe/PE<extra></extra>",
                name="Sede",
            ))
            _fig_mapa.update_layout(
                height=580,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="#fff",
                mapbox=dict(
                    style="carto-positron",
                    center={"lat": _lat_c, "lon": _lon_c},
                    zoom=_zoom_inicial,
                ),
                legend=dict(orientation="h", y=-0.08),
            )
            apply_ptbr(_fig_mapa)
            st.plotly_chart(_fig_mapa, use_container_width=True)
            st.caption(
                (
                    f"Raio médio (ponderado por LTV) = {fmt_num(_raio_medio, 0)} km · "
                    if _raio_medio else "Raio médio indisponível · "
                )
                + f"Visualização: **{_viz_modo}** · Segmento: **{_seg_label}** · "
                + "Escala logarítmica (log1p) — evita que cidades de baixa densidade sumam."
            )

            # ── controles de oportunidades + tabelas ───────────────────────
            _tab_top, _tab_brancas = st.tabs(
                ["Top cidades atendidas", "Oportunidades no raio"]
            )

            with _tab_top:
                _cidades_top = _mapa_agg.sort_values("ltv", ascending=False).head(15).copy()
                _cidades_top["Clientes"] = _cidades_top["n_clientes"].apply(fmt_num)
                _cidades_top["LTV"] = _cidades_top["ltv"].apply(lambda v: fmt_brl(v, compact=True))
                _cidades_top["Ticket médio"] = _cidades_top["ticket_medio"].apply(fmt_brl)
                st.dataframe(
                    _cidades_top.rename(columns={
                        "cidade": "Cidade", "uf": "UF", "tipologia_pred": "Perfil dominante"
                    })[["Cidade", "UF", "Clientes", "LTV", "Ticket médio", "Perfil dominante"]],
                    use_container_width=True,
                    hide_index=True,
                )

            with _tab_brancas:
                _col_zb1, _col_zb2 = st.columns([1, 1])
                with _col_zb1:
                    st.checkbox(
                        "Destacar oportunidades no mapa",
                        value=True,
                        key="_mostra_zonas_brancas",
                    )
                with _col_zb2:
                    st.select_slider(
                        "População mínima",
                        options=[5000, 10000, 20000, 50000, 100000],
                        value=10000,
                        key="_pop_min_brancas",
                        help=(
                            "Filtra cidades pequenas. Elevar o mínimo foca em "
                            "oportunidades com massa de mercado."
                        ),
                    )

                if _df_brancas.empty:
                    if not _raio_medio or _raio_medio <= 0:
                        st.info(
                            "Sem raio médio calculável para o segmento selecionado "
                            "(faltam vendas com distância/LTV)."
                        )
                    else:
                        st.success(
                            f"Dentro do raio de {fmt_num(_raio_medio, 0)} km não há "
                            f"cidades acima de {fmt_num(_pop_min)} habitantes sem cliente. "
                            "Reduza o filtro de população ou expanda o raio."
                        )
                else:
                    _mp1, _mp2, _mp3 = st.columns(3)
                    _mp1.metric("Cidades sem cliente (no raio)", fmt_num(len(_df_brancas)))
                    if _tem_pop:
                        _pop_sem_penet = int(_df_brancas["populacao"].fillna(0).sum())
                        _mp2.metric("População não atendida", fmt_num(_pop_sem_penet))
                    else:
                        _mp2.metric("População não atendida", "—",
                                    help="Dados de população IBGE indisponíveis no cache.")
                    _mp3.metric(
                        "Raio analisado",
                        f"{fmt_num(_raio_medio, 0)} km",
                        help="Raio médio ponderado por LTV do segmento selecionado.",
                    )

                    _brancas_show = _df_brancas.head(25).copy()
                    _brancas_show["População"] = _brancas_show["populacao"].apply(
                        lambda v: fmt_num(int(v)) if pd.notna(v) else "—"
                    )
                    _brancas_show["Distância"] = _brancas_show["distancia_km"].apply(
                        lambda v: f"{fmt_num(v, 0)} km"
                    )
                    st.dataframe(
                        _brancas_show.rename(columns={
                            "cidade": "Cidade", "uf": "UF",
                        })[["Cidade", "UF", "População", "Distância"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        "Cidades do IBGE dentro do raio médio de penetração **sem "
                        "nenhum cliente na carteira** — "
                        + ("ordenadas por população (potencial de mercado não atendido)."
                           if _tem_pop
                           else "ordenadas por distância da sede.")
                    )

    st.divider()
    st.subheader("Distribuição por distância")

    _faixa_agg = (
        df_ativos.groupby("faixa_distancia", as_index=False)
        .agg(
            n_clientes=("id", "count"),
            ltv=("valor_total_r", "sum"),
            ticket_medio=("ticket_medio_r", "mean"),
        )
    )
    _faixa_agg = (
        pd.DataFrame({"faixa_distancia": ORDEM_FAIXAS})
        .merge(_faixa_agg, on="faixa_distancia", how="left")
        .fillna(0)
    )

    _col_f1, _col_f2 = st.columns(2)
    with _col_f1:
        _fig_fc = go.Figure(go.Bar(
            y=_faixa_agg["faixa_distancia"],
            x=_faixa_agg["n_clientes"],
            orientation="h",
            marker_color=[CORES_FAIXA.get(f, "#ccc") for f in _faixa_agg["faixa_distancia"]],
            text=_faixa_agg["n_clientes"].astype(int).apply(fmt_num),
            textposition="outside",
            cliponaxis=False,
        ))
        _fig_fc.update_layout(
            height=300, margin=dict(l=0, r=50, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        _fig_fc.update_xaxes(title_text="Clientes", gridcolor="#f0f0f0")
        _fig_fc.update_yaxes(showgrid=False, categoryorder="array",
                             categoryarray=list(reversed(ORDEM_FAIXAS)))
        apply_ptbr(_fig_fc)
        st.plotly_chart(_fig_fc, use_container_width=True)

    with _col_f2:
        _fig_fl = go.Figure(go.Bar(
            y=_faixa_agg["faixa_distancia"],
            x=_faixa_agg["ltv"],
            orientation="h",
            marker_color=[CORES_FAIXA.get(f, "#ccc") for f in _faixa_agg["faixa_distancia"]],
            text=_faixa_agg["ltv"].apply(lambda v: fmt_brl(v, compact=True)),
            textposition="outside",
            cliponaxis=False,
        ))
        _fig_fl.update_layout(
            height=300, margin=dict(l=0, r=80, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        _fig_fl.update_xaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        _fig_fl.update_yaxes(showgrid=False, categoryorder="array",
                             categoryarray=list(reversed(ORDEM_FAIXAS)))
        apply_ptbr(_fig_fl)
        st.plotly_chart(_fig_fl, use_container_width=True)

    st.markdown("**Tipologia × faixa de distância**")
    _modo_matriz = st.radio(
        "Exibir",
        ["Nº de clientes", "LTV agregado (R$)", "Ticket médio (R$)"],
        horizontal=True,
        key="radio_matriz",
    )
    _mat_base = df_ativos.copy()
    _mat_n = _mat_base.groupby(["tipologia", "faixa_distancia"]).size().unstack(fill_value=0)
    _mat_ltv = _mat_base.groupby(["tipologia", "faixa_distancia"])["valor_total_r"].sum().unstack(fill_value=0)
    _mat_ticket = _mat_base.groupby(["tipologia", "faixa_distancia"])["ticket_medio_r"].mean().unstack(fill_value=0)
    _mat_map = {
        "Nº de clientes": _mat_n,
        "LTV agregado (R$)": _mat_ltv,
        "Ticket médio (R$)": _mat_ticket,
    }
    _mat_plot = _mat_map[_modo_matriz].reindex(index=ORDEM_TIPOLOGIAS, columns=ORDEM_FAIXAS, fill_value=0)
    _mat_plot = _mat_plot.loc[_mat_plot.sum(axis=1) > 0]

    if not _mat_plot.empty:
        if _modo_matriz == "Nº de clientes":
            _fmt_cell = lambda v: fmt_num(int(v)) if v > 0 else "—"
        else:
            _fmt_cell = lambda v: fmt_brl(v, compact=True) if pd.notna(v) and v > 0 else "—"
        _fig_mat = go.Figure(go.Heatmap(
            z=_mat_plot.values,
            x=list(_mat_plot.columns),
            y=list(_mat_plot.index),
            colorscale=[
                [0.0, "#eef4ff"],
                [0.30, "#bbd2ff"],
                [0.65, "#5b96f7"],
                [1.0, "#0d3b8e"],
            ],
            text=[[_fmt_cell(v) for v in row] for row in _mat_plot.values],
            texttemplate="%{text}",
            hovertemplate="Tipologia: %{y}<br>Faixa: %{x}<br>Valor: %{text}<extra></extra>",
            showscale=False,
        ))
        _fig_mat.update_layout(
            height=max(260, 42 * len(_mat_plot) + 80),
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#fff",
            xaxis=dict(tickangle=-20),
        )
        apply_ptbr(_fig_mat)
        st.plotly_chart(_fig_mat, use_container_width=True)

    st.divider()
    st.subheader("Quem compra os itens mais caros")
    try:
        df_itens_demo = aplicar_periodo(seg(load_itens_clientes()), periodo, "data_venda")
        if not df_itens_demo.empty and df_itens_demo["preco_unitario_r"].notna().any():
            _origens_itens = sorted(df_itens_demo["origem"].dropna().unique().tolist())
            if _origens_itens == ["TRAY"]:
                st.caption("Escopo atual: itens disponíveis apenas do e-commerce/Tray.")

            _geo_item = df_geo_full[["id", "tipologia", "faixa_distancia"]].rename(columns={"id": "cliente_id"})
            _it_demo = df_itens_demo.merge(_geo_item, on="cliente_id", how="left")
            _it_demo["tipologia"] = _it_demo["tipologia"].fillna(_it_demo["grupo_cadastrado"].map(classificar_tipologia))
            _it_demo["faixa_distancia"] = _it_demo["faixa_distancia"].fillna("Sem localização")
            _it_demo = _it_demo[_it_demo["cliente_id"].notna() & _it_demo["preco_unitario_r"].notna()]

            if not _it_demo.empty:
                _cut = float(_it_demo["preco_unitario_r"].quantile(0.90))
                _premium = _it_demo[_it_demo["preco_unitario_r"] >= _cut].copy()
                st.caption(
                    f"Recorte premium = top 10% do preço unitário da base atual "
                    f"(a partir de {fmt_brl(_cut)})."
                )

                _col_p1, _col_p2 = st.columns([1.1, 1.9])
                with _col_p1:
                    _prem_tip = (
                        _premium.groupby("tipologia", as_index=False)
                        .agg(
                            clientes=("cliente_id", "nunique"),
                            preco_medio=("preco_unitario_r", "mean"),
                            receita=("valor_total_item_r", "sum"),
                        )
                        .sort_values("clientes", ascending=True)
                    )
                    _fig_prem = go.Figure(go.Bar(
                        y=_prem_tip["tipologia"],
                        x=_prem_tip["clientes"],
                        orientation="h",
                        marker_color=[CORES_TIPOLOGIA.get(t, "#ccc") for t in _prem_tip["tipologia"]],
                        text=_prem_tip["preco_medio"].apply(fmt_brl),
                        textposition="outside",
                        cliponaxis=False,
                    ))
                    _fig_prem.update_layout(
                        height=300, margin=dict(l=0, r=70, t=10, b=0),
                        plot_bgcolor="#fff", paper_bgcolor="#fff",
                        showlegend=False,
                    )
                    _fig_prem.update_xaxes(title_text="Clientes premium", gridcolor="#f0f0f0")
                    _fig_prem.update_yaxes(showgrid=False)
                    apply_ptbr(_fig_prem)
                    st.plotly_chart(_fig_prem, use_container_width=True)

                with _col_p2:
                    _cli_prem = (
                        _premium.groupby(
                            ["cliente_id", "nome_exibicao", "tipologia", "cidade", "uf"], as_index=False
                        )
                        .agg(
                            itens_premium=("item_id", "count"),
                            max_preco=("preco_unitario_r", "max"),
                            preco_medio=("preco_unitario_r", "mean"),
                            ltv_cliente=("cliente_ltv_r", "max"),
                            ticket_cliente=("cliente_ticket_medio_r", "max"),
                        )
                        .sort_values(["max_preco", "itens_premium"], ascending=[False, False])
                        .head(15)
                    )
                    _cli_prem["Item premium"] = _cli_prem["itens_premium"].apply(fmt_num)
                    _cli_prem["Maior preço"] = _cli_prem["max_preco"].apply(fmt_brl)
                    _cli_prem["Preço médio"] = _cli_prem["preco_medio"].apply(fmt_brl)
                    _cli_prem["LTV"] = _cli_prem["ltv_cliente"].apply(
                        lambda v: fmt_brl(v, compact=True) if pd.notna(v) else "—"
                    )
                    _cli_prem["Ticket cliente"] = _cli_prem["ticket_cliente"].apply(
                        lambda v: fmt_brl(v) if pd.notna(v) else "—"
                    )
                    st.dataframe(
                        _cli_prem.rename(columns={
                            "nome_exibicao": "Cliente",
                            "tipologia": "Perfil",
                            "cidade": "Cidade",
                            "uf": "UF",
                        })[[
                            "Cliente", "Perfil", "Cidade", "UF",
                            "Item premium", "Maior preço", "Preço médio",
                            "LTV", "Ticket cliente",
                        ]],
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                    )
            else:
                st.info("Os itens disponíveis ainda não têm cliente identificado suficiente para esta leitura.")
        else:
            st.info("Não há itens disponíveis para o filtro atual.")
    except Exception as _e:
        st.info(f"Não foi possível carregar a análise de itens neste painel: {_e}")


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 6 — ITENS
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Itens":

    st.title("Itens e Mix de Produto")
    st.caption("Produtos vendidos, faixas de preço e quem compra os itens mais caros.")
    from geo import CORES_TIPOLOGIA, ORDEM_TIPOLOGIAS, classificar_tipologia

    try:
        with st.spinner("Carregando itens vendidos..."):
            df_itens = aplicar_periodo(seg(load_itens_clientes()), periodo, "data_venda")
    except Exception as _e:
        st.error(f"Erro ao carregar itens de venda: **{_e}**")
        st.stop()

    if df_itens.empty:
        st.info("Não há itens disponíveis para o filtro atual.")
        st.stop()

    _origens_itens = sorted(df_itens["origem"].dropna().unique().tolist())
    if _origens_itens == ["TRAY"]:
        st.warning(
            "Escopo atual: este painel usa apenas itens do e-commerce/Tray. "
            "Ainda não representa o mix completo do DAPIC/atacado."
        )

    _it_validos = df_itens[df_itens["preco_unitario_r"].notna()].copy()
    _preco_medio = _it_validos["preco_unitario_r"].mean() if not _it_validos.empty else None
    _faturamento_itens = _it_validos["valor_total_item_r"].sum() if not _it_validos.empty else 0
    _cut_premium = float(_it_validos["preco_unitario_r"].quantile(0.90)) if not _it_validos.empty else None
    _premium = _it_validos[_it_validos["preco_unitario_r"] >= _cut_premium].copy() if _cut_premium else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Itens vendidos", fmt_num(len(_it_validos)))
    with c2:
        st.metric("SKUs distintos", fmt_num(_it_validos["referencia"].fillna(_it_validos["sku"]).nunique()))
    with c3:
        st.metric("Preço médio unitário", fmt_brl(_preco_medio) if _preco_medio else "—")
    with c4:
        st.metric("Receita em itens", fmt_brl(_faturamento_itens, compact=True))

    st.divider()
    st.subheader("Mix de preço dos itens")

    _faixa_agg = (
        _it_validos.groupby("faixa_preco_item", as_index=False)
        .agg(
            itens=("item_id", "count"),
            receita=("valor_total_item_r", "sum"),
            preco_medio=("preco_unitario_r", "mean"),
        )
    )
    _ordem_preco = ["Até R$ 49", "R$ 50–99", "R$ 100–149", "R$ 150–199", "R$ 200+", "Sem preço"]
    _faixa_agg["ord"] = _faixa_agg["faixa_preco_item"].map({v: i for i, v in enumerate(_ordem_preco)})
    _faixa_agg = _faixa_agg.sort_values("ord")

    _col_i1, _col_i2 = st.columns([1.15, 1.85])
    with _col_i1:
        _fig_preco = go.Figure(go.Bar(
            x=_faixa_agg["faixa_preco_item"],
            y=_faixa_agg["itens"],
            marker_color="#1A73E8",
            text=_faixa_agg["receita"].apply(lambda v: fmt_brl(v, compact=True)),
            textposition="outside",
            cliponaxis=False,
        ))
        _fig_preco.update_layout(
            height=310, margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        _fig_preco.update_xaxes(showgrid=False, title_text="")
        _fig_preco.update_yaxes(title_text="Itens", gridcolor="#f0f0f0")
        apply_ptbr(_fig_preco)
        st.plotly_chart(_fig_preco, use_container_width=True)

    with _col_i2:
        _prod_top = (
            _it_validos.groupby(["referencia", "produto"], as_index=False)
            .agg(
                itens=("item_id", "count"),
                clientes=("cliente_id", "nunique"),
                receita=("valor_total_item_r", "sum"),
                preco_medio=("preco_unitario_r", "mean"),
                preco_max=("preco_unitario_r", "max"),
            )
            .sort_values(["preco_medio", "receita"], ascending=[False, False])
            .head(15)
        )
        _prod_top["Receita"] = _prod_top["receita"].apply(lambda v: fmt_brl(v, compact=True))
        _prod_top["Preço médio"] = _prod_top["preco_medio"].apply(fmt_brl)
        _prod_top["Preço máx."] = _prod_top["preco_max"].apply(fmt_brl)
        _prod_top["Itens"] = _prod_top["itens"].apply(fmt_num)
        _prod_top["Clientes"] = _prod_top["clientes"].apply(fmt_num)
        st.dataframe(
            _prod_top.rename(columns={"referencia": "Ref.", "produto": "Produto"})[
                ["Ref.", "Produto", "Itens", "Clientes", "Receita", "Preço médio", "Preço máx."]
            ],
            use_container_width=True,
            hide_index=True,
            height=310,
        )

    st.divider()
    st.subheader("Quem compra os itens mais caros")

    if _premium.empty:
        st.info("Não há massa suficiente de itens para identificar o recorte premium.")
    else:
        st.caption(
            f"Recorte premium = top 10% do preço unitário da base atual "
            f"(a partir de {fmt_brl(_cut_premium)})."
        )

        _premium["tipologia"] = _premium["grupo_cadastrado"].map(classificar_tipologia)
        _premium["faixa_distancia"] = "Sem localização"
        try:
            _geo_lookup = load_carteira_geo_cached()[["id", "tipologia", "faixa_distancia"]].rename(
                columns={"id": "cliente_id"}
            )
            _premium = _premium.drop(columns=["tipologia", "faixa_distancia"], errors="ignore").merge(
                _geo_lookup,
                on="cliente_id",
                how="left",
            )
            _premium["tipologia"] = _premium["tipologia"].fillna("Sem classificação")
            _premium["faixa_distancia"] = _premium["faixa_distancia"].fillna("Sem localização")
        except Exception:
            pass

        _col_p1, _col_p2 = st.columns([1.0, 2.0])
        with _col_p1:
            _premium_tip = (
                _premium.groupby("tipologia", as_index=False)
                .agg(
                    clientes=("cliente_id", "nunique"),
                    receita=("valor_total_item_r", "sum"),
                    preco_medio=("preco_unitario_r", "mean"),
                )
                .sort_values("clientes", ascending=True)
            )
            _fig_tip = go.Figure(go.Bar(
                y=_premium_tip["tipologia"],
                x=_premium_tip["clientes"],
                orientation="h",
                marker_color=[CORES_TIPOLOGIA.get(t, "#ccc") for t in _premium_tip["tipologia"]],
                text=_premium_tip["preco_medio"].apply(fmt_brl),
                textposition="outside",
                cliponaxis=False,
            ))
            _fig_tip.update_layout(
                height=320, margin=dict(l=0, r=70, t=10, b=0),
                plot_bgcolor="#fff", paper_bgcolor="#fff",
                showlegend=False,
            )
            _fig_tip.update_xaxes(title_text="Clientes premium", gridcolor="#f0f0f0")
            _fig_tip.update_yaxes(showgrid=False)
            apply_ptbr(_fig_tip)
            st.plotly_chart(_fig_tip, use_container_width=True)

        with _col_p2:
            _cli_top = (
                _premium.groupby(
                    ["cliente_id", "nome_exibicao", "tipologia", "cidade", "uf", "faixa_distancia"],
                    as_index=False,
                )
                .agg(
                    itens=("item_id", "count"),
                    produtos=("referencia", "nunique"),
                    maior_preco=("preco_unitario_r", "max"),
                    preco_medio=("preco_unitario_r", "mean"),
                    ltv=("cliente_ltv_r", "max"),
                    ticket=("cliente_ticket_medio_r", "max"),
                )
                .sort_values(["maior_preco", "itens"], ascending=[False, False])
                .head(20)
            )
            _cli_top["Itens"] = _cli_top["itens"].apply(fmt_num)
            _cli_top["SKUs"] = _cli_top["produtos"].apply(fmt_num)
            _cli_top["Maior preço"] = _cli_top["maior_preco"].apply(fmt_brl)
            _cli_top["Preço médio"] = _cli_top["preco_medio"].apply(fmt_brl)
            _cli_top["LTV"] = _cli_top["ltv"].apply(
                lambda v: fmt_brl(v, compact=True) if pd.notna(v) else "—"
            )
            _cli_top["Ticket cliente"] = _cli_top["ticket"].apply(
                lambda v: fmt_brl(v) if pd.notna(v) else "—"
            )
            st.dataframe(
                _cli_top.rename(columns={
                    "nome_exibicao": "Cliente",
                    "tipologia": "Perfil",
                    "cidade": "Cidade",
                    "uf": "UF",
                    "faixa_distancia": "Distância",
                })[[
                    "Cliente", "Perfil", "Cidade", "UF", "Distância",
                    "Itens", "SKUs", "Maior preço", "Preço médio",
                    "LTV", "Ticket cliente",
                ]],
                use_container_width=True,
                hide_index=True,
                height=320,
            )

        st.markdown("**Perfis × faixa de preço**")
        _heat_mix = (
            _it_validos.assign(
                tipologia=_it_validos["grupo_cadastrado"].map(classificar_tipologia)
            )
            .groupby(["tipologia", "faixa_preco_item"], as_index=False)
            .agg(itens=("item_id", "count"))
        )
        _heat_pivot = _heat_mix.pivot(
            index="tipologia",
            columns="faixa_preco_item",
            values="itens",
        ).reindex(index=ORDEM_TIPOLOGIAS, columns=_ordem_preco[:-1], fill_value=0)
        _heat_pivot = _heat_pivot.loc[_heat_pivot.sum(axis=1) > 0]
        if not _heat_pivot.empty:
            _fig_mix = go.Figure(go.Heatmap(
                z=_heat_pivot.values,
                x=list(_heat_pivot.columns),
                y=list(_heat_pivot.index),
                colorscale=[
                    [0.0, "#eef4ff"],
                    [0.30, "#bbd2ff"],
                    [0.65, "#5b96f7"],
                    [1.0, "#0d3b8e"],
                ],
                text=[[fmt_num(int(v)) if v > 0 else "—" for v in row] for row in _heat_pivot.values],
                texttemplate="%{text}",
                hovertemplate="Perfil: %{y}<br>Faixa: %{x}<br>Itens: %{z}<extra></extra>",
                showscale=False,
            ))
            _fig_mix.update_layout(
                height=max(260, 42 * len(_heat_pivot) + 80),
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="#fff",
            )
            apply_ptbr(_fig_mix)
            st.plotly_chart(_fig_mix, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 7 — VENDEDORES
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Vendedores":

    st.title("Performance de Vendedores")
    st.caption("Baseado no campo Funcionário/Vendedor do DAPIC · Apenas vendas fechadas")

    if df_vend.empty:
        st.warning("Dados de vendedores ainda não carregados. Execute etl/step4_vendedor.py primeiro.")
        st.stop()

    vend_seg = seg(df_vend)

    # ── KPIs gerais ───────────────────────────────────────────────────────
    tot_vend   = vend_seg["vendedor"].nunique()
    tot_fat    = vend_seg["valor_total_r"].sum()
    tot_vendas = vend_seg["qtd_vendas"].sum()
    tkt_medio  = vend_seg["ticket_medio_r"].mean()

    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Vendedores ativos",  fmt_num(tot_vend))
    with c2: st.metric("Faturamento total",  fmt_brl(tot_fat, compact=True))
    with c3: st.metric("Total de vendas",    fmt_num(tot_vendas))
    with c4: st.metric("Ticket médio geral", fmt_brl(tkt_medio))

    st.divider()

    # ── Ranking de faturamento total ──────────────────────────────────────
    st.subheader("Ranking de vendedores — faturamento total")

    rank = vend_seg.groupby("vendedor", as_index=False).agg(
        vendas=("qtd_vendas","sum"),
        clientes=("clientes_distintos","sum"),
        valor=("valor_total_r","sum"),
        ticket=("ticket_medio_r","mean"),
    ).sort_values("valor", ascending=False)

    col_bar, col_tbl = st.columns([3, 2])

    with col_bar:
        fig = px.bar(
            rank.head(15).sort_values("valor"),
            x="valor", y="vendedor", orientation="h",
            color="valor",
            color_continuous_scale=[[0,"#d2e3fc"],[1,"#1A73E8"]],
            labels={"valor":"Faturamento R$","vendedor":""},
            text="vendas",
        )
        fig.update_traces(
            texttemplate="%{text:,} vendas",
            textposition="outside",
        )
        fig.update_layout(
            height=460, margin=dict(l=0,r=90,t=10,b=0),
            coloraxis_showscale=False,
            plot_bgcolor="#fff", paper_bgcolor="#fff",
        )
        fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_yaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_tbl:
        rank["Faturamento"]  = rank["valor"].apply(fmt_brl)
        rank["Ticket Medio"] = rank["ticket"].apply(fmt_brl)
        exib_rank = rank.rename(columns={
            "vendedor":"Vendedor","vendas":"Vendas","clientes":"Clientes",
        })[["Vendedor","Vendas","Clientes","Faturamento","Ticket Medio"]]
        st.dataframe(exib_rank, use_container_width=True, height=460, hide_index=True)
        botao_csv(rank[["vendedor","vendas","clientes","valor","ticket"]],
                  "ranking_vendedores", key="csv_rank_vend")

    st.divider()

    # ── Evolução mensal por vendedor ──────────────────────────────────────
    st.subheader("Evolução mensal de faturamento")

    # Selector de vendedores para o gráfico
    top10_nomes = rank.head(10)["vendedor"].tolist()
    vend_sel = st.multiselect(
        "Vendedores", options=rank["vendedor"].tolist(),
        default=top10_nomes[:6],
    )

    if vend_sel:
        evo = vend_seg[vend_seg["vendedor"].isin(vend_sel)]
        evo_agg = evo.groupby(["mes","vendedor"], as_index=False)["valor_total_r"].sum()

        fig = px.line(
            evo_agg, x="mes", y="valor_total_r", color="vendedor",
            markers=True,
            labels={"mes":"","valor_total_r":"Faturamento R$","vendedor":"Vendedor"},
        )
        fig.update_layout(
            height=340, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", y=-0.35, font_size=11),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            hovermode="x unified",
        )
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        fig.update_xaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Mix de segmento por vendedor ──────────────────────────────────────
    st.subheader("Mix de segmento por vendedor — Top 12")

    mix = vend_seg[vend_seg["vendedor"].isin(rank.head(12)["vendedor"])].copy()
    mix_agg = mix.groupby(["vendedor","segmento"], as_index=False)["valor_total_r"].sum()

    # Normaliza para % dentro de cada vendedor
    mix_tot = mix_agg.groupby("vendedor")["valor_total_r"].transform("sum")
    mix_agg["pct"] = (mix_agg["valor_total_r"] / mix_tot * 100).round(1)

    # Ordena vendedores por faturamento total
    ordem_vend = rank.head(12)["vendedor"].tolist()

    fig = px.bar(
        mix_agg, x="pct", y="vendedor", color="segmento",
        orientation="h", barmode="stack",
        color_discrete_map=CORES_SEG,
        category_orders={"vendedor": list(reversed(ordem_vend))},
        labels={"pct":"% do faturamento","vendedor":"","segmento":"Segmento"},
        text="pct",
    )
    fig.update_traces(texttemplate="%{text:.0f}%", textposition="inside", textfont_size=10)
    fig.update_layout(
        height=400, margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h", y=-0.2, font_size=11),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        xaxis_range=[0,100],
    )
    fig.update_xaxes(ticksuffix="%", showgrid=False)
    fig.update_yaxes(showgrid=False)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Matriz qualidade da carteira por vendedor ─────────────────────────
    st.subheader("Matriz de qualidade da carteira por vendedor")
    st.caption(
        "Cada cliente é atribuído ao vendedor com mais vendas fechadas para ele "
        "(via `funcionario_vendedor` em fato_vendas). Quadrantes indicam quem "
        "fideliza versus quem queima leads."
    )

    cart_q = df_cart[df_cart["status_cliente"] != "sem_compra"].copy()
    if seg_filter != "Todos":
        cart_q = cart_q[cart_q["segmento"] == seg_filter]

    # Vincula cliente ↔ vendedor via fato_vendas
    cart_q = cart_q.merge(df_cli_vend, left_on="id", right_on="cliente_id", how="inner")

    q = cart_q.groupby(["vendedor_principal", "status_cliente"]).size().unstack(fill_value=0)
    for c in ["ativo", "em_risco", "hibernando", "hibernando_sazonal", "perdido"]:
        if c not in q.columns:
            q[c] = 0
    q["total"] = q[["ativo","em_risco","hibernando","hibernando_sazonal","perdido"]].sum(axis=1)
    q = q[q["total"] >= 20]
    q["pct_ativo"]   = q["ativo"] / q["total"] * 100
    q["pct_risco"]   = (q["em_risco"] + q["hibernando"] + q["hibernando_sazonal"]) / q["total"] * 100
    q["pct_perdido"] = q["perdido"] / q["total"] * 100

    q = q.reset_index().rename(columns={"vendedor_principal": "vendedor"})
    q = q.merge(rank[["vendedor","valor","vendas"]], on="vendedor", how="inner")

    if q.empty:
        st.info("Sem vendedores com ≥20 clientes atribuídos para o filtro atual.")
    else:
        mx = q["pct_ativo"].median()
        my = q["valor"].median()

        fig = px.scatter(
            q, x="pct_ativo", y="valor",
            size="total", color="pct_risco",
            hover_name="vendedor",
            color_continuous_scale=[[0, "#34A853"], [0.5, "#F9AB00"], [1, "#E8453C"]],
            custom_data=["vendedor","total","pct_risco","pct_perdido","vendas"],
            labels={
                "pct_ativo":"% da carteira ativa",
                "valor":"Faturamento R$",
                "pct_risco":"% em risco/hibernando",
                "total":"Clientes",
            },
            size_max=48,
        )
        fig.update_traces(
            marker=dict(opacity=0.85, line=dict(width=1, color="#fff")),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Carteira: %{customdata[1]:,.0f} clientes · %{customdata[4]:,.0f} vendas<br>"
                "% ativa: %{x:.1f}%<br>"
                "% risco/hibernando: %{customdata[2]:.1f}%<br>"
                "% perdidos: %{customdata[3]:.1f}%<br>"
                "Faturamento: R$ %{y:,.0f}<extra></extra>"
            ),
        )
        fig.add_vline(x=mx, line_dash="dot", line_color="#999",
                      annotation_text=f"mediana {mx:.0f}%",
                      annotation_position="top")
        fig.add_hline(y=my, line_dash="dot", line_color="#999",
                      annotation_text=f"mediana {fmt_brl(my, compact=True)}",
                      annotation_position="right")

        # Rótulos dos 5 maiores
        for _, r in q.nlargest(5, "valor").iterrows():
            fig.add_annotation(
                x=r["pct_ativo"], y=r["valor"],
                text=r["vendedor"].split()[0],
                showarrow=False, yshift=14,
                font=dict(size=10, color="#333"),
            )

        fig.update_layout(
            height=440, margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            coloraxis=dict(colorbar=dict(title="% risco", ticksuffix="%")),
        )
        fig.update_xaxes(ticksuffix="%", gridcolor="#f0f0f0")
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", gridcolor="#f0f0f0")
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            "<div style='font-size:0.82rem; color:#555; line-height:1.55;'>"
            "<b>Leitura dos quadrantes:</b> superior-direito = estrelas "
            "(alto faturamento, alta retenção); superior-esquerdo = "
            "queimam leads (alto faturamento, baixa retenção); "
            "inferior-direito = subaproveitados (bom pós-venda, pouco volume); "
            "inferior-esquerdo = atenção."
            "</div>",
            unsafe_allow_html=True,
        )

        # Tabela + exportação
        tbl_q = q.sort_values("pct_ativo", ascending=False).copy()
        tbl_q["Faturamento"]   = tbl_q["valor"].apply(fmt_brl)
        tbl_q["% ativa"]       = tbl_q["pct_ativo"].apply(lambda v: f"{fmt_num(v,1)}%")
        tbl_q["% risco/hib"]   = tbl_q["pct_risco"].apply(lambda v: f"{fmt_num(v,1)}%")
        tbl_q["% perdidos"]    = tbl_q["pct_perdido"].apply(lambda v: f"{fmt_num(v,1)}%")
        exib_q = tbl_q.rename(columns={"vendedor":"Vendedor","total":"Clientes"})[
            ["Vendedor","Clientes","% ativa","% risco/hib","% perdidos","Faturamento"]
        ]
        with st.expander(f"Tabela completa — {len(exib_q)} vendedores", expanded=False):
            st.dataframe(exib_q, use_container_width=True, hide_index=True)
            botao_csv(tbl_q[["vendedor","total","pct_ativo","pct_risco",
                              "pct_perdido","valor"]],
                      "qualidade_carteira_vendedores", key="csv_qual_vend")

    st.divider()

    # ── Clientes para reativação por vendedor ─────────────────────────────
    st.subheader("Clientes para reativação por vendedor")
    st.caption(
        "Cruza a carteira recuperável (em risco + hibernando + hibern. sazonal) "
        "com o vendedor predominante de cada cliente. Camadas A/B/C vêm do "
        "score RFV — prioriza operacionalmente quem vale mais recuperar."
    )

    recup = df_cart[df_cart["status_cliente"].isin(
        ["em_risco", "hibernando", "hibernando_sazonal"]
    )].copy()
    if seg_filter != "Todos":
        recup = recup[recup["segmento"] == seg_filter]

    recup = recup.merge(df_cli_vend, left_on="id", right_on="cliente_id", how="inner")

    if recup.empty:
        st.info("Sem clientes recuperáveis atribuíveis a vendedores para o filtro atual.")
    else:
        recup = calcular_score_reativacao(recup)

        # Agregação por vendedor × camada
        ag = (recup.groupby(["vendedor_principal", "camada"], as_index=False)
              .agg(n_cli=("id", "count"), valor=("valor_total_r", "sum")))

        CAMADAS = ["A — Alto valor", "B — Médio valor", "C — Base"]
        CORES_CAM = {
            "A — Alto valor":  "#1A73E8",
            "B — Médio valor": "#F9AB00",
            "C — Base":        "#BDC1C6",
        }

        # Pivota para ter colunas por camada (tanto contagem quanto valor)
        piv_n = ag.pivot_table(index="vendedor_principal", columns="camada",
                                values="n_cli", fill_value=0)
        piv_v = ag.pivot_table(index="vendedor_principal", columns="camada",
                                values="valor", fill_value=0.0)
        for cam in CAMADAS:
            if cam not in piv_n.columns: piv_n[cam] = 0
            if cam not in piv_v.columns: piv_v[cam] = 0.0

        piv_n = piv_n[CAMADAS]
        piv_v = piv_v[CAMADAS]
        piv_n["Total"]  = piv_n.sum(axis=1)
        piv_v["Valor"]  = piv_v.sum(axis=1)

        # Ordem de prioridade: primeiro quem tem mais Camada A; depois B; depois C.
        ordem = piv_n.sort_values(
            by=["A — Alto valor", "B — Médio valor", "Total"],
            ascending=[False, False, False],
        )
        top_n = 15
        ordem_top = ordem.head(top_n).index.tolist()

        col_bar, col_lado = st.columns([3, 2])

        with col_bar:
            # Barras horizontais empilhadas por camada (contagem de clientes)
            plot_df = piv_n.loc[ordem_top, CAMADAS].reset_index()
            # Eixo Y invertido: maior prioridade no topo
            y_order = list(reversed(ordem_top))

            fig = go.Figure()
            for cam in CAMADAS:
                fig.add_trace(go.Bar(
                    y=plot_df["vendedor_principal"],
                    x=plot_df[cam],
                    orientation="h",
                    name=cam,
                    marker_color=CORES_CAM[cam],
                    text=plot_df[cam].astype(int).astype(str),
                    textposition="inside",
                    insidetextanchor="middle",
                    textfont=dict(color="#fff", size=11),
                    hovertemplate=f"<b>%{{y}}</b><br>{cam}: %{{x}} clientes<extra></extra>",
                ))

            fig.update_layout(
                barmode="stack",
                height=max(280, 32 * len(ordem_top) + 80),
                margin=dict(l=0, r=10, t=10, b=0),
                plot_bgcolor="#fff", paper_bgcolor="#fff",
                legend=dict(orientation="h", y=-0.12, x=0, font_size=11),
                yaxis=dict(categoryorder="array", categoryarray=y_order),
            )
            fig.update_xaxes(
                title_text="Clientes recuperáveis",
                showgrid=True, gridcolor="#f0f0f0",
            )
            fig.update_yaxes(showgrid=False)
            apply_ptbr(fig)
            st.plotly_chart(fig, use_container_width=True)

        with col_lado:
            # KPI agregado + tabela lado a lado (Top 5 por Camada A)
            total_recup   = int(piv_n["Total"].sum())
            total_valor   = float(piv_v["Valor"].sum())
            total_cam_a   = int(piv_n["A — Alto valor"].sum())

            k1, k2 = st.columns(2)
            with k1:
                st.metric("Clientes recuperáveis", fmt_num(total_recup),
                          help="Em risco + hibernando + hibern. sazonal com vendedor atribuído")
            with k2:
                st.metric("Valor histórico", fmt_brl(total_valor, compact=True),
                          help="Soma do faturamento histórico desses clientes")
            st.metric("Dentro da Camada A (prioridade)", fmt_num(total_cam_a))

            # Tabela compacta: top 10 por Camada A
            tabela = piv_n.join(piv_v["Valor"]).loc[ordem_top].copy()
            tabela["Valor hist."] = tabela["Valor"].apply(lambda v: fmt_brl(v, compact=True))
            tabela = tabela.reset_index().rename(columns={
                "vendedor_principal": "Vendedor",
                "A — Alto valor": "A", "B — Médio valor": "B", "C — Base": "C",
            })[["Vendedor", "A", "B", "C", "Total", "Valor hist."]]
            st.caption(f"Top {len(tabela)} por concentração de Camada A")
            st.dataframe(tabela, use_container_width=True, hide_index=True, height=380)

        # Tabela completa expandida + CSV da lista detalhada
        with st.expander("Lista completa — clientes recuperáveis por vendedor",
                         expanded=False):
            detail = recup[[
                "vendedor_principal", "nome_exibicao", "segmento", "cidade", "uf",
                "status_cliente", "camada", "score", "ultima_compra",
                "dias_sem_compra", "total_compras", "valor_total_r", "ticket_medio_r",
            ]].copy()
            detail = detail.sort_values(
                ["vendedor_principal", "score"], ascending=[True, False]
            )

            exib_det = detail.rename(columns={
                "vendedor_principal": "Vendedor",
                "nome_exibicao": "Cliente",
                "segmento": "Segmento",
                "cidade": "Cidade",
                "uf": "UF",
                "camada": "Camada",
                "total_compras": "Compras",
                "dias_sem_compra": "Dias s/comprar",
            })
            exib_det["Status"]       = exib_det["status_cliente"].map(LABEL_STATUS)
            exib_det["Ult. Compra"]  = pd.to_datetime(
                exib_det["ultima_compra"], errors="coerce"
            ).dt.strftime("%d/%m/%Y")
            exib_det["Fat. Total"]   = exib_det["valor_total_r"].apply(fmt_brl)
            exib_det["Ticket Medio"] = exib_det["ticket_medio_r"].apply(fmt_brl)
            exib_det["Score"]        = exib_det["score"].apply(
                lambda v: f"{float(v):.2f}".replace(".", ",") if pd.notna(v) else "—"
            )

            st.dataframe(
                exib_det[[
                    "Vendedor", "Cliente", "Segmento", "Cidade", "UF",
                    "Status", "Camada", "Score", "Ult. Compra",
                    "Dias s/comprar", "Compras", "Fat. Total", "Ticket Medio",
                ]],
                use_container_width=True, hide_index=True, height=420,
            )
            botao_csv(
                detail, "reativacao_por_vendedor",
                "Exportar lista (CSV)", key="csv_reat_vend",
            )


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 6 — QUALIDADE DE DADOS
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Qualidade de Dados":

    st.title("Qualidade de Dados — Vendas Órfãs")
    st.caption(
        "Venda órfã = sem CPF/CNPJ registrado na transação, "
        "impossibilitando o vínculo com o cliente. "
        "Comum em PDV de varejo/atacarejo onde o operador não solicita o documento."
    )

    # ── Consolidação de segmentos ────────────────────────────────────────
    _SEG_PRINCIPAIS = {"1 - Atacado", "2 - Varejo", "5 - Atacarejo"}
    _orfas = df_orfas.copy()
    _orfas["segmento"] = _orfas["segmento"].apply(
        lambda s: s if s in _SEG_PRINCIPAIS else "Outros"
    )

    CORES_QD = {**CORES_SEG, "Outros": "#9E9E9E"}

    # ── KPIs ──────────────────────────────────────────────────────────────
    orf_tot = _orfas.groupby("segmento", as_index=False).agg(
        total_vendas=("total_vendas","sum"),
        vendas_orfas=("vendas_orfas","sum"),
        valor_total_r=("valor_total_r","sum"),
        valor_orfas_r=("valor_orfas_r","sum"),
    )
    tot_v  = orf_tot["total_vendas"].sum()
    tot_o  = orf_tot["vendas_orfas"].sum()
    val_t  = orf_tot["valor_total_r"].sum()
    val_o  = orf_tot["valor_orfas_r"].sum()
    pct_vinc_val = ((val_t - val_o) / val_t * 100) if val_t else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total de vendas",     fmt_num(tot_v))
    with c2: st.metric("Vendas vinculadas",   fmt_num(tot_v - tot_o))
    with c3: st.metric("Vendas órfãs",        fmt_num(tot_o))
    with c4: st.metric("Faturamento coberto", f"{pct_vinc_val:.1f}%".replace(".",","))

    st.divider()

    # ── % de órfãs por segmento (qtd e valor) ────────────────────────────
    st.subheader("Percentual de vendas órfãs por segmento")

    orf_tot["pct_orfas_qtd"] = (
        orf_tot["vendas_orfas"] / orf_tot["total_vendas"].replace(0, 1) * 100
    ).round(1)
    orf_tot["pct_orfas_val"] = (
        orf_tot["valor_orfas_r"] / orf_tot["valor_total_r"].replace(0, 1) * 100
    ).round(1)
    orf_tot = orf_tot.sort_values("pct_orfas_qtd", ascending=True)

    col_bar_q, col_bar_v = st.columns(2)

    with col_bar_q:
        st.markdown("**Por quantidade de vendas**")
        fig = go.Figure(go.Bar(
            x=orf_tot["pct_orfas_qtd"],
            y=orf_tot["segmento"],
            orientation="h",
            marker_color=[CORES_QD.get(s, "#9E9E9E") for s in orf_tot["segmento"]],
            text=orf_tot["pct_orfas_qtd"].apply(lambda v: f"{fmt_num(v,1)}%"),
            textposition="outside",
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=60, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis_range=[0, min(orf_tot["pct_orfas_qtd"].max() * 1.25, 100)],
        )
        fig.update_xaxes(ticksuffix="%", gridcolor="#f0f0f0")
        fig.update_yaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_bar_v:
        st.markdown("**Por valor faturado (R$)**")
        orf_val_sorted = orf_tot.sort_values("pct_orfas_val", ascending=True)
        fig = go.Figure(go.Bar(
            x=orf_val_sorted["pct_orfas_val"],
            y=orf_val_sorted["segmento"],
            orientation="h",
            marker_color=[CORES_QD.get(s, "#9E9E9E") for s in orf_val_sorted["segmento"]],
            text=orf_val_sorted["pct_orfas_val"].apply(lambda v: f"{fmt_num(v,1)}%"),
            textposition="outside",
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=60, t=10, b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis_range=[0, min(orf_val_sorted["pct_orfas_val"].max() * 1.25, 100)],
        )
        fig.update_xaxes(ticksuffix="%", gridcolor="#f0f0f0")
        fig.update_yaxes(showgrid=False)
        apply_ptbr(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Evolução mensal do % de órfãs ────────────────────────────────────
    st.subheader("Evolução mensal do percentual de órfãs")
    st.caption("Tendência do % de vendas sem cliente identificado, por segmento")

    orf_mes = _orfas[_orfas["mes"] >= "2024-01-01"].copy()
    orf_mes_agg = orf_mes.groupby(["mes","segmento"], as_index=False).agg(
        total_vendas=("total_vendas","sum"),
        vendas_orfas=("vendas_orfas","sum"),
    )
    orf_mes_agg["pct_orfas"] = (
        orf_mes_agg["vendas_orfas"]
        / orf_mes_agg["total_vendas"].replace(0, 1) * 100
    ).round(1)

    fig = px.line(
        orf_mes_agg, x="mes", y="pct_orfas", color="segmento",
        color_discrete_map=CORES_QD, markers=True,
        labels={"mes":"", "pct_orfas":"% órfãs", "segmento":"Segmento"},
    )
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", y=-0.3, font_size=11),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        hovermode="x unified",
    )
    fig.update_yaxes(ticksuffix="%", gridcolor="#f0f0f0", rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Tabela resumo ────────────────────────────────────────────────────
    st.subheader("Resumo por segmento")
    tbl = orf_tot.sort_values("total_vendas", ascending=False).copy()
    tbl["Vendas vinculadas"] = tbl["total_vendas"] - tbl["vendas_orfas"]
    tbl["Valor vinculado"]   = (tbl["valor_total_r"] - tbl["valor_orfas_r"]).apply(fmt_brl)
    tbl["Valor órfão"]       = tbl["valor_orfas_r"].apply(fmt_brl)
    tbl["% órfãs (qtd)"]     = tbl["pct_orfas_qtd"].apply(lambda v: f"{fmt_num(v,1)}%")
    tbl["% órfãs (valor)"]   = tbl["pct_orfas_val"].apply(lambda v: f"{fmt_num(v,1)}%")

    exib_orf = tbl.rename(columns={
        "segmento":"Segmento", "total_vendas":"Total vendas",
        "vendas_orfas":"Vendas órfãs",
    })[["Segmento","Total vendas","Vendas vinculadas","Vendas órfãs",
        "% órfãs (qtd)","Valor vinculado","Valor órfão","% órfãs (valor)"]]

    st.dataframe(exib_orf, use_container_width=True, hide_index=True)
    botao_csv(
        tbl[["segmento","total_vendas","vendas_orfas","pct_orfas_qtd",
             "valor_total_r","valor_orfas_r","pct_orfas_val"]],
        "qualidade_dados_orfas", key="csv_orfas",
    )
