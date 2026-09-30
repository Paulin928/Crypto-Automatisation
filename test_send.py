"""Envoie une petite tx de test au Wallet A pour declencher le watcher."""
import asyncio
import json
import os
from decimal import Decimal

from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider
from eth_account import Account


async def main():
    load_dotenv()
    ws_url = os.getenv("INFURA_SEPOLIA_WS")
    priv_key = os.getenv("WALLET_A_PRIVATE_KEY")

    with open("data/wallets.json") as f:
        wallets = json.load(f)

    wallet_a = wallets[0]["address"]

    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        acct = Account.from_key(priv_key)
        nonce = await w3.eth.get_transaction_count(acct.address, "pending")
        gas_price = await w3.eth.gas_price

        montant = Decimal("0.0005")  # 0.0005 ETH

        tx = {
            "nonce": nonce,
            "to": wallet_a,
            "value": w3.to_wei(montant, "ether"),
            "gas": 21_000,
            "gasPrice": gas_price,
            "chainId": await w3.eth.chain_id,
        }

        signed = acct.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)

        print(f"Transaction envoyee : {tx_hash.hex()}")
        print(f"De     : {acct.address}")
        print(f"Vers   : {wallet_a}")
        print(f"Montant : {montant} ETH")


if __name__ == "__main__":
    asyncio.run(main())
