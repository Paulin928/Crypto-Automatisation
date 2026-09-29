"""Test de la logique de distribution en local (sans blockchain)."""
import asyncio
from decimal import Decimal

from engine.distribution import DistributionEngine
from storage.repository import JobRepository


async def main():
    # 1. Initialiser la base SQLite
    repo = JobRepository("data/test.db")
    await repo.init()

    # 2. Creer un moteur simule
    ratios = [0.48, 0.20, 0.15, 0.10, 0.07]
    retry_cfg = {"initial_delay": 1, "multiplier": 2, "max_tries": 3}

    engine = DistributionEngine(
        chain_name="simulation",
        config={},
        ratios=ratios,
        retry_cfg=retry_cfg,
        repo=repo,
    )

    # 3. Simuler une reception de 1.0 ETH
    montant = Decimal("1.0")
    print(f"\n=== Reception de {montant} ETH ===\n")
    await engine.handle_incoming(montant, tx_hash="simu_tx_001")

    # 4. Afficher le resultat
    print("\n=== Distribution terminee ===\n")


if __name__ == "__main__":
    asyncio.run(main())
