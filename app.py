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

DB_URL = st.secrets.get("DB_URL", "postgresql://postgres:camboriu-axivero@db.amvcvoicgvwgrudxeboa.supabase.co:5432/postgres?sslmode=require")

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
            senha_correta = st.secrets.get("SENHA", "camboriu")
            if pwd == senha_correta:
                st.session_state["_auth"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

if not _check_password():
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
""", height=0, width=0)

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

# ─────────────────────────────────────────────────────────────────────────────
# Conexão e cache
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_conn():
    return psycopg2.connect(DB_URL)


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
        WHERE mes_entrada >= '2024-01-01' AND meses_desde_entrada <= 12
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


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## Camboriú")
    st.caption("Gestão de Carteira · 2024–2026")
    st.divider()

    painel = st.radio(
        "Painel",
        ["Executivo", "Recorrência", "Sazonalidade", "Operacional", "Vendedores"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Filtros")

    seg_options = ["Todos", "1 - Atacado", "2 - Varejo", "5 - Atacarejo"]
    seg_filter = st.selectbox("Segmento", seg_options)

    st.divider()
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache atualizado a cada 1h")


# ─────────────────────────────────────────────────────────────────────────────
# Carrega dados
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Carregando..."):
    df_fat   = load_faturamento()
    df_cart  = load_carteira()
    df_reat  = load_reativacao()
    df_pag   = load_pagamentos()
    df_cohort= load_cohort()
    df_novos = load_novos()
    df_pe    = load_cidades_pe()
    df_vend  = load_vendedores()


def seg(df, col="segmento"):
    if seg_filter == "Todos" or col not in df.columns:
        return df
    return df[df[col] == seg_filter]


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 1 — EXECUTIVO
# ═════════════════════════════════════════════════════════════════════════════

if painel == "Executivo":

    st.title("Visão Executiva")

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

    # ── KPIs ──────────────────────────────────────────────────────────────
    cart_ativa = df_cart[df_cart["status_cliente"] != "sem_compra"]
    cart_seg   = seg(cart_ativa)

    ativos     = (cart_seg["status_cliente"] == "ativo").sum()
    em_risco   = (cart_seg["status_cliente"] == "em_risco").sum()
    hibernando = cart_seg["status_cliente"].isin(["hibernando","hibernando_sazonal"]).sum()
    perdidos   = (cart_seg["status_cliente"] == "perdido").sum()

    hoje      = pd.Timestamp(date.today())
    fat_seg   = seg(df_fat)
    fat_12m   = fat_seg["valor_total_r"].sum()
    fat_12m_s = fmt_brl(fat_12m, compact=True)

    novos_30 = df_cart[
        (hoje - df_cart["primeira_compra"]).dt.days <= 30
    ]
    if seg_filter != "Todos":
        novos_30 = novos_30[novos_30["segmento"] == seg_filter]
    n_novos_30 = len(novos_30)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: st.metric("Ativos",         fmt_num(ativos))
    with c2: st.metric("Em Risco",        fmt_num(em_risco))
    with c3: st.metric("Hibernando",      fmt_num(hibernando))
    with c4: st.metric("Perdidos",        fmt_num(perdidos))
    with c5: st.metric("Faturamento (período)", fat_12m_s)
    with c6: st.metric("Novos (30 dias)", fmt_num(n_novos_30))

    st.divider()

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
        status_counts["label"] = status_counts["status_cliente"].map(LABEL_STATUS)
        status_counts["cor"]   = status_counts["status_cliente"].map(CORES_STATUS)

        fig = go.Figure(go.Pie(
            labels=status_counts["label"],
            values=status_counts["n"],
            marker_colors=status_counts["cor"],
            hole=0.45,
            textinfo="label+percent",
            insidetextorientation="radial",
        ))
        fig.update_layout(
            height=300, margin=dict(l=0,r=0,t=10,b=0), showlegend=False,
            paper_bgcolor="#fff",
        )
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


# ═════════════════════════════════════════════════════════════════════════════
# PAINEL 2 — RECORRÊNCIA
# ═════════════════════════════════════════════════════════════════════════════

elif painel == "Recorrência":

    st.title("Recorrência e Comportamento")

    # ── Cohort ────────────────────────────────────────────────────────────
    st.subheader("Retenção por cohort — % de clientes que voltaram a comprar")
    st.caption("Cada linha = grupo pelo mês da 1ª compra · Coluna 0 = mês de entrada · +N = N meses depois")

    pivot = df_cohort.pivot_table(
        index="mes_entrada", columns="meses_desde_entrada",
        values="pct_retencao", aggfunc="mean",
    )
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

    # ── Lista de reativação ───────────────────────────────────────────────
    st.subheader("Lista de clientes para reativação")

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
        reps_opts = ["Todos"] + sorted(reat_d["representante_principal"].dropna().unique().tolist())
        rep_sel = st.selectbox("Representante", reps_opts)

    reat_f = reat_d[reat_d["status_cliente"].isin(st_sel)]
    if uf_sel  != "Todos": reat_f = reat_f[reat_f["uf"]==uf_sel]
    if rep_sel != "Todos": reat_f = reat_f[reat_f["representante_principal"]==rep_sel]

    reat_f = reat_f.copy()
    reat_f["Fat. Total"]    = reat_f["valor_total_r"].apply(fmt_brl)
    reat_f["Ticket Medio"]  = reat_f["ticket_medio_r"].apply(fmt_brl)
    reat_f["Ultima Compra"] = reat_f["ultima_compra"].dt.strftime("%d/%m/%Y")
    reat_f["Status"]        = reat_f["status_cliente"].map(LABEL_STATUS)

    def _bg(val):
        m={"Em Risco":"background-color:#fff3cd","Hibernando":"background-color:#ffe0b2",
           "Perdido":"background-color:#f8d7da","Hibern. Sazonal":"background-color:#ffe0b2"}
        return m.get(val,"")

    exib_r = reat_f.rename(columns={
        "nome_exibicao":"Cliente","segmento":"Segmento","cidade":"Cidade","uf":"UF",
        "representante_principal":"Representante","total_compras":"Compras",
        "dias_sem_compra":"Dias s/comprar",
    })[["Cliente","Segmento","Cidade","UF","Representante","Status",
        "Ultima Compra","Dias s/comprar","Compras","Fat. Total","Ticket Medio"]]

    st.dataframe(
        exib_r.style.map(_bg, subset=["Status"]),
        use_container_width=True, height=460, hide_index=True,
    )
    st.caption(f"{len(exib_r):,} clientes exibidos".replace(",","."))

    csv = reat_f[["nome_exibicao","segmento","cidade","uf","representante_principal",
                  "status_cliente","ultima_compra","dias_sem_compra","total_compras",
                  "valor_total_r","ticket_medio_r"]].to_csv(index=False).encode("utf-8")
    st.download_button("Exportar lista (CSV)", csv, "reativacao_camboriu.csv", "text/csv")

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

    st.dataframe(
        novos60.rename(columns={"nome_exibicao":"Cliente","total_compras":"Compras"})[
            ["Cliente","segmento","cidade","uf","1a Compra","Compras","Fat. Total","Ticket Medio"]
        ],
        use_container_width=True, height=300, hide_index=True,
    )
    st.caption(f"{len(novos60):,} novos clientes nos últimos 60 dias".replace(",","."))

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
        st.dataframe(
            rank.rename(columns={
                "vendedor":"Vendedor","vendas":"Vendas","clientes":"Clientes",
            })[["Vendedor","Vendas","Clientes","Faturamento","Ticket Medio"]],
            use_container_width=True, height=460, hide_index=True,
        )

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

    # ── Ticket médio vs volume de vendas (dispersão) ──────────────────────
    st.subheader("Ticket médio vs volume de vendas")

    disp = vend_seg.groupby("vendedor", as_index=False).agg(
        vendas=("qtd_vendas","sum"),
        ticket=("ticket_medio_r","mean"),
        valor=("valor_total_r","sum"),
    )

    fig = px.scatter(
        disp, x="vendas", y="ticket",
        size="valor",
        color="valor",
        custom_data=["vendedor", "valor"],
        color_continuous_scale=[[0,"#d2e3fc"],[1,"#1A73E8"]],
        labels={"vendas":"Qtd vendas","ticket":"Ticket médio R$","valor":"Faturamento"},
        size_max=55,
    )
    fig.update_traces(
        marker=dict(opacity=0.85, line=dict(width=1, color="#fff")),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Qtd vendas: %{x:,.0f}<br>"
            "Ticket médio: R$ %{y:,.0f}<br>"
            "Faturamento: R$ %{customdata[1]:,.0f}<extra></extra>"
        ),
    )
    # Anota apenas o top 5 por faturamento (evita poluição visual)
    top5 = disp.nlargest(5, "valor")
    for _, r in top5.iterrows():
        fig.add_annotation(
            x=r["vendas"], y=r["ticket"],
            text=r["vendedor"].split()[0],  # só primeiro nome
            showarrow=False,
            yshift=14,
            font=dict(size=10, color="#333"),
        )
    fig.update_layout(
        height=440, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        coloraxis_showscale=False,
    )
    fig.update_yaxes(tickprefix="R$ ", gridcolor="#f0f0f0")
    fig.update_xaxes(showgrid=False)
    apply_ptbr(fig)
    st.plotly_chart(fig, use_container_width=True)
