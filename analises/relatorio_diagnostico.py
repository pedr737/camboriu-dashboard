"""
Gera o conjunto de tabelas e gráficos do relatório de diagnóstico inicial.

Saídas em analises/out/relatorio/:
    00_sumario.txt                  — números-âncora para o sumário executivo
    01_carteira_composicao.csv      — tipologia × status × camada
    02_pareto_clientes.csv/.html    — curva de Lorenz (concentração de receita)
    03_top_clientes.csv             — top 50 por valor histórico
    04_camadas_rfv.csv              — A/B/C × métricas
    05_faixas_distancia.csv/.html   — distribuição e valor por faixa
    06_penetracao_municipal.csv     — clientes ÷ população IBGE, top 50
    07_cidades_orfas.csv            — municípios próximos sem cliente
    08_gradiente_direcional.html    — lat/lon coloridos por volume
    09_recorrencia_tipologia.csv    — % recorrente, gap mediano
    10_sobrevivencia_km.csv/.html   — Kaplan-Meier tempo até 2ª compra
    11_ticket_faixa_tipologia.csv   — ticket mediano por faixa × tipologia
    12_coorte_retencao.csv/.html    — safra × meses desde 1ª compra
    13_heatmap_tempo_casa.html      — tempo de casa × recência
    14_entrada_saida.csv/.html      — fluxo mensal de ativação/inativação
    15_patrimonio_risco.csv         — LTV por status de risco
    16_perfil_fuga.csv              — clientes que entraram em inativo

Uso:
    python3 analises/relatorio_diagnostico.py
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "relatorio"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))
from geo import (
    GEO_CACHE_PATH,
    ORDEM_FAIXAS,
    SEDE_LAT,
    SEDE_LON,
    classificar_faixa,
    classificar_tipologia,
    haversine_km,
    normalizar_nome_cidade,
)

HOJE = pd.Timestamp.today().normalize()
TEMPLATE = "simple_white"
ORDEM_TIPOLOGIA = ["Lojista", "Sacoleiro", "Varejo", "Ex-atacado", "Inativo geral", "Interno", "Sem classificação"]


# ═════════════════════════════════════════════════════════════════════
# Infra
# ═════════════════════════════════════════════════════════════════════
def _conn_url() -> str:
    with open(ROOT / ".streamlit" / "secrets.toml", "rb") as f:
        cfg = tomllib.load(f)
    return cfg.get("DB_URL_POOLER") or cfg["DB_URL"]


def qry(sql: str) -> pd.DataFrame:
    conn = psycopg2.connect(_conn_url(), connect_timeout=15, options="-c statement_timeout=180000")
    try:
        with conn.cursor() as c:
            c.execute(sql)
            cols = [d[0] for d in c.description]
            return pd.DataFrame(c.fetchall(), columns=cols)
    finally:
        conn.close()


def _write_html(fig, fname: str) -> None:
    fig.update_layout(template=TEMPLATE, height=480, margin=dict(l=60, r=30, t=70, b=50))
    fig.write_html(OUT / fname, include_plotlyjs="cdn")


# ═════════════════════════════════════════════════════════════════════
# Carga
# ═════════════════════════════════════════════════════════════════════
def carregar_carteira() -> pd.DataFrame:
    print("→ Carteira...")
    df = qry("""
        SELECT id, nome_exibicao, segmento, cidade, uf, grupo_cadastrado,
               primeira_compra, ultima_compra,
               valor_total_r::float, ticket_medio_r::float,
               total_compras, dias_sem_compra, status_cliente
        FROM vw_ls_carteira
    """)
    df["primeira_compra"] = pd.to_datetime(df["primeira_compra"], errors="coerce")
    df["ultima_compra"] = pd.to_datetime(df["ultima_compra"], errors="coerce")
    df["tipologia"] = df["grupo_cadastrado"].map(classificar_tipologia)
    df["dias_de_casa"] = (HOJE - df["primeira_compra"]).dt.days

    if not GEO_CACHE_PATH.exists():
        print("  ! cache de municípios ausente — rode o dash para gerar")
        sys.exit(1)
    muni = pd.read_parquet(GEO_CACHE_PATH)
    df["_cidade_norm"] = df["cidade"].map(normalizar_nome_cidade)
    df = df.merge(
        muni[["cidade_norm", "uf", "lat", "lon", "populacao"]],
        left_on=["_cidade_norm", "uf"], right_on=["cidade_norm", "uf"], how="left",
    ).drop(columns=["cidade_norm", "_cidade_norm"], errors="ignore")

    df["distancia_km"] = df.apply(
        lambda r: haversine_km(float(r["lat"]), float(r["lon"]), SEDE_LAT, SEDE_LON)
        if pd.notna(r.get("lat")) and pd.notna(r.get("lon")) else np.nan,
        axis=1,
    )
    df["faixa"] = df["distancia_km"].map(classificar_faixa)

    # camadas RFV A/B/C por valor total acumulado (80/15/5)
    df_sorted = df.sort_values("valor_total_r", ascending=False).copy()
    df_sorted["_cum"] = df_sorted["valor_total_r"].cumsum()
    total = df_sorted["valor_total_r"].sum()
    df_sorted["camada"] = np.where(
        df_sorted["_cum"] <= 0.80 * total, "A — Alto valor",
        np.where(df_sorted["_cum"] <= 0.95 * total, "B — Médio valor", "C — Base"),
    )
    df = df_sorted.drop(columns=["_cum"]).sort_index()
    print(f"  {len(df):,} clientes")
    return df


def carregar_vendas() -> pd.DataFrame:
    print("→ Vendas...")
    df = qry("""
        SELECT cliente_id, data_venda, valor_total::float AS valor
        FROM fato_vendas
        WHERE status_venda IN ('Fechada', 'Fechado')
          AND data_venda IS NOT NULL
    """)
    df["data_venda"] = pd.to_datetime(df["data_venda"], errors="coerce")
    df = df.dropna(subset=["data_venda"])
    print(f"  {len(df):,} vendas")
    return df


# ═════════════════════════════════════════════════════════════════════
# 01 — Composição da carteira
# ═════════════════════════════════════════════════════════════════════
def composicao(df: pd.DataFrame) -> None:
    tab = (
        df.groupby(["tipologia", "status_cliente", "camada"])
        .agg(n=("id", "count"), receita=("valor_total_r", "sum"))
        .reset_index()
    )
    tab["pct_n"] = (tab["n"] / tab["n"].sum() * 100).round(1)
    tab["pct_receita"] = (tab["receita"] / tab["receita"].sum() * 100).round(1)
    tab.to_csv(OUT / "01_carteira_composicao.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 02 — Pareto / Lorenz
# ═════════════════════════════════════════════════════════════════════
def pareto(df: pd.DataFrame) -> dict:
    import plotly.graph_objects as go

    v = df["valor_total_r"].sort_values(ascending=False).values
    n = len(v)
    pct_cli = np.arange(1, n + 1) / n * 100
    pct_rec = np.cumsum(v) / v.sum() * 100

    tab = pd.DataFrame({"pct_clientes": pct_cli, "pct_receita": pct_rec})
    tab.to_csv(OUT / "02_pareto_clientes.csv", index=False)

    marcos = {p: float(np.interp(p, pct_cli, pct_rec)) for p in [5, 10, 20, 50]}

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pct_cli, y=pct_rec, mode="lines", name="Observado", line=dict(color="#1A73E8", width=3)))
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", name="Igualdade", line=dict(color="#bbb", dash="dash")))
    for p, v_ in marcos.items():
        fig.add_annotation(x=p, y=v_, text=f"{p}% → {v_:.0f}%", showarrow=True, arrowhead=2, ax=30, ay=-30)
    fig.update_layout(
        title=f"{marcos[10]:.0f}% da receita vem de 10% dos clientes (Lorenz)",
        xaxis_title="% clientes acumulado (do maior para o menor)",
        yaxis_title="% receita acumulada",
    )
    _write_html(fig, "02_pareto_clientes.html")
    return marcos


# ═════════════════════════════════════════════════════════════════════
# 03 — Top clientes
# ═════════════════════════════════════════════════════════════════════
def top_clientes(df: pd.DataFrame) -> None:
    cols = ["nome_exibicao", "tipologia", "cidade", "uf", "distancia_km",
            "valor_total_r", "ticket_medio_r", "total_compras",
            "primeira_compra", "ultima_compra", "status_cliente", "camada"]
    top = df.nlargest(50, "valor_total_r")[cols]
    top.to_csv(OUT / "03_top_clientes.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 04 — Camadas RFV
# ═════════════════════════════════════════════════════════════════════
def camadas_rfv(df: pd.DataFrame) -> None:
    tab = (
        df.groupby("camada")
        .agg(
            n_clientes=("id", "count"),
            receita=("valor_total_r", "sum"),
            ticket_mediano=("ticket_medio_r", "median"),
            compras_mediana=("total_compras", "median"),
        )
        .reset_index()
    )
    tab["pct_clientes"] = (tab["n_clientes"] / tab["n_clientes"].sum() * 100).round(1)
    tab["pct_receita"] = (tab["receita"] / tab["receita"].sum() * 100).round(1)
    tab.to_csv(OUT / "04_camadas_rfv.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 05 — Faixas de distância
# ═════════════════════════════════════════════════════════════════════
def faixas(df: pd.DataFrame) -> None:
    import plotly.express as px
    tab = (
        df.groupby("faixa")
        .agg(
            n_clientes=("id", "count"),
            receita=("valor_total_r", "sum"),
            ticket_mediano=("ticket_medio_r", "median"),
            compras_mediana=("total_compras", "median"),
        )
        .reindex(ORDEM_FAIXAS).dropna(how="all").reset_index()
    )
    tab["pct_clientes"] = (tab["n_clientes"] / tab["n_clientes"].sum() * 100).round(1)
    tab["pct_receita"] = (tab["receita"] / tab["receita"].sum() * 100).round(1)
    tab.to_csv(OUT / "05_faixas_distancia.csv", index=False)

    m = tab.melt(id_vars="faixa", value_vars=["pct_clientes", "pct_receita"],
                 var_name="métrica", value_name="%")
    fig = px.bar(m, x="faixa", y="%", color="métrica", barmode="group",
                 category_orders={"faixa": ORDEM_FAIXAS},
                 title="Distribuição de clientes e receita por faixa de distância")
    _write_html(fig, "05_faixas_distancia.html")


# ═════════════════════════════════════════════════════════════════════
# 06 — Penetração municipal
# ═════════════════════════════════════════════════════════════════════
def penetracao(df: pd.DataFrame) -> None:
    pen = (
        df.dropna(subset=["cidade", "uf", "populacao"])
        .groupby(["cidade", "uf"])
        .agg(
            clientes=("id", "count"),
            receita=("valor_total_r", "sum"),
            populacao=("populacao", "first"),
            distancia_km=("distancia_km", "first"),
        )
        .reset_index()
    )
    pen = pen[pen["populacao"] >= 5000]
    pen["clientes_por_10k_hab"] = (pen["clientes"] / pen["populacao"] * 10000).round(2)
    pen = pen.sort_values("clientes_por_10k_hab", ascending=False).head(50)
    pen.to_csv(OUT / "06_penetracao_municipal.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 07 — Cidades órfãs (próximas, sem cliente)
# ═════════════════════════════════════════════════════════════════════
def cidades_orfas(df: pd.DataFrame) -> None:
    muni = pd.read_parquet(GEO_CACHE_PATH)
    muni = muni.dropna(subset=["lat", "lon"]).copy()
    muni["distancia_km"] = muni.apply(
        lambda r: haversine_km(float(r["lat"]), float(r["lon"]), SEDE_LAT, SEDE_LON), axis=1
    )
    clientes_por_cidade = df.groupby(["cidade", "uf"])["id"].count().reset_index(name="clientes")
    clientes_por_cidade["_cn"] = clientes_por_cidade["cidade"].map(normalizar_nome_cidade)

    muni = muni.merge(
        clientes_por_cidade[["_cn", "uf", "clientes"]],
        left_on=["cidade_norm", "uf"], right_on=["_cn", "uf"], how="left",
    )
    muni["clientes"] = muni["clientes"].fillna(0)
    orfas = muni[(muni["clientes"] == 0) & (muni["distancia_km"] <= 300) &
                 (muni["populacao"].fillna(0) >= 10000)]
    orfas = orfas.sort_values("populacao", ascending=False).head(100)
    cols = ["cidade_orig", "uf", "populacao", "distancia_km"]
    orfas[[c for c in cols if c in orfas.columns]].to_csv(OUT / "07_cidades_orfas.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 08 — Gradiente direcional (mapa)
# ═════════════════════════════════════════════════════════════════════
def gradiente_direcional(df: pd.DataFrame) -> None:
    import plotly.express as px
    geo = df.dropna(subset=["lat", "lon"]).copy()
    agg = geo.groupby(["cidade", "uf", "lat", "lon"]).agg(
        clientes=("id", "count"), receita=("valor_total_r", "sum"),
    ).reset_index()
    fig = px.scatter_mapbox(
        agg, lat="lat", lon="lon", size="receita", color="clientes",
        color_continuous_scale="Blues", zoom=4,
        center=dict(lat=SEDE_LAT, lon=SEDE_LON), hover_name="cidade",
        title="Gradiente geográfico — volume de receita por cidade",
        mapbox_style="carto-positron",
    )
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=60, b=0))
    fig.write_html(OUT / "08_gradiente_direcional.html", include_plotlyjs="cdn")


# ═════════════════════════════════════════════════════════════════════
# 09 — Recorrência por tipologia
# ═════════════════════════════════════════════════════════════════════
def recorrencia(df: pd.DataFrame) -> None:
    # Janela mínima de observação: cliente precisa estar na base há pelo
    # menos um ciclo completo de retenção (240d = corte de "perdido" na
    # régua calibrada) para entrar na análise de recorrência.
    sub = df[df["dias_de_casa"] >= 240].copy()
    sub["gap_medio"] = np.where(
        sub["total_compras"] >= 2,
        (sub["ultima_compra"] - sub["primeira_compra"]).dt.days / (sub["total_compras"] - 1),
        np.nan,
    )
    tab = (
        sub.groupby("tipologia")
        .agg(
            n=("id", "count"),
            pct_recorrente=("total_compras", lambda s: round((s >= 2).mean() * 100, 1)),
            gap_mediano=("gap_medio", "median"),
            ticket_mediano=("ticket_medio_r", "median"),
        )
        .reindex(ORDEM_TIPOLOGIA).dropna(how="all").reset_index()
    )
    tab.to_csv(OUT / "09_recorrencia_tipologia.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 10 — Kaplan-Meier até 2ª compra
# ═════════════════════════════════════════════════════════════════════
def kaplan_meier(df: pd.DataFrame, vendas: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    v = vendas.sort_values(["cliente_id", "data_venda"])
    v["rn"] = v.groupby("cliente_id").cumcount() + 1
    t2 = v[v["rn"] == 2][["cliente_id", "data_venda"]].rename(
        columns={"cliente_id": "id", "data_venda": "t2"})
    sub = df.merge(t2, on="id", how="left")
    sub = sub[sub["primeira_compra"].notna()].copy()
    sub["dias_ate_evento"] = np.where(
        sub["t2"].notna(),
        (sub["t2"] - sub["primeira_compra"]).dt.days,
        (HOJE - sub["primeira_compra"]).dt.days,
    )
    sub["evento"] = sub["t2"].notna().astype(int)
    sub = sub[sub["dias_ate_evento"] > 0]

    def km(group: pd.DataFrame) -> pd.DataFrame:
        g = group.sort_values("dias_ate_evento")
        tempos = np.sort(g.loc[g["evento"] == 1, "dias_ate_evento"].unique())
        n = len(g); S = 1.0
        rows = [(0, 1.0, n)]
        for t in tempos:
            em_risco = (g["dias_ate_evento"] >= t).sum()
            eventos = ((g["dias_ate_evento"] == t) & (g["evento"] == 1)).sum()
            if em_risco == 0:
                continue
            S *= (1 - eventos / em_risco)
            rows.append((int(t), S, int(em_risco)))
        return pd.DataFrame(rows, columns=["dia", "S", "em_risco"])

    fig = go.Figure()
    linhas = []
    for tip in ["Lojista", "Sacoleiro", "Varejo"]:
        g = sub[sub["tipologia"] == tip]
        if len(g) < 30:
            continue
        k = km(g)
        k["tipologia"] = tip
        k["pct_retornou"] = (1 - k["S"]) * 100
        linhas.append(k)
        fig.add_trace(go.Scatter(x=k["dia"], y=k["pct_retornou"], mode="lines",
                                 name=f"{tip} (n={len(g)})"))
    if linhas:
        pd.concat(linhas).to_csv(OUT / "10_sobrevivencia_km.csv", index=False)
    fig.update_layout(
        title="Curva de retorno (Kaplan-Meier) — tempo até 2ª compra",
        xaxis_title="Dias desde a 1ª compra",
        yaxis_title="% de clientes que já retornaram",
        xaxis=dict(range=[0, 730]),
    )
    _write_html(fig, "10_sobrevivencia_km.html")


# ═════════════════════════════════════════════════════════════════════
# 11 — Ticket × faixa × tipologia
# ═════════════════════════════════════════════════════════════════════
def ticket_faixa(df: pd.DataFrame) -> None:
    sub = df[df["tipologia"].isin(["Lojista", "Sacoleiro", "Varejo"])]
    sub = sub[sub["faixa"] != "Sem localização"]
    tab = (
        sub.groupby(["faixa", "tipologia"])
        .agg(n=("id", "count"), ticket_mediano=("ticket_medio_r", "median"),
             ltv_mediano=("valor_total_r", "median"))
        .reset_index()
    )
    tab.to_csv(OUT / "11_ticket_faixa_tipologia.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 12 — Coorte de retenção (safra × meses)
# ═════════════════════════════════════════════════════════════════════
def coorte(df: pd.DataFrame, vendas: pd.DataFrame) -> None:
    import plotly.express as px
    primeira = df[["id", "primeira_compra"]].dropna().copy()
    primeira["safra"] = primeira["primeira_compra"].dt.to_period("Y").astype(str)

    v = vendas.rename(columns={"cliente_id": "id"}).merge(primeira, on="id", how="inner")
    v["meses_desde_1a"] = (
        (v["data_venda"].dt.year - v["primeira_compra"].dt.year) * 12
        + (v["data_venda"].dt.month - v["primeira_compra"].dt.month)
    )
    v = v[v["meses_desde_1a"] >= 0]

    coortes = (
        v.groupby(["safra", "meses_desde_1a"])["id"].nunique().reset_index(name="ativos")
    )
    base = primeira.groupby("safra")["id"].nunique().reset_index(name="base")
    coortes = coortes.merge(base, on="safra")
    coortes["pct_retencao"] = (coortes["ativos"] / coortes["base"] * 100).round(1)
    coortes = coortes[coortes["meses_desde_1a"] <= 36]
    coortes.to_csv(OUT / "12_coorte_retencao.csv", index=False)

    pivot = coortes.pivot(index="safra", columns="meses_desde_1a", values="pct_retencao")
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Blues",
                    labels=dict(x="Meses desde 1ª compra", y="Safra", color="% ativos"),
                    title="Retenção por safra de 1ª compra")
    _write_html(fig, "12_coorte_retencao.html")


# ═════════════════════════════════════════════════════════════════════
# 13 — Heatmap tempo de casa × recência
# ═════════════════════════════════════════════════════════════════════
def heatmap_casa_recencia(df: pd.DataFrame) -> None:
    import plotly.express as px
    sub = df.dropna(subset=["dias_de_casa", "dias_sem_compra"]).copy()
    # Faixas de tempo de casa (longevidade — independente da régua de status)
    bins_casa = [0, 180, 365, 730, 1460, 99999]
    lbl_casa = ["≤6m", "6–12m", "1–2a", "2–4a", "4a+"]
    # Faixas de recência alinhadas à régua calibrada de status (60/120/240)
    bins_rec = [-1, 30, 60, 120, 240, 99999]
    lbl_rec = ["≤30d", "31–60d", "61–120d", "121–240d", "240d+"]
    sub["casa"] = pd.cut(sub["dias_de_casa"], bins_casa, labels=lbl_casa)
    sub["recencia"] = pd.cut(sub["dias_sem_compra"], bins_rec, labels=lbl_rec)
    tab = sub.groupby(["casa", "recencia"])["id"].count().reset_index(name="n")
    pivot = tab.pivot(index="casa", columns="recencia", values="n").fillna(0)
    fig = px.imshow(pivot, text_auto=True, color_continuous_scale="Reds",
                    title="Clientes por tempo de casa × recência (onda de inativação)",
                    labels=dict(x="Tempo sem comprar", y="Tempo de casa", color="Clientes"))
    _write_html(fig, "13_heatmap_tempo_casa.html")


# ═════════════════════════════════════════════════════════════════════
# 14 — Entrada vs. saída mensal
# ═════════════════════════════════════════════════════════════════════
def entrada_saida(df: pd.DataFrame) -> None:
    import plotly.graph_objects as go
    entradas = df.dropna(subset=["primeira_compra"]).copy()
    entradas["mes"] = entradas["primeira_compra"].dt.to_period("M").astype(str)
    ent = entradas.groupby("mes")["id"].count().reset_index(name="entradas")

    saidas = df.dropna(subset=["ultima_compra"]).copy()
    # Cliente é considerado "saído" após 240d sem comprar (corte de "perdido"
    # na régua calibrada — antes era 180d pela régua antiga).
    saidas["mes_saida"] = (saidas["ultima_compra"] + pd.Timedelta(days=240)).dt.to_period("M").astype(str)
    sai = saidas.groupby("mes_saida")["id"].count().reset_index(name="inativacoes").rename(
        columns={"mes_saida": "mes"})

    fluxo = ent.merge(sai, on="mes", how="outer").fillna(0).sort_values("mes").tail(36)
    fluxo["saldo"] = fluxo["entradas"] - fluxo["inativacoes"]
    fluxo.to_csv(OUT / "14_entrada_saida.csv", index=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=fluxo["mes"], y=fluxo["entradas"], name="Novos clientes", marker_color="#1A73E8"))
    fig.add_trace(go.Bar(x=fluxo["mes"], y=-fluxo["inativacoes"], name="Inativações (180d)", marker_color="#c0392b"))
    fig.add_trace(go.Scatter(x=fluxo["mes"], y=fluxo["saldo"], name="Saldo", mode="lines+markers",
                             line=dict(color="#111", width=2)))
    fig.update_layout(title="Fluxo mensal de entrada e inativação (últimos 36 meses)",
                      barmode="relative", xaxis_tickangle=-45)
    _write_html(fig, "14_entrada_saida.html")


# ═════════════════════════════════════════════════════════════════════
# 15 — Patrimônio em risco
# ═════════════════════════════════════════════════════════════════════
def patrimonio_risco(df: pd.DataFrame) -> None:
    tab = (
        df.groupby("status_cliente")
        .agg(n=("id", "count"),
             ltv_total=("valor_total_r", "sum"),
             ltv_mediano=("valor_total_r", "median"))
        .reset_index()
    )
    tab["pct_ltv"] = (tab["ltv_total"] / tab["ltv_total"].sum() * 100).round(1)
    tab.to_csv(OUT / "15_patrimonio_risco.csv", index=False)


# ═════════════════════════════════════════════════════════════════════
# 16 — Perfil do cliente que foge
# ═════════════════════════════════════════════════════════════════════
def perfil_fuga(df: pd.DataFrame) -> None:
    # Corte de inatividade = "perdido" da régua calibrada (240d).
    # Antes era 180d pela régua antiga.
    inativos = df[df["dias_sem_compra"] >= 240]
    ativos = df[df["dias_sem_compra"] < 240]

    def resumo(g: pd.DataFrame, rotulo: str) -> dict:
        return {
            "grupo": rotulo, "n": len(g),
            "ticket_mediano": g["ticket_medio_r"].median(),
            "ltv_mediano": g["valor_total_r"].median(),
            "compras_medianas": g["total_compras"].median(),
            "distancia_mediana_km": g["distancia_km"].median(),
            "pct_lojista": (g["tipologia"] == "Lojista").mean() * 100,
            "pct_sacoleiro": (g["tipologia"] == "Sacoleiro").mean() * 100,
            "pct_varejo": (g["tipologia"] == "Varejo").mean() * 100,
        }

    pd.DataFrame([resumo(ativos, "Ativos"), resumo(inativos, "Inativos ≥240d")]).to_csv(
        OUT / "16_perfil_fuga.csv", index=False
    )


# ═════════════════════════════════════════════════════════════════════
# Sumário
# ═════════════════════════════════════════════════════════════════════
def sumario(df: pd.DataFrame, marcos_pareto: dict) -> None:
    # Corte "ativo" alinhado à régua calibrada: <240d (tudo que não é perdido).
    # "LTV em risco" usa a janela em risco + hibernando (61–240d), conforme
    # novos cortes — antes era 90–365.
    ativos = (df["dias_sem_compra"] < 240).sum()
    receita_total = df["valor_total_r"].sum()
    ltv_risco = df.loc[df["dias_sem_compra"].between(60, 240), "valor_total_r"].sum()
    top10_pct = marcos_pareto.get(10, 0)
    linhas = [
        f"Clientes na base              : {len(df):,}",
        f"Clientes ativos (<240d)       : {ativos:,} ({ativos/len(df)*100:.1f}%)",
        f"Receita histórica total       : R$ {receita_total:,.0f}",
        f"Top 10% dos clientes respondem: {top10_pct:.1f}% da receita",
        f"LTV em risco (60–240d)        : R$ {ltv_risco:,.0f}",
        f"Ticket mediano                : R$ {df['ticket_medio_r'].median():,.0f}",
        f"Compras medianas por cliente  : {df['total_compras'].median():.0f}",
    ]
    (OUT / "00_sumario.txt").write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


# ═════════════════════════════════════════════════════════════════════
def main() -> None:
    df = carregar_carteira()
    vendas = carregar_vendas()

    composicao(df)
    marcos = pareto(df)
    top_clientes(df)
    camadas_rfv(df)
    faixas(df)
    penetracao(df)
    cidades_orfas(df)
    gradiente_direcional(df)
    recorrencia(df)
    kaplan_meier(df, vendas)
    ticket_faixa(df)
    coorte(df, vendas)
    heatmap_casa_recencia(df)
    entrada_saida(df)
    patrimonio_risco(df)
    perfil_fuga(df)
    sumario(df, marcos)

    print(f"\n✔ Saídas em: {OUT}")


if __name__ == "__main__":
    main()
