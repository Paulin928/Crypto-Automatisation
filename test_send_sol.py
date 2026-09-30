"""Envoie une petite tx de test au Wallet A (Solana Devnet) pour declencher le watcher."""
import asyncio
import json
import base58

from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.message import Message


async def main():
    with open('data/wallets_sol.json') as f:
        wallets = json.load(f)

    wallet_a = wallets[0]

    # Reconstruire le Keypair depuis la cle privee
    private_bytes = base58.b58decode(wallet_a['private_key'])
    kp = Keypair.from_bytes(private_bytes)

    async with AsyncClient("https://api.devnet.solana.com") as client:
        sender = kp.pubkey()
        receiver = Pubkey.from_string(wallet_a['address'])

        montant_lamports = 1_000_000  # 0.001 SOL

        print(f"Envoi de {montant_lamports / 1e9} SOL")
        print(f"De     : {sender}")
        print(f"Vers   : {receiver}")

        # Recuperer le blockhash recent
        blockhash_resp = await client.get_latest_blockhash()
        blockhash = blockhash_resp.value.blockhash

        # Construire la transaction (avec solders.transaction)
        ix = transfer(TransferParams(
            from_pubkey=sender,
            to_pubkey=receiver,
            lamports=montant_lamports,
        ))
        msg = Message([ix])
        tx = Transaction([kp], msg, blockhash)

        # Signer et envoyer
        resp = await client.send_transaction(tx)
        print(f"\nTransaction envoyee : {resp.value}")
        print("Verifiez le watcher dans l'autre terminal !")


if __name__ == "__main__":
    asyncio.run(main())
