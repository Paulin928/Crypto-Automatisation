"""Signature et envoi de transactions Solana (devnet)."""

import asyncio
import json
from decimal import Decimal

from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.message import Message


LAMPORTS_PER_SOL = Decimal("1000000000")


class SolSigner:
    """Signe et envoie des transactions natives (SOL) depuis le wallet A.

    Le wallet A est un keypair Solana complet (adresse publique + cle privee)
    au format array de 64 bytes. Les wallets B ne fournissent que leur adresse
    publique.
    """

    def __init__(
        self,
        private_key_str: str,
        rpc_http_url: str = "https://api.devnet.solana.com",
        fee_lamports_per_tx: int = 5000,
    ):
        # Detection du format de la cle privee :
        #  - "[1,2,3,...]"      -> JSON array de 64 bytes
        #  - "5J...base58..."   -> base58 string
        if isinstance(private_key_str, str) and private_key_str.startswith("["):
            key_bytes = json.loads(private_key_str)
            self.keypair = Keypair.from_bytes(bytes(key_bytes))
        else:
            import base58
            key_bytes = base58.b58decode(private_key_str)
            self.keypair = Keypair.from_bytes(key_bytes)
        self.rpc_http_url = rpc_http_url
        self.fee_lamports_per_tx = fee_lamports_per_tx

    @property
    def address(self) -> str:
        return str(self.keypair.pubkey())

    def estimate_fee(self, num_inputs: int = 1, num_outputs: int = 1) -> int:
        """Frais Solana : ~5000 lamports par signature (fixe)."""
        return self.fee_lamports_per_tx

    async def send_native(self, to_address: str, amount_lamports: int) -> str:
        """Envoie `amount_lamports` a `to_address`. Retourne la signature.

        Utilise VersionedTransaction (methode moderne recommandee par Solana).
        """
        from solders.message import MessageV0
        from solders.transaction import VersionedTransaction

        receiver = Pubkey.from_string(to_address)
        sender = self.keypair.pubkey()

        async with AsyncClient(self.rpc_http_url) as client:
            # Blockhash recent
            blockhash_resp = await client.get_latest_blockhash()
            blockhash = blockhash_resp.value.blockhash

            # Instruction de transfert
            ix = transfer(TransferParams(
                from_pubkey=sender,
                to_pubkey=receiver,
                lamports=amount_lamports,
            ))

            # Message V0 (format moderne)
            msg = MessageV0.try_compile(
                payer=sender,
                instructions=[ix],
                address_lookup_table_accounts=[],
                recent_blockhash=blockhash,
            )

            # VersionedTransaction signee
            tx = VersionedTransaction(msg, [self.keypair])

            # Envoi
            resp = await client.send_transaction(tx)
            return str(resp.value)
