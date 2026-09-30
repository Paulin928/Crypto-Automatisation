"""Test du watcher Solana."""
import asyncio
import json

from watchers.sol import SolWatcher

WS_URL = "wss://api.devnet.solana.com"
HTTP_URL = "https://api.devnet.solana.com"


async def main():
    with open("data/wallets_sol.json") as f:
        wallets = json.load(f)
    wallet_a = wallets[0]["address"]

    async def on_incoming(montant, signature):
        print(f"\n>>> CALLBACK : {montant} SOL recus")
        print(f">>> SIGNATURE : {signature}\n")

    watcher = SolWatcher(WS_URL, HTTP_URL, wallet_a, on_incoming)

    print(f"[TEST] Ecoute du wallet {wallet_a}")
    print("[TEST] Le watcher tourne 300 s.\n")

    try:
        await asyncio.wait_for(watcher.start(), timeout=300)
    except asyncio.TimeoutError:
        print("\n[TEST] Fin (300 s).")
        await watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
