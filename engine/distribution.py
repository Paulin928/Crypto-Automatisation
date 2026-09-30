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
        """Point d'entree quand une tx entrante est detectee."""
        async with self.lock:
            print(f"\n[{self.chain_name}] === Distribution de {montant_recu} ETH ===")

            job_id = await self.repo.create_job(
                chain=self.chain_name,
                tx_hash=tx_hash,
                montant_initial=montant_recu,
            )
            print(f"[{self.chain_name}] Job #{job_id} cree")

            reste = montant_recu
            for i, ratio in enumerate(self.ratios, start=1):
                if i > len(self.wallets_b):
                    print(f"[{self.chain_name}] Pas de wallet B{i}, on s'arrete")
                    break

                montant = (reste * ratio).quantize(PRECISION)
                gas = await self._estimate_gas()
                # Garde-fou : on doit avoir assez pour envoyer + payer le gas
                if reste - montant - gas < 0:
                    montant = max(reste - gas, Decimal("0"))
                    if montant <= 0:
                        print(f"[{self.chain_name}] Etape {i} : plus assez de fonds, skip")
                        await self.repo.mark_step(job_id, i, "SKIPPED", Decimal("0"), reste)
                        continue

                print(f"[{self.chain_name}] Etape {i} : envoi {montant} ETH "
                      f"vers {self.wallets_b[i-1][:10]}... (gas ~{gas})")

                ok = await self._retry_expo(i, montant)
                if ok:
                    reste = reste - montant - gas
                    await self.repo.mark_step(job_id, i, "OK", montant, reste)
                    print(f"[{self.chain_name}] Etape {i} OK, reste = {reste}")
                else:
                    await self.repo.mark_step(job_id, i, "FAILED", montant, reste)
                    print(f"[{self.chain_name}] Etape {i} FAILED apres retries")

            await self.repo.complete_job(job_id, reste)
            print(f"[{self.chain_name}] === Termine. Reste final : {reste} ETH ===\n")

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
