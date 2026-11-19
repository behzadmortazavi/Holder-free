# Token Holder Explorer (MVP)

A small real-data starter for ranking token holders on EVM chains and Solana.

## What works
- Responsive web UI served by FastAPI.
- Solana SPL: calls Solana JSON-RPC `getTokenLargestAccounts` and `getTokenSupply`, then resolves token-account owners via `getMultipleAccounts`.
- EVM: uses public Blockscout APIs ERC-20 token owners endpoint; provider support depends on the selected chain and the public Blockscout APIs account plan.
- API keys are read server-side from environment variables.
- Explicitly labels Solana results as the largest token accounts returned by RPC; token accounts are grouped by owner to reduce duplicate owner rows.

## Important limits
- This is an MVP, not yet a production-grade indexer. Solana's standard `getTokenLargestAccounts` returns only up to 20 largest token accounts; it cannot promise every holder or a full top 100.
- EVM holder endpoint response shapes and supported chains may change; verify against your public Blockscout APIs dashboard/docs. No API key means EVM requests return a clear configuration error.
- Token lookup currently requires the contract/mint address and network. Symbol/name search should be added with a token discovery/indexing provider to avoid ambiguous tickers.
- Results are on-chain addresses, not verified real-world identities. Exchange, burn, bridge and contract wallets need separate labels.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Set  for EVM support. SOLANA_RPC_URL has a public default.
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Environment variables
- ``: required for EVM holder queries.
- `SOLANA_RPC_URL`: optional; defaults to Solana mainnet-beta public RPC (rate limits apply).
- `MORALIS_BASE_URL`: optional; defaults to `https://deep-index.moralis.io/api/v2.2`.

## API
`GET /api/holders?chain=ethereum&address=0x...&limit=20`
`GET /api/holders?chain=solana&address=<mint>&limit=20`
`GET /health`

## Next steps before public launch
1. Add a token discovery/search provider and token metadata endpoint.
2. Add pagination/indexing for complete holder sets, not just top accounts.
3. Add PostgreSQL + Redis caching, rate limiting, abuse protection, monitoring and API usage budgets.
4. Add automated tests against known tokens on each supported network.
5. Add wallet labels and holder history snapshots only after their data source is selected.


This free starter uses public Blockscout API instances for Ethereum, Base, Optimism and Gnosis, and public Solana RPC. Public endpoints may rate-limit requests or have incomplete coverage. No paid API key is required.
