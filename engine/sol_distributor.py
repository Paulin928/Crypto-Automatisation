"""Moteur de distribution Solana.

Recoit un event "X SOL recus" et dispatche vers 5 wallets B
selon 48% / 20% / 15% / 10% / reste - frais.

Verrou asyncio pour eviter les doubles envois si plusieurs TX
arrivent a quelques ms d'intervalle.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from engine.sol_signer import SolSigner


LAMPORTS_PER_SOL = Decimal("1000000000")


class SolDistributor:
    """Dispatcher SOL serialise (1 TX entrante = 1 cycle complet)."""

    def __init__(
        self,
        signer: SolSigner,
        wallets_b: list[str],
        ratios_4_first: list[float],
        fee_lamports_per_tx: int = 5000,
        min_lamports: int = 1_000_000,
        dust_limit_lamports: int = 5000,
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
        self.fee_lamports_per_tx = fee_lamports_per_tx
        self.min_lamports = min_lamports
        self.dust_limit_lamports = dust_limit_lamports
        self.dry_run = dry_run

        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[tuple[Decimal, str]] = asyncio.Queue()

    async def handle_incoming(self, montant_sol: Decimal, tx_hash: str):
        """Enfile la TX (non bloquant), un worker unique la traitera."""
        await self._queue.put((montant_sol, tx_hash))
        print(
            f"[SOL-DIST] TX enfilee : {montant_sol} SOL (sig={tx_hash[:16]}...) "
            f"| file={self._queue.qsize()}"
        )

    async def run_worker(self):
        """A lancer en tache de fond : consomme la queue sequentiellement."""
        while True:
            montant_sol, tx_hash = await self._queue.get()
            try:
                async with self._lock:
                    await self._process_one(montant_sol, tx_hash)
            except Exception as e:
                print(f"[SOL-DIST] ERREUR sur sig={tx_hash[:16]}... : {e!r}")
            finally:
                self._queue.task_done()

    async def _process_one(self, montant_sol: Decimal, tx_hash: str):
        recu_lamports = int(montant_sol * LAMPORTS_PER_SOL)

        if recu_lamports < self.min_lamports:
            print(
                f"[SOL-DIST] Montant {recu_lamports} lamports < seuil {self.min_lamports} "
                f"— ignore"
            )
            return

        print(f"\n[SOL-DIST] === Traitement sig={tx_hash[:16]}... ===")
        print(f"[SOL-DIST] Recu : {montant_sol} SOL ({recu_lamports} lamports)")

        # 1) Montants B1..B4
        allocations: list[tuple[str, int]] = []
        total_fixed = 0
        for addr, ratio in zip(self.wallets_b[:4], self.ratios_4_first):
            amt = int(recu_lamports * Decimal(str(ratio)))
            allocations.append((addr, amt))
            total_fixed += amt

        # 2) Frais estimes pour 5 TX
        fee_per_tx = self.signer.estimate_fee()
        total_fees = fee_per_tx * 5

        # 3) Reste pour B5
        reste = recu_lamports - total_fixed - total_fees
        if reste < self.dust_limit_lamports:
            print(
                f"[SOL-DIST] Reste {reste} lamports < dust ({self.dust_limit_lamports}) "
                f"— distribution annulee"
            )
            return

        allocations.append((self.wallets_b[4], reste))

        # 4) Resume
        print(f"[SOL-DIST] Frais estimes : {fee_per_tx} lamports/tx x5 = {total_fees}")
        for i, (addr, amt) in enumerate(allocations, start=1):
            pct = Decimal(amt) / Decimal(recu_lamports) * 100
            print(f"[SOL-DIST]   B{i} -> {addr[:14]}... : {amt} lamports ({pct:.2f}%)")

        if self.dry_run:
            print("[SOL-DIST] DRY_RUN actif — aucun envoi reel")
            return

        # 5) Envois sequentiels B1..B4 puis B5
        for i, (addr, amt) in enumerate(allocations, start=1):
            try:
                sig = await self.signer.send_native(addr, amt)
                print(f"[SOL-DIST]   B{i} envoye : sig={sig[:20]}...")
            except Exception as e:
                print(f"[SOL-DIST]   B{i} ECHEC : {e!r}")
                raise
