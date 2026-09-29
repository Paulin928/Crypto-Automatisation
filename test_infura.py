"""Test de connexion a Infura Sepolia."""
import asyncio
import os
from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider


async def main():
    load_dotenv()
    ws_url = os.getenv("INFURA_SEPOLIA_WS")
    print(f"Connexion a : {ws_url[:50]}...")

    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        connected = await w3.is_connected()
        print(f"Connecte : {connected}")

        if connected:
            chain_id = await w3.eth.chain_id
            block = await w3.eth.block_number
            gas_price = await w3.eth.gas_price
            print(f"Chain ID    : {chain_id}  (attendu : 11155111 pour Sepolia)")
            print(f"Bloc actuel : {block}")
            print(f"Gas price   : {gas_price} wei")


if __name__ == "__main__":
    asyncio.run(main())
