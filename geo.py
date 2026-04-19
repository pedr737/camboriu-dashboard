"""Helpers geográficos para o painel Demographics."""

from math import asin, cos, pi, radians, sin, sqrt
from pathlib import Path
import unicodedata

import pandas as pd
import streamlit as st

SEDE_LAT = -7.9580
SEDE_LON = -36.2025  # Santa Cruz do Capibaribe / PE

GEO_CACHE_PATH = Path(__file__).parent / "data" / "municipios_geo.parquet"

_KELVINS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/"
    "main/csv/municipios.csv"
)
_IBGE_POP_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/2022/"
    "variaveis/9324?localidades=N6[all]"
)

FAIXAS = [
    (0,    50,            "Até 50 km · Entorno"),
    (50,   150,           "50–150 km · Bate-volta"),
    (150,  300,           "150–300 km · Viagem curta"),
    (300,  600,           "300–600 km · Viagem planejada"),
    (600,  1200,          "600–1.200 km · Mercado distante"),
    (1200, float("inf"),  "1.200+ km · Muito distante"),
]
ORDEM_FAIXAS = [f[2] for f in FAIXAS] + ["Sem localização"]

_MAPA_TIPOLOGIA = {
    "LOJISTA":         "Lojista",
    "SACOLEIRO":       "Sacoleiro",
    "VAREJO":          "Varejo",
    "ATACADO_INATIVO": "Ex-atacado",
    "INATIVO":         "Inativo geral",
    "GERAL_INATIVO":   "Inativo geral",
    "FUNCIONARIO":     "Interno",
    "REPRESENTANTE":   "Interno",
}

ORDEM_TIPOLOGIAS = [
    "Lojista", "Sacoleiro", "Varejo", "Ex-atacado",
    "Inativo geral", "Interno", "Sem classificação",
]

CORES_TIPOLOGIA = {
    "Lojista":           "#1A73E8",
    "Sacoleiro":         "#F9AB00",
    "Varejo":            "#34A853",
    "Ex-atacado":        "#FA7B17",
    "Inativo geral":     "#BDC1C6",
    "Interno":           "#9E9E9E",
    "Sem classificação": "#E0E0E0",
}

CORES_FAIXA = {
    "Até 50 km · Entorno":                "#0D47A1",
    "50–150 km · Bate-volta":             "#1565C0",
    "150–300 km · Viagem curta":          "#1E88E5",
    "300–600 km · Viagem planejada":      "#64B5F6",
    "600–1.200 km · Mercado distante":    "#BBDEFB",
    "1.200+ km · Muito distante":         "#E3F2FD",
    "Sem localização":                    "#E0E0E0",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica em km entre dois pontos."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def circle_points_km(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    n_points: int = 72,
) -> tuple[list[float], list[float]]:
    """Gera coordenadas aproximadas de um círculo em torno de um ponto."""
    if radius_km <= 0:
        return [center_lat], [center_lon]

    lats: list[float] = []
    lons: list[float] = []
    lat_rad = radians(center_lat)
    km_per_deg_lat = 111.32
    km_per_deg_lon = max(111.32 * cos(lat_rad), 0.01)

    for i in range(n_points + 1):
        ang = 2 * pi * i / n_points
        dlat = (radius_km * sin(ang)) / km_per_deg_lat
        dlon = (radius_km * cos(ang)) / km_per_deg_lon
        lats.append(center_lat + dlat)
        lons.append(center_lon + dlon)
    return lats, lons


def normalizar_nome_cidade(nome) -> str | None:
    if nome is None or (isinstance(nome, float) and pd.isna(nome)):
        return None
    nome_str = str(nome).strip()
    if not nome_str:
        return None
    s = unicodedata.normalize("NFKD", nome_str)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split()) or None


# Mapa IBGE codigo_uf → sigla (estável, não muda)
_CODIGO_UF = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


def _baixar_municipios() -> pd.DataFrame:
    """Baixa CSV kelvins/municipios-brasileiros e agrega população IBGE."""
    import requests
    from io import StringIO

    resp = requests.get(_KELVINS_URL, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))

    # O CSV kelvins usa codigo_uf numérico — mapear para sigla
    df = df.rename(columns={
        "nome":        "cidade_orig",
        "latitude":    "lat",
        "longitude":   "lon",
        "codigo_ibge": "ibge_codigo",
    })
    df["uf"] = df["codigo_uf"].map(_CODIGO_UF)
    df["cidade_norm"] = df["cidade_orig"].map(normalizar_nome_cidade)
    df["ibge_codigo"] = df["ibge_codigo"].astype(str).str.zfill(7)

    # Tentar população via IBGE Sidra (gracioso — apenas para seção penetração)
    try:
        pop_resp = requests.get(_IBGE_POP_URL, timeout=60)
        pop_resp.raise_for_status()
        pop_data = pop_resp.json()
        pop_rows = []
        for item in pop_data[0]["resultados"][0]["series"]:
            cod = str(item["localidade"]["id"]).zfill(7)
            serie = item["serie"]
            pop = None
            for ano in sorted(serie.keys(), reverse=True):
                try:
                    pop = int(str(serie[ano]).replace("...", "").strip())
                    break
                except (ValueError, AttributeError, TypeError):
                    continue
            pop_rows.append({"ibge_codigo": cod, "populacao": pop})
        df_pop = pd.DataFrame(pop_rows)
        df = df.merge(df_pop, on="ibge_codigo", how="left")
        df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    except Exception:
        df["populacao"] = None

    cols = ["cidade_norm", "uf", "lat", "lon", "populacao", "cidade_orig", "ibge_codigo"]
    return df[[c for c in cols if c in df.columns]].copy()


@st.cache_data(ttl=30 * 86400, show_spinner=False)
def carregar_municipios_ibge() -> pd.DataFrame:
    """Carrega de parquet local (30 dias de cache) ou baixa e salva."""
    if GEO_CACHE_PATH.exists():
        return pd.read_parquet(GEO_CACHE_PATH)
    df = _baixar_municipios()
    GEO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(GEO_CACHE_PATH, index=False)
    return df


def enriquecer_carteira_geo(df_cart: pd.DataFrame) -> pd.DataFrame:
    """Junta carteira com lat/lon IBGE e calcula distância até a sede."""
    muni = carregar_municipios_ibge()
    out = df_cart.copy()
    out["_cidade_norm"] = out["cidade"].map(normalizar_nome_cidade)
    out = out.merge(
        muni[["cidade_norm", "uf", "lat", "lon", "populacao"]],
        left_on=["_cidade_norm", "uf"],
        right_on=["cidade_norm", "uf"],
        how="left",
    )
    out = out.drop(columns=["cidade_norm", "_cidade_norm"], errors="ignore")
    out["distancia_km"] = out.apply(
        lambda r: haversine_km(float(r["lat"]), float(r["lon"]), SEDE_LAT, SEDE_LON)
        if pd.notna(r.get("lat")) and pd.notna(r.get("lon"))
        else None,
        axis=1,
    )
    out["faixa_distancia"] = out["distancia_km"].map(classificar_faixa)
    out["tipologia"] = out.get("grupo_cadastrado", pd.Series(dtype=object)).map(
        classificar_tipologia
    )
    return out


def classificar_faixa(km) -> str:
    if km is None or (isinstance(km, float) and pd.isna(km)):
        return "Sem localização"
    for lo, hi, label in FAIXAS:
        if lo <= km < hi:
            return label
    return "1.500+ km (Resto do Brasil)"


def classificar_tipologia(grupo) -> str:
    if grupo is None or (isinstance(grupo, float) and pd.isna(grupo)) or str(grupo).strip() == "":
        return "Sem classificação"
    return _MAPA_TIPOLOGIA.get(str(grupo).upper().strip(), "Sem classificação")
