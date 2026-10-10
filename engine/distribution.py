"""Moteur de distribution : recoit un evenement, envoie vers les wallets B."""
import asyncio
from decimal import Decimal

from engine.gas import GasEstimator
from engine.signer import EVMSigner

PRECISION = Decimal("0.00000001")


class DistributionEngine:
    def __init__(self, chain_name, config, ratios, retry_cfg, repo,
                 signer: EVMSigner = None, gas_estimator: GasEstimator = None):
        self.chain_name = chain_name
        self.config = config
        self.ratios = [Decimal(str(r)) for r in ratios]
        self.retry_cfg = retry_cfg
        self.repo = repo
        self.signer = signer
        self.gas_estimator = gas_estimator
        self.wallets_b = config.get("wallets_b", [])
        self.lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def run(self):
        print(f"[{self.chain_name}] moteur demarre")
        await self._stop.wait()

    async def wait(self):
        await self._stop.wait()

    async def handle_incoming(self, montant_recu: Decimal, tx_hash: str):
        """Point d'entree quand une tx entrante est detectee.

        Logique 4+1 :
        - B1..B4 recoivent un pourcentage FIXE du montant recu.
        - B5 recoit : montant_recu - somme(B1..B4) - 5 * gas_unitaire.
        """
        async with self.lock:
            print(f"\n[{self.chain_name}] === Distribution de {montant_recu} ETH ===")

            job_id = await self.repo.create_job(
                chain=self.chain_name,
                tx_hash=tx_hash,
                montant_initial=montant_recu,
            )
            print(f"[{self.chain_name}] Job #{job_id} cree")

            if len(self.wallets_b) != 5:
                print(f"[{self.chain_name}] Il faut 5 wallets B (recu {len(self.wallets_b)}), abandon")
                await self.repo.complete_job(job_id, montant_recu)
                return

            if len(self.ratios) != 4:
                print(f"[{self.chain_name}] Il faut 4 ratios (recu {len(self.ratios)}), abandon")
                await self.repo.complete_job(job_id, montant_recu)
                return

            # 1) Gas unitaire + gas total (5 envois)
            gas_unit = await self._estimate_gas()
            total_fees = gas_unit * 5

            # 2) Montants B1..B4 = ratio * montant_recu
            allocations = []
            total_fixed = Decimal("0")
            for ratio, dest in zip(self.ratios, self.wallets_b[:4]):
                amt = (montant_recu * ratio).quantize(PRECISION)
                allocations.append((dest, amt))
                total_fixed += amt

            # 3) Montant B5 = reste - frais
            reste_b5 = (montant_recu - total_fixed - total_fees).quantize(PRECISION)

            # Seuil de dust ETH : on exige au moins gas_unit pour pouvoir envoyer
            if reste_b5 < gas_unit:
                print(f"[{self.chain_name}] B5 = {reste_b5} ETH < gas_unit {gas_unit} -> distribution annulee")
                await self.repo.complete_job(job_id, montant_recu)
                return

            allocations.append((self.wallets_b[4], reste_b5))

            # 4) Recap
            print(f"[{self.chain_name}] Gas unitaire ~{gas_unit} ETH, total (x5) = {total_fees} ETH")
            for i, (dest, amt) in enumerate(allocations, start=1):
                pct = (amt / montant_recu * 100).quantize(Decimal("0.01"))
                print(f"[{self.chain_name}]   B{i} -> {dest[:10]}... : {amt} ETH ({pct}%)")

            # 5) Envois sequentiels B1..B4 puis B5
            for i, (dest, amt) in enumerate(allocations, start=1):
                print(f"[{self.chain_name}] Etape {i} : envoi {amt} ETH vers {dest[:10]}...")
                ok = await self._retry_expo(i, amt)
                if ok:
                    await self.repo.mark_step(job_id, i, "OK", amt, montant_recu)
                    print(f"[{self.chain_name}] Etape {i} OK")
                else:
                    await self.repo.mark_step(job_id, i, "FAILED", amt, montant_recu)
                    print(f"[{self.chain_name}] Etape {i} FAILED apres retries")

            await self.repo.complete_job(job_id, Decimal("0"))
            print(f"[{self.chain_name}] === Termine ===\n")

    async def _estimate_gas(self) -> Decimal:
        """Estime le cout d'une tx en ETH."""
        if self.gas_estimator is None:
            return Decimal("0.0008")  # placeholder
        return await self.gas_estimator.estimate_native_transfer()

    async def _send(self, index: int, montant: Decimal) -> bool:
        """Signe et envoie la tx vers le wallet B[index-1]."""
        if self.signer is None:
            print(f"[{self.chain_name}] Pas de signer, envoi simule (index={index})")
            return True

        destinataire = self.wallets_b[index - 1]
        try:
            tx_hash = await self.signer.send_native(destinataire, montant)
            print(f"[{self.chain_name}] -> tx envoyee : {tx_hash}")
            return True
        except Exception as e:
            print(f"[{self.chain_name}] -> erreur envoi : {e}")
            raise

    async def _retry_expo(self, index: int, montant: Decimal) -> bool:
        """Retry exponentiel : 5s, 10s, 20s, 40s..."""
        delay = self.retry_cfg["initial_delay"]
        for attempt in range(self.retry_cfg["max_tries"]):
            try:
                return await self._send(index, montant)
            except Exception as e:
                print(f"[{self.chain_name}] tentative {attempt+1} echouee : {e}")
                if attempt < self.retry_cfg["max_tries"] - 1:
                    await asyncio.sleep(delay)
                    delay *= self.retry_cfg["multiplier"]
        return False
