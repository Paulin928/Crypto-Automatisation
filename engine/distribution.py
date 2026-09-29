"""Moteur de distribution : recoit un evenement, envoie vers les wallets B."""
import asyncio
from decimal import Decimal

PRECISION = Decimal("0.00000001")


class DistributionEngine:
    def __init__(self, chain_name, config, ratios, retry_cfg, repo):
        self.chain_name = chain_name
        self.config = config
        self.ratios = [Decimal(str(r)) for r in ratios]
        self.retry_cfg = retry_cfg
        self.repo = repo
        self.lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def run(self):
        print(f"[{self.chain_name}] watcher demarre")
        await self._stop.wait()

    async def wait(self):
        await self._stop.wait()

    async def handle_incoming(self, montant_recu: Decimal, tx_hash: str):
        async with self.lock:
            job_id = await self.repo.create_job(
                chain=self.chain_name,
                tx_hash=tx_hash,
                montant_initial=montant_recu,
            )
            reste = montant_recu
            for i, ratio in enumerate(self.ratios, start=1):
                montant = (reste * ratio).quantize(PRECISION)
                gas = await self._estimate_gas(montant)
                if reste - montant - gas < 0:
                    montant = max(reste - gas, Decimal("0"))
                ok = await self._retry_expo(i, montant)
                if ok:
                    reste = reste - montant - gas
                    await self.repo.mark_step(job_id, i, "OK", montant, reste)
                else:
                    await self.repo.mark_step(job_id, i, "FAILED", montant, reste)
            await self.repo.complete_job(job_id, reste)

    async def _estimate_gas(self, montant: Decimal) -> Decimal:
        return Decimal("0.0008")

    async def _send(self, index: int, montant: Decimal) -> bool:
        print(f"[{self.chain_name}] envoi {montant} vers B{index}")
        return True

    async def _retry_expo(self, index: int, montant: Decimal) -> bool:
        delay = self.retry_cfg["initial_delay"]
        for attempt in range(self.retry_cfg["max_tries"]):
            try:
                return await self._send(index, montant)
            except Exception as e:
                print(f"[{self.chain_name}] tentative {attempt+1} echouee : {e}")
                await asyncio.sleep(delay)
                delay *= self.retry_cfg["multiplier"]
        return False
