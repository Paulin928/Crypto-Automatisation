"""Test du GasEstimator et du EVMSigner sur Sepolia."""
import asyncio
import json
import os
from decimal import Decimal

from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider

from engine.gas import GasEstimator
from engine.signer import EVMSigner


async def main():
    load_dotenv()
    ws_url = os.getenv("INFURA_SEPOLIA_WS")
    priv_key = os.getenv("WALLET_A_PRIVATE_KEY")

    with open('data/wallets.json') as f:
        wallets = json.load(f)

    wallet_a = wallets[0]['address']

    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        gas_est = GasEstimator(w3)
        signer = EVMSigner(w3, priv_key)

        print(f"Wallet A declare   : {wallet_a}")
        print(f"Signer voit        : {signer.address}")
        print(f"Match              : {wallet_a.lower() == signer.address.lower()}")
        print()

        solde = await gas_est.get_balance_eth(signer.address)
        print(f"Solde Wallet A     : {solde} ETH")

        gas = await gas_est.estimate_native_transfer()
        print(f"Cout d'une tx     : {gas} ETH (~21 000 gas)")
        print()

        nb_tx_possibles = int(solde / gas) if gas > 0 else 0
        print(f"Transactions possibles avec ce solde : {nb_tx_possibles}")


if __name__ == "__main__":
    asyncio.run(main())
