"""Point d'entree du robot Multi-Chain Auto Distributor."""
import asyncio
import yaml
from dotenv import load_dotenv

from engine.distribution import DistributionEngine
from storage.repository import JobRepository


async def main():
    load_dotenv()
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    repo = JobRepository(config["database"]["path"])
    await repo.init()

    engines = []
    for chain_name, chain_cfg in config["chains"].items():
        if not chain_cfg.get("enabled"):
            continue
        engine = DistributionEngine(
            chain_name=chain_name,
            config=chain_cfg,
            ratios=config["distribution"]["ratios"],
            retry_cfg=config["retry"],
            repo=repo,
        )
        engines.append(engine)
        asyncio.create_task(engine.run())

    print(f"[MCAD] {len(engines)} chaine(s) demarree(s).")
    await asyncio.gather(*[e.wait() for e in engines])


if __name__ == "__main__":
    asyncio.run(main())
