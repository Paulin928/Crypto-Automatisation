"""Verifie le solde du Wallet A sur Sepolia."""
import asyncio
import json
import os
from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider


async def main():
    load_dotenv()
    ws_url = os.getenv("INFURA_SEPOLIA_WS")

    with open('data/wallets.json') as f:
        wallets = json.load(f)
    wallet_a = wallets[0]['address']

    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        balance_wei = await w3.eth.get_balance(wallet_a)
        balance_eth = w3.from_wei(balance_wei, 'ether')
        print(f"Wallet A : {wallet_a}")
        print(f"Solde    : {balance_eth} ETH")


if __name__ == "__main__":
    asyncio.run(main())
