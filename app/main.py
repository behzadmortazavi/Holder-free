from __future__ import annotations
import base64
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
SOLANA_RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

app = FastAPI(title="Token Holder Explorer", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

EVM_CHAINS = {
    "ethereum": "https://eth.blockscout.com", "base": "https://base.blockscout.com",
    "optimism": "https://optimism.blockscout.com", "gnosis": "https://gnosis.blockscout.com",
}

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/health")
def health():
    return {"status": "ok", "evm_provider_configured": True, "provider": "public Blockscout APIs", "solana_rpc_configured": bool(SOLANA_RPC)}

async def solana_rpc(method: str, params: list[Any]) -> Any:
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        response.raise_for_status()
        payload = response.json()
    if payload.get("error"):
        raise HTTPException(502, f"Solana RPC error: {payload['error'].get('message', 'unknown error')}")
    return payload.get("result")

async def get_solana_holders(mint: str, limit: int) -> dict[str, Any]:
    # Solana RPC only exposes the top 20 token accounts with this method.
    largest, supply = await __import__('asyncio').gather(
        solana_rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}]),
        solana_rpc("getTokenSupply", [mint, {"commitment": "confirmed"}]),
    )
    token_accounts = (largest or {}).get("value", [])
    supply_value = (supply or {}).get("value", {})
    decimals = int(supply_value.get("decimals", 0))
    total_supply = Decimal(str(supply_value.get("amount", "0"))) / (Decimal(10) ** decimals)
    addresses = [item["address"] for item in token_accounts if item.get("address")]
    account_result = await solana_rpc("getMultipleAccounts", [addresses, {"encoding": "base64", "commitment": "confirmed"}]) if addresses else {"value": []}
    grouped: dict[str, Decimal] = {}
    for token_acc, raw in zip(token_accounts, (account_result or {}).get("value", [])):
        if not raw or not raw.get("data"):
            continue
        try:
            binary = base64.b64decode(raw["data"][0])
            # SPL Token account layout: mint[0:32], owner[32:64], amount[64:72]
            owner = __import__('base58').b58encode(binary[32:64]).decode() if False else None
            # Avoid an extra dependency: encode 32-byte owner key as base58 below.
            owner = b58encode(binary[32:64])
            raw_amount = int.from_bytes(binary[64:72], "little")
            amount = Decimal(raw_amount) / (Decimal(10) ** decimals)
            grouped[owner] = grouped.get(owner, Decimal(0)) + amount
        except Exception:
            continue
    rows = sorted(grouped.items(), key=lambda x: x[1], reverse=True)[:min(limit, 20)]
    holders = [{"rank": i + 1, "address": owner, "balance": str(amount), "percentage": float(amount / total_supply * 100) if total_supply else None, "explorer_url": f"https://solscan.io/account/{owner}"} for i, (owner, amount) in enumerate(rows)]
    return {"chain": "solana", "address": mint, "total_supply": str(total_supply), "decimals": decimals, "holders": holders, "returned": len(holders), "limit_note": "Solana public RPC returns up to 20 largest token accounts; this is not a complete holder list. Results group those accounts by owner where possible."}

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = ALPHABET[rem] + out
    return "1" * zeros + (out or ("" if zeros else "1"))

async def get_evm_holders(chain: str, address: str, limit: int) -> dict[str, Any]:
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
        raise HTTPException(400, "Enter a valid EVM contract address (0x followed by 40 hex characters).")
    base = EVM_CHAINS[chain]
    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.get(f"{base}/api/v2/tokens/{address}")
        if token_response.status_code == 404:
            raise HTTPException(404, "Token not found on this network, or this Blockscout instance does not index it.")
        if token_response.status_code >= 400:
            raise HTTPException(502, f"Public Blockscout token endpoint returned HTTP {token_response.status_code}.")
        token = token_response.json()
        holders_response = await client.get(f"{base}/api/v2/tokens/{address}/holders", params={"page_size": min(limit, 100)})
        if holders_response.status_code >= 400:
            raise HTTPException(502, f"Public Blockscout holders endpoint returned HTTP {holders_response.status_code}.")
        holder_payload = holders_response.json()
    items = holder_payload.get("items", []) if isinstance(holder_payload, dict) else []
    decimals = int(token.get("decimals") or 0)
    total_supply_raw = token.get("total_supply")
    total_supply = None
    try:
        total_supply = Decimal(str(total_supply_raw)) / (Decimal(10) ** decimals) if total_supply_raw is not None else None
    except Exception:
        total_supply = None
    holders = []
    for item in items[:limit]:
        address_obj = item.get("address") or {}
        owner = address_obj.get("hash") if isinstance(address_obj, dict) else address_obj
        raw_balance = item.get("value") or item.get("balance") or "0"
        try:
            balance = Decimal(str(raw_balance)) / (Decimal(10) ** decimals)
        except Exception:
            balance = Decimal(0)
        if not owner:
            continue
        percentage = float(balance / total_supply * 100) if total_supply else None
        explorer_url = f"{base}/address/{owner}"
        holders.append({"rank": len(holders) + 1, "address": owner, "balance": str(balance), "percentage": percentage, "explorer_url": explorer_url})
    return {"chain": chain, "address": address, "total_supply": str(total_supply) if total_supply is not None else None, "decimals": decimals, "holders": holders, "returned": len(holders), "provider": "Public Blockscout", "limit_note": "Using public Blockscout endpoints without an API key. Coverage and rate limits vary by network; this list is limited to the requested page size and may not represent every holder."}

@app.get("/api/holders")
async def holders(chain: str = Query(...), address: str = Query(..., min_length=20, max_length=100), limit: int = Query(20, ge=1, le=100)):
    chain = chain.lower().strip()
    address = address.strip()
    if chain == "solana":
        if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", address):
            raise HTTPException(400, "Enter a valid Solana token mint address.")
        return await get_solana_holders(address, limit)
    if chain not in EVM_CHAINS:
        raise HTTPException(400, f"Unsupported chain. Choose one of: {', '.join(list(EVM_CHAINS) + ['solana'])}.")
    return await get_evm_holders(chain, address, limit)
