"""Moteur de distribution BTC.

Recoit un event "X BTC recus" et dispatche vers 5 wallets B
selon 48% / 20% / 15% / 10% / reste - frais.

Verrou asyncio pour eviter les doubles envois si plusieurs TX
arrivent a quelques ms d'intervalle.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from engine.btc_signer import BtcSigner


SATS_PER_BTC = Decimal("100000000")


class BtcDistributor:
    """Dispatcher BTC serialise (1 TX entrante = 1 cycle complet)."""

    def __init__(
        self,
        signer: BtcSigner,
        wallets_b: list[str],
        ratios_4_first: list[float],
        fee_rate_sat_vb: int = 2,
        min_satoshis: int = 10000,
        dust_limit: int = 546,
        dry_run: bool = True,
    ):
        if len(wallets_b) != 5:
            raise ValueError("Il faut exactement 5 wallets B")
        if len(ratios_4_first) != 4:
            raise ValueError("Il faut exactement 4 ratios (B5 = reste)")
        if abs(sum(ratios_4_first) - 0.93) > 1e-9:
            raise ValueError(
                f"La somme des 4 premiers ratios doit valoir 0.93, "
                f"recu {sum(ratios_4_first)}"
            )

        self.signer = signer
        self.wallets_b = wallets_b
        self.ratios_4_first = ratios_4_first
        self.fee_rate_sat_vb = fee_rate_sat_vb
        self.min_satoshis = min_satoshis
        self.dust_limit = dust_limit
        self.dry_run = dry_run

        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[tuple[Decimal, str]] = asyncio.Queue()

    async def handle_incoming(self, montant_btc: Decimal, tx_hash: str):
        """Enfile la TX (non bloquant), un worker unique la traitera."""
        await self._queue.put((montant_btc, tx_hash))
        print(
            f"[BTC-DIST] TX enfilee : {montant_btc} BTC (txid={tx_hash[:16]}...) "
            f"| file={self._queue.qsize()}"
        )

    async def run_worker(self):
        """A lancer en tache de fond : consomme la queue sequentiellement."""
        while True:
            montant_btc, tx_hash = await self._queue.get()
            try:
                async with self._lock:
                    await self._process_one(montant_btc, tx_hash)
            except Exception as e:
                print(f"[BTC-DIST] ERREUR sur txid={tx_hash[:16]}... : {e!r}")
            finally:
                self._queue.task_done()

    async def _process_one(self, montant_btc: Decimal, tx_hash: str):
        recu_sat = int(montant_btc * SATS_PER_BTC)

        if recu_sat < self.min_satoshis:
            print(
                f"[BTC-DIST] Montant {recu_sat} sat < seuil {self.min_satoshis} "
                f"— ignore"
            )
            return

        print(f"\n[BTC-DIST] === Traitement txid={tx_hash[:16]}... ===")
        print(f"[BTC-DIST] Recu : {montant_btc} BTC ({recu_sat} sat)")

        # 1) Montants B1..B4
        allocations: list[tuple[str, int]] = []
        total_fixed = 0
        for addr, ratio in zip(self.wallets_b[:4], self.ratios_4_first):
            amt = int(recu_sat * Decimal(str(ratio)))
            allocations.append((addr, amt))
            total_fixed += amt

        # 2) Frais estimes pour 5 TX
        fee_per_tx = self.signer.estimate_fee(num_inputs=1, num_outputs=2)
        total_fees = fee_per_tx * 5

        # 3) Reste pour B5
        reste = recu_sat - total_fixed - total_fees
        if reste < self.dust_limit:
            print(
                f"[BTC-DIST] Reste {reste} sat < dust ({self.dust_limit}) — "
                f"distribution annulee"
            )
            return

        allocations.append((self.wallets_b[4], reste))

        # 4) Resume
        print(f"[BTC-DIST] Frais estimes : {fee_per_tx} sat/tx x5 = {total_fees} sat")
        for i, (addr, amt) in enumerate(allocations, start=1):
            pct = Decimal(amt) / Decimal(recu_sat) * 100
            print(f"[BTC-DIST]   B{i} -> {addr[:14]}... : {amt} sat ({pct:.2f}%)")

        if self.dry_run:
            print("[BTC-DIST] DRY_RUN actif — aucun envoi reel")
            return

        # 5) Envois sequentiels B1..B4 puis B5
        for i, (addr, amt) in enumerate(allocations, start=1):
            try:
                txid = await self.signer.send_native(addr, amt)
                print(f"[BTC-DIST]   B{i} envoye : txid={txid[:16]}...")
            except Exception as e:
                print(f"[BTC-DIST]   B{i} ECHEC : {e!r}")
                raise
