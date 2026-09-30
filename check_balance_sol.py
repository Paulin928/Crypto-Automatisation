"""Verifie le solde du Wallet A sur Solana Devnet."""
import asyncio
import json
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey


async def main():
    with open('data/wallets_sol.json') as f:
        wallets = json.load(f)
    wallet_a_str = wallets[0]['address']

    # Conversion str -> Pubkey (obligatoire pour solana-py)
    wallet_a = Pubkey.from_string(wallet_a_str)

    async with AsyncClient("https://api.devnet.solana.com") as client:
        resp = await client.get_balance(wallet_a)
        lamports = resp.value
        sol = lamports / 1_000_000_000
        print(f"Wallet A : {wallet_a_str}")
        print(f"Solde    : {sol} SOL ({lamports} lamports)")


if __name__ == "__main__":
    asyncio.run(main())
