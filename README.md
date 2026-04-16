# Camboriú · Dashboard de Carteira

Dashboard Streamlit para análise da carteira de clientes Camboriú.
Conecta ao Supabase PostgreSQL (star schema: `dim_clientes`, `fato_vendas`, `fato_itens_venda`).

## Painéis

- **Visão Executiva** — KPIs, status da carteira, faturamento por segmento
- **Recorrência** — coortes, reativação, frequência
- **Sazonalidade** — índice mensal, heatmap ano × mês
- **Operacional** — forma de pagamento, cidades (PE), segmentos
- **Vendedores** — ranking, evolução mensal, ticket médio

## Deploy local

```bash
pip install -r requirements.txt
streamlit run app.py
```

Crie `.streamlit/secrets.toml`:

```toml
DB_URL = "postgresql://..."
SENHA  = "sua-senha"
```

## Deploy em produção

[Streamlit Community Cloud](https://share.streamlit.io) — gratuito, com gerenciamento de secrets nativo.
