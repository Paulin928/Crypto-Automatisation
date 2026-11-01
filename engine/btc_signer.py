"""Signature et envoi de transactions Bitcoin (bitcoinlib)."""

import asyncio
import aiohttp
from decimal import Decimal

from bitcoinlib.wallets import Wallet
from bitcoinlib.keys import HDKey


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
        witness_type: str = "segwit",
        db_uri: str = "sqlite:///data/btc_signer.db",
    ):
        # bitcoinlib attend "bitcoin" ou "testnet"
        self.network = "testnet" if network == "testnet" else "bitcoin"
        self.fee_rate_sat_vb = fee_rate_sat_vb
        self.witness_type = witness_type

        # Cle importee en memoire
        self.key = HDKey(import_key=wif, network=self.network, witness_type=self.witness_type)
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

        Utilise bitcoinutils (fiable) pour construire et signer la TX.
        """
        from bitcoinutils.setup import setup
        from bitcoinutils.keys import PrivateKey, P2wpkhAddress
        from bitcoinutils.transactions import Transaction, TxInput, TxOutput, TxWitnessInput
        from bitcoinutils.script import Script

        # Setup network
        setup("mainnet" if self.network == "bitcoin" else "testnet")

        # Charger la cle privee
        priv = PrivateKey.from_wif(self.key.wif())
        pub = priv.get_public_key()
        addr_a = pub.get_segwit_address().to_string()

        # 1) Recuperer les UTXOs via Blockstream
        async with aiohttp.ClientSession() as session:
            url = f"https://blockstream.info/api/address/{addr_a}/utxo"
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Blockstream UTXOs HTTP {resp.status}")
                utxos = await resp.json()

        if not utxos:
            raise RuntimeError(f"Aucun UTXO pour {addr_a}")

        print(f"[BtcSigner] {len(utxos)} UTXO(s) recupere(s)")

        # Trier par valeur decroissante
        utxos.sort(key=lambda u: u["value"], reverse=True)

        # 2) Construire la TX avec TOUS les UTXOs disponibles
        amount_in = sum(u["value"] for u in utxos)
        num_inputs = len(utxos)
        num_outputs = 2
        vbytes = num_inputs * 68 + num_outputs * 31 + 11
        fee_sat = vbytes * self.fee_rate_sat_vb

        total_needed = amount_sat + fee_sat
        if amount_in < total_needed:
            raise RuntimeError(
                f"Fonds insuffisants : {amount_in} sat dispo, "
                f"{total_needed} sat requis ({amount_sat} + {fee_sat} frais)"
            )

        change = amount_in - amount_sat - fee_sat

        if change < 546:
            fee_sat = amount_in - amount_sat
            change = 0
            print(f"[BtcSigner] Change < 546 sat, ajoute aux frais")

        print(f"[BtcSigner] {num_inputs} input(s), {amount_in} sat in, {fee_sat} sat frais, {change} sat change")

        # Scripts
        script_pubkey_a = Script(["OP_0", pub.to_hash160()])
        script_code = Script([
            "OP_DUP", "OP_HASH160", pub.to_hash160(),
            "OP_EQUALVERIFY", "OP_CHECKSIG"
        ])

        # Inputs : TOUS les UTXOs
        tx_inputs = [TxInput(u["txid"], u["vout"]) for u in utxos]

        # Outputs
        tx_out_b = TxOutput(amount_sat, P2wpkhAddress(to_address).to_script_pub_key())
        outputs = [tx_out_b]
        if change > 0:
            outputs.append(TxOutput(change, script_pubkey_a))
            print(f"[BtcSigner] Change : {change} sat")

        tx = Transaction(tx_inputs, outputs, has_segwit=True)

        # 3) Signer CHAQUE input
        for i, utxo in enumerate(utxos):
            sig = priv.sign_segwit_input(tx, i, script_code, utxo["value"])
            witness = TxWitnessInput([sig, pub.to_hex()])
            tx.set_witness(i, witness)

        print(f"[BtcSigner] {num_inputs} input(s) signe(s)")

        # 5) Serialiser
        raw_hex = tx.serialize()
        txid_local = tx.get_txid()

        print(f"[BtcSigner] TX signee ({len(raw_hex)} chars), txid local : {txid_local[:20]}...")

        # 6) Broadcast via Blockstream
        broadcast_url = "https://blockstream.info/api/tx"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                broadcast_url,
                data=raw_hex,
                headers={"Content-Type": "text/plain"},
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"Broadcast HTTP {resp.status} : {body[:200]}")
                txid = body.strip()
                print(f"[BtcSigner] Broadcaste OK : {txid[:20]}...")
                return txid

    # (methode _prepare_wallet supprimee, plus necessaire)

    async def _prepare_wallet(self):
        """Charge/creer le wallet bitcoinlib ET injecte les UTXOs de Blockstream."""
        # Creer ou charger le wallet
        if self._wallet is None:
            try:
                self._wallet = Wallet(self._wallet_name, db_uri=self._db_uri)
                print(f"[BtcSigner] Wallet charge : {self._wallet_name}")
            except Exception:
                self._wallet = Wallet.create(
                    self._wallet_name,
                    keys=self.key.wif(),
                    network=self.network,
                    db_uri=self._db_uri,
                    witness_type=self.witness_type,
                )
                print(f"[BtcSigner] Wallet cree : {self._wallet_name}")

        # Recuperer les UTXOs on-chain via Blockstream
        async with aiohttp.ClientSession() as session:
            url = f"https://blockstream.info/api/address/{self.address}/utxo"
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    print(f"[BtcSigner] Blockstream HTTP {resp.status}")
                    return self._wallet
                utxos = await resp.json()

        if not utxos:
            print(f"[BtcSigner] Aucun UTXO on-chain pour {self.address}")
            return self._wallet

        print(f"[BtcSigner] {len(utxos)} UTXO(s) recupere(s) de Blockstream")

        # Supprimer les anciens UTXOs locaux
        try:
            for old_u in self._wallet.utxos():
                old_u.delete()
        except Exception as e:
            print(f"[BtcSigner] Erreur delete UTXOs : {e}")

        # Injecter les nouveaux UTXOs
        try:
            self._wallet.utxos_add([
                {
                    "txid": u["txid"],
                    "output_n": u["vout"],
                    "value": u["value"],
                    "address": self.address,
                    "confirmations": 1,
                    "script": "",
                    "spendable": True,
                }
                for u in utxos
            ])
            bal = self._wallet.balance()
            print(f"[BtcSigner] Solde injecte : {bal} sat")
        except Exception as e:
            print(f"[BtcSigner] Erreur injection UTXOs : {type(e).__name__} : {e}")

        return self._wallet

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
                witness_type=self.witness_type,
            )

        # Scanner les UTXOs on-chain pour synchroniser
        try:
            print(f"[BtcSigner] Scan UTXOs pour {self.address}...")
            self._wallet.scan()
            bal = self._wallet.balance()
            print(f"[BtcSigner] Solde bitcoinlib : {bal} sat")
        except Exception as e:
            print(f"[BtcSigner] Scan erreur : {type(e).__name__} : {e}")

        return self._wallet
