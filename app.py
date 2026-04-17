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
from datetime import date, timedelta
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

DB_URL = st.secrets.get("DB_URL", "")  # configure em .streamlit/secrets.toml

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
    _test_conn = psycopg2.connect(DB_URL, connect_timeout=10)
    _test_conn.close()
except Exception as _e:
    st.error(f"Erro de conexão: **{type(_e).__name__}** — {_e}")
    st.info(f"DB_URL tem {len(DB_URL)} caracteres. Começa com: `{DB_URL[:25]}...`")
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


def calcular_score_reativacao(df: pd.DataFrame) -> pd.DataFrame:
    """Score RFV composto: 0.5·V + 0.3·F + 0.2·R_inv.

    Valor = ticket_medio / ticket_medio_segmento (cap 3)
    Frequência = total_compras / mediana_segmento (cap 3)
    Recência invertida = max(0, 1 - dias_sem_compra/365)
    Modificador sazonal: +0.2 em out-dez para clientes sazonais.
    """
    df = df.copy()
    if "segmento" not in df.columns or df.empty:
        df["score"] = 0.0
        df["camada"] = "C — restante"
        return df

    tm_seg = df.groupby("segmento")["ticket_medio_r"].transform("mean").replace(0, pd.NA)
    f_seg  = df.groupby("segmento")["total_compras"].transform("median").replace(0, pd.NA)

    df["v_norm"] = (df["ticket_medio_r"] / tm_seg).clip(upper=3).fillna(0)
    df["f_norm"] = (df["total_compras"] / f_seg).clip(upper=3).fillna(0)
    df["r_inv"]  = (1 - df["dias_sem_compra"] / 365).clip(lower=0).fillna(0)
    df["score"]  = 0.5 * df["v_norm"] + 0.3 * df["f_norm"] + 0.2 * df["r_inv"]

    hoje = pd.Timestamp.now()
    if hoje.month in (10, 11, 12) and "perfil_sazonalidade" in df.columns:
        df.loc[df["perfil_sazonalidade"] == "Sazonal", "score"] += 0.2

    rank_pct = df["score"].rank(pct=True, ascending=False)
    df["camada"] = pd.cut(
        rank_pct,
        bins=[0, 0.05, 0.20, 1.01],
        labels=["A — Top 5%", "B — 6-20%", "C — restante"],
        include_lowest=True,
    )
    return df.sort_values("score", ascending=False)


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

# ─────────────────────────────────────────────────────────────────────────────
# Conexão e cache
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_conn():
    if not DB_URL:
        st.error("DB_URL vazio — configure em Settings → Secrets no Streamlit Cloud.")
        st.stop()
    try:
        return psycopg2.connect(DB_URL, connect_timeout=10)
    except Exception as e:
        # Mostra o tipo do erro sem expor a connection string
        st.error(f"Falha na conexão com o banco: {type(e).__name__}: {e}")
        st.info(f"DB_URL presente: {'sim' if DB_URL else 'não'} | tamanho: {len(DB_URL)} chars")
        st.stop()


def qry(sql):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(sql)
            cols = [d[0] for d in c.description]
            return pd.DataFrame(c.fetchall(), columns=cols)
    except Exception:
        st.cache_resource.clear()
        conn2 = psycopg2.connect(DB_URL)
        with conn2.cursor() as c:
            c.execute(sql)
            cols = [d[0] for d in c.description]
            return pd.DataFrame(c.fetchall(), columns=cols)


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
        SELECT dc.cidade_norm AS cidade,
               COUNT(DISTINCT dc.id)               AS clientes,
               COUNT(fv.id)                         AS vendas,
               ROUND(SUM(fv.valor_total_liquido)::numeric/100,0)::float AS valor_r
        FROM dim_clientes dc
        JOIN fato_vendas fv ON fv.cliente_id = dc.id
        WHERE dc.estado_norm = 'PE'
          AND fv.status_venda IN ('Fechada','Fechado')
          AND dc.cidade_norm IS NOT NULL
        GROUP BY 1 ORDER BY 3 DESC LIMIT 25
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


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

PAINEIS = ["Executivo", "Recorrência", "Sazonalidade", "Operacional", "Vendedores",
           "Qualidade de Dados"]

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
    ca1, ca2, ca3 = st.columns(3)
    with ca1:
        if st.button("Top clientes para reativação →",
                     use_container_width=True, key="nav_reat"):
            st.session_state["_nav_target"] = "Operacional"
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
    pe_top = df_pe.head(20)

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

    # ── Top 20 Atacadistas ─────────────────────────────────────────────────
    st.subheader("Top 20 clientes por faturamento — Atacado")
    top20 = df_cart[df_cart["segmento"]=="1 - Atacado"].nlargest(20,"valor_total_r").copy()
    top20["Status"]        = top20["status_cliente"].map(LABEL_STATUS)
    top20["Fat. Total"]    = top20["valor_total_r"].apply(fmt_brl)
    top20["Ticket Medio"]  = top20["ticket_medio_r"].apply(fmt_brl)
    top20["Ultima Compra"] = top20["ultima_compra"].dt.strftime("%d/%m/%Y")

    def cor_status(val):
        m = {
            "Ativo":           "background-color:#d4edda;color:#155724",
            "Em Risco":        "background-color:#fff3cd;color:#856404",
            "Hibernando":      "background-color:#ffe0b2;color:#e65100",
            "Perdido":         "background-color:#f8d7da;color:#721c24",
            "Hibern. Sazonal": "background-color:#ffe0b2;color:#e65100",
        }
        return m.get(val, "")

    exib = top20.rename(columns={
        "nome_exibicao":"Cliente","cidade":"Cidade","uf":"UF","total_compras":"Compras",
    })[["Cliente","Cidade","UF","Compras","Ultima Compra","Fat. Total","Ticket Medio","Status"]]

    st.dataframe(
        exib.style.map(cor_status, subset=["Status"]),
        use_container_width=True, height=430, hide_index=True,
    )
    botao_csv(exib, "top20_atacadistas_camboriu", key="csv_top20")


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
# PAINEL 4 — OPERACIONAL
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Operacional":

    st.title("Painel Operacional")

    with st.expander("Definições de status de cliente", expanded=False):
        st.markdown("""
<div class="nota-status">
<b>Ativo</b> — última compra há menos de 90 dias<br>
<b>Em Risco</b> — última compra entre 91 e 180 dias<br>
<b>Hibernando</b> — última compra entre 181 e 365 dias<br>
<b>Hibernando Sazonal</b> — cliente sazonal que comprou na última temporada mas não na atual<br>
<b>Perdido</b> — última compra há mais de 365 dias
</div>
""", unsafe_allow_html=True)

    # ── KPIs reativação ───────────────────────────────────────────────────
    reat_d = seg(df_reat)
    n_risco  = (reat_d["status_cliente"]=="em_risco").sum()
    n_hibern = reat_d["status_cliente"].isin(["hibernando","hibernando_sazonal"]).sum()
    n_perdid = (reat_d["status_cliente"]=="perdido").sum()
    val_risco= reat_d[reat_d["status_cliente"]=="em_risco"]["valor_total_r"].sum()

    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Em Risco",    fmt_num(n_risco),  help="91–180 dias sem comprar")
    with c2: st.metric("Hibernando",  fmt_num(n_hibern), help="181–365 dias sem comprar")
    with c3: st.metric("Perdidos",    fmt_num(n_perdid), help="Mais de 365 dias sem comprar")
    with c4: st.metric("Valor histórico em risco", fmt_brl(val_risco, compact=True))

    st.divider()

    # ── Score RFV + carteira enriquecida ──────────────────────────────────
    # Aplicado somente aos recuperáveis (em risco + hibernando sazonal/normal).
    reat_alvos = reat_d[reat_d["status_cliente"].isin(
        ["em_risco", "hibernando", "hibernando_sazonal"]
    )].copy()

    if not reat_alvos.empty:
        saz_map = (
            df_cart.drop_duplicates("nome_exibicao")
            .set_index("nome_exibicao")["perfil_sazonalidade"]
            .to_dict()
        )
        reat_alvos["perfil_sazonalidade"] = reat_alvos["nome_exibicao"].map(saz_map)
        reat_alvos = calcular_score_reativacao(reat_alvos)

    # ── Cartões das camadas A/B/C ─────────────────────────────────────────
    st.subheader("Camadas por score RFV")
    st.caption(
        "Score = 0,5·Valor + 0,3·Frequência + 0,2·Recência invertida · "
        "Modificador sazonal +0,2 para clientes sazonais em Out–Dez"
    )

    def _camada(df, rotulo):
        sub = df[df["camada"] == rotulo] if "camada" in df.columns else df.head(0)
        n = len(sub)
        v = sub["valor_total_r"].sum() if n else 0
        return sub, n, v

    cam_a, n_a, v_a = _camada(reat_alvos, "A — Top 5%")
    cam_b, n_b, v_b = _camada(reat_alvos, "B — 6-20%")
    cam_c, n_c, v_c = _camada(reat_alvos, "C — restante")

    CARD_CSS = (
        "padding:14px 16px; border-radius:8px; border:1px solid #e0e0e0; "
        "background:#fff; box-shadow:0 1px 2px rgba(0,0,0,0.04);"
    )

    def _card(col, titulo, n, v, cor_borda):
        with col:
            st.markdown(
                f"<div style='{CARD_CSS} border-left:4px solid {cor_borda};'>"
                f"<div style='font-size:0.78rem; color:#666; font-weight:600; "
                f"text-transform:uppercase; letter-spacing:0.04em;'>{titulo}</div>"
                f"<div style='font-size:1.45rem; font-weight:700; color:#111; "
                f"margin-top:4px;'>{fmt_num(n)} clientes</div>"
                f"<div style='font-size:0.9rem; color:#333; margin-top:2px;'>"
                f"{fmt_brl(v, compact=True)} em valor histórico</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    col_a, col_b, col_c = st.columns(3)
    _card(col_a, "Camada A — Top 5%",   n_a, v_a, "#1A73E8")
    _card(col_b, "Camada B — 6 a 20%",  n_b, v_b, "#F9AB00")
    _card(col_c, "Camada C — restante", n_c, v_c, "#BDC1C6")

    exp_a, exp_b, exp_c = st.columns(3)
    with exp_a:
        if n_a: botao_csv(cam_a, "reativacao_camada_A", "Baixar Camada A", key="csv_cam_a")
    with exp_b:
        if n_b: botao_csv(cam_b, "reativacao_camada_B", "Baixar Camada B", key="csv_cam_b")
    with exp_c:
        if n_c: botao_csv(cam_c, "reativacao_camada_C", "Baixar Camada C", key="csv_cam_c")

    st.divider()

    # ── Lista de reativação ───────────────────────────────────────────────
    st.subheader("Lista de clientes para reativação")

    # Enriquece com vendedor predominante (por nº de vendas fechadas),
    # que é mais útil operacionalmente do que o representante fixo do cadastro.
    vend_map = (
        df_cart[["id", "nome_exibicao"]]
        .merge(df_cli_vend, left_on="id", right_on="cliente_id", how="inner")
        .drop_duplicates("nome_exibicao")
        .set_index("nome_exibicao")["vendedor_principal"]
    )
    reat_d = reat_d.copy()
    reat_d["vendedor"] = reat_d["nome_exibicao"].map(vend_map)

    f1,f2,f3 = st.columns(3)
    with f1:
        st_sel = st.multiselect(
            "Status", ["em_risco","hibernando","hibernando_sazonal","perdido"],
            default=["em_risco","hibernando_sazonal"],
        )
    with f2:
        ufs = ["Todos"] + sorted(reat_d["uf"].dropna().unique().tolist())
        uf_sel = st.selectbox("UF", ufs)
    with f3:
        vend_opts = ["Todos"] + sorted(reat_d["vendedor"].dropna().unique().tolist())
        vend_sel = st.selectbox("Vendedor", vend_opts)

    reat_f = reat_d[reat_d["status_cliente"].isin(st_sel)]
    if uf_sel   != "Todos": reat_f = reat_f[reat_f["uf"]==uf_sel]
    if vend_sel != "Todos": reat_f = reat_f[reat_f["vendedor"]==vend_sel]

    reat_f = reat_f.copy()
    if not reat_alvos.empty and "score" in reat_alvos.columns:
        score_map = (
            reat_alvos.drop_duplicates("nome_exibicao")
            .set_index("nome_exibicao")[["score", "camada"]]
        )
        reat_f = reat_f.join(score_map, on="nome_exibicao")
    else:
        reat_f["score"]  = pd.NA
        reat_f["camada"] = pd.NA

    reat_f = reat_f.sort_values("score", ascending=False, na_position="last")

    reat_f["Fat. Total"]    = reat_f["valor_total_r"].apply(fmt_brl)
    reat_f["Ticket Medio"]  = reat_f["ticket_medio_r"].apply(fmt_brl)
    reat_f["Ultima Compra"] = reat_f["ultima_compra"].dt.strftime("%d/%m/%Y")
    reat_f["Status"]        = reat_f["status_cliente"].map(LABEL_STATUS)
    reat_f["Score"]         = reat_f["score"].apply(
        lambda v: f"{float(v):.2f}".replace(".", ",") if pd.notna(v) else "—"
    )
    reat_f["Camada"]        = reat_f["camada"].astype("object").fillna("—")

    def _bg(val):
        m={"Em Risco":"background-color:#fff3cd","Hibernando":"background-color:#ffe0b2",
           "Perdido":"background-color:#f8d7da","Hibern. Sazonal":"background-color:#ffe0b2"}
        return m.get(val,"")

    def _bg_cam(val):
        m={"A — Top 5%":"background-color:#d2e3fc;color:#0d47a1;font-weight:600",
           "B — 6-20%":"background-color:#fff3cd;color:#856404",
           "C — restante":"background-color:#f1f3f4;color:#555"}
        return m.get(str(val),"")

    exib_r = reat_f.rename(columns={
        "nome_exibicao":"Cliente","segmento":"Segmento","cidade":"Cidade","uf":"UF",
        "vendedor":"Vendedor","total_compras":"Compras",
        "dias_sem_compra":"Dias s/comprar",
    })[["Cliente","Segmento","Cidade","UF","Vendedor","Status","Camada","Score",
        "Ultima Compra","Dias s/comprar","Compras","Fat. Total","Ticket Medio"]]
    exib_r["Vendedor"] = exib_r["Vendedor"].fillna("—")

    st.dataframe(
        exib_r.style.map(_bg, subset=["Status"]).map(_bg_cam, subset=["Camada"]),
        use_container_width=True, height=460, hide_index=True,
    )
    n_str = f"{len(exib_r):,}".replace(",", ".")
    st.caption(
        f"{n_str} clientes exibidos · Vendedor = funcionário/vendedor "
        "predominante (maior nº de vendas fechadas)"
    )

    botao_csv(
        reat_f[["nome_exibicao","segmento","cidade","uf","vendedor",
                "status_cliente","camada","score","ultima_compra","dias_sem_compra",
                "total_compras","valor_total_r","ticket_medio_r"]],
        "reativacao_camboriu", "Exportar lista (CSV)", key="csv_reat_full",
    )

    st.divider()

    # ── Novos clientes — últimos 60 dias ──────────────────────────────────
    st.subheader("Novos clientes — últimos 60 dias")
    hoje = pd.Timestamp(date.today())
    novos60 = df_cart[
        (hoje - df_cart["primeira_compra"]).dt.days <= 60
    ].copy()
    if seg_filter != "Todos":
        novos60 = novos60[novos60["segmento"]==seg_filter]
    novos60 = novos60.sort_values("valor_total_r", ascending=False)
    novos60["Fat. Total"]   = novos60["valor_total_r"].apply(fmt_brl)
    novos60["Ticket Medio"] = novos60["ticket_medio_r"].apply(fmt_brl)
    novos60["1a Compra"]    = novos60["primeira_compra"].dt.strftime("%d/%m/%Y")

    exib_novos = novos60.rename(
        columns={"nome_exibicao":"Cliente","total_compras":"Compras"}
    )[["Cliente","segmento","cidade","uf","1a Compra","Compras","Fat. Total","Ticket Medio"]]

    st.dataframe(exib_novos, use_container_width=True, height=300, hide_index=True)
    st.caption(f"{len(novos60):,} novos clientes nos últimos 60 dias".replace(",","."))
    if not novos60.empty:
        botao_csv(exib_novos, "novos_clientes_60d", key="csv_novos60")

    st.divider()

    st.caption("Para análise completa de performance por vendedor, acesse o painel **Vendedores**.")


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 5 — VENDEDORES
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

        CAMADAS = ["A — Top 5%", "B — 6-20%", "C — restante"]
        CORES_CAM = {
            "A — Top 5%":   "#1A73E8",
            "B — 6-20%":    "#F9AB00",
            "C — restante": "#BDC1C6",
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
            by=["A — Top 5%", "B — 6-20%", "Total"], ascending=[False, False, False]
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
            total_cam_a   = int(piv_n["A — Top 5%"].sum())

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
                "A — Top 5%": "A", "B — 6-20%": "B", "C — restante": "C",
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
