"""Debug : affiche tous les messages WebSocket recus de Solana."""
import asyncio
import json

from solana.rpc.websocket_api import connect
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions


async def main():
    with open('data/wallets_sol.json') as f:
        wallets = json.load(f)
    wallet_a = wallets[0]['address']
    print(f"Wallet surveille : {wallet_a}\n")

    async with connect("wss://api.devnet.solana.com") as ws:
        filter_obj = RpcTransactionLogsFilterMentions(Pubkey.from_string(wallet_a))
        await ws.logs_subscribe(filter_obj, commitment="confirmed")

        # Premier message : ID de souscription
        first = await ws.recv()
        print(f"[DEBUG] Premier message (ID) : {first}\n")

        print("[DEBUG] Ecoute en cours... (Ctrl+C pour arreter)\n")

        count = 0
        async for msg in ws:
            count += 1
            print(f"--- Message #{count} ---")
            print(f"Type : {type(msg)}")
            print(f"Contenu : {msg}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
