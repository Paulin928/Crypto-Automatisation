"""Signature et envoi de transactions Bitcoin (bitcoinlib)."""

import asyncio
from decimal import Decimal

from bitcoinlib.wallets import Wallet
from bitcoinlib.keys import Key


class BtcSigner:
    """Signe et envoie des transactions natives (BTC) depuis le wallet A.

    Le wallet A possede la cle privee (WIF). Les wallets B ne fournissent
    que leur adresse publique.
    """

    def __init__(
        self,
        wif: str,
        network: str = "testnet",
        fee_rate_sat_vb: int = 2,
        db_uri: str = "sqlite:///data/btc_signer.db",
    ):
        # bitcoinlib attend "bitcoin" ou "testnet"
        self.network = "testnet" if network == "testnet" else "bitcoin"
        self.fee_rate_sat_vb = fee_rate_sat_vb

        # Cle importee en memoire
        self.key = Key(import_key=wif, network=self.network)
        self.address = self.key.address()

        # Wallet bitcoinlib (cree en lazy au premier envoi)
        self._wallet_name = f"btc-signer-{self.address[:8]}"
        self._db_uri = db_uri
        self._wallet = None

    def estimate_fee(self, num_inputs: int = 1, num_outputs: int = 2) -> int:
        """Estimation simple : ~68 vB par input P2WPKH, ~31 vB par output, +11 vB."""
        vbytes = num_inputs * 68 + num_outputs * 31 + 11
        return vbytes * self.fee_rate_sat_vb

    async def send_native(self, to_address: str, amount_sat: int) -> str:
        """Envoie `amount_sat` satoshis a `to_address`. Retourne le txid.

        `amount_sat` est le montant NET recu par le destinataire.
        Les frais sont pris en plus sur le wallet A.
        """
        loop = asyncio.get_running_loop()

        def _blocking() -> str:
            w = self._get_or_create_wallet()
            tx = w.send_to(
                to_address,
                amount_sat,
                fee=self.fee_rate_sat_vb,
                fee_per_kb=False,
                offline=False,
                network=self.network,
            )
            return tx.txid

        return await loop.run_in_executor(None, _blocking)

    def _get_or_create_wallet(self):
        """Cree (ou recharge) le Wallet bitcoinlib lie a notre WIF."""
        if self._wallet is not None:
            return self._wallet

        try:
            self._wallet = Wallet(self._wallet_name, db_uri=self._db_uri)
        except Exception:
            self._wallet = Wallet.create(
                self._wallet_name,
                keys=self.key.wif(),
                network=self.network,
                db_uri=self._db_uri,
                witness_type="segwit",
            )

        return self._wallet
