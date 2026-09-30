"""Point d'entree du robot Multi-Chain Auto Distributor."""
import asyncio
import json
import os
import yaml
from decimal import Decimal

from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider

from engine.distribution import DistributionEngine
from engine.gas import GasEstimator
from engine.signer import EVMSigner
from storage.repository import JobRepository
from watchers.evm import EVMWatcher


async def main():
    load_dotenv()
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # Base de donnees
    repo = JobRepository(config["database"]["path"])
    await repo.init()

    # Connexion blockchain
    ws_url = os.getenv("INFURA_SEPOLIA_WS")
    priv_key = os.getenv("WALLET_A_PRIVATE_KEY")

    if not ws_url or not priv_key:
        raise RuntimeError("INFURA_SEPOLIA_WS ou WALLET_A_PRIVATE_KEY manquant dans .env")

    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        # Instancier le signer et le gas estimator une fois
        signer = EVMSigner(w3, priv_key)
        gas_estimator = GasEstimator(w3)

        print(f"[MCAD] Signer : {signer.address}")
        solde = await gas_estimator.get_balance_eth(signer.address)
        gas_unit = await gas_estimator.estimate_native_transfer()
        print(f"[MCAD] Solde Wallet A : {solde} ETH")
        print(f"[MCAD] Cout d'une tx : {gas_unit} ETH")
        print()

        # Creer le moteur pour chaque chaine active
        engines = {}
        for chain_name, chain_cfg in config["chains"].items():
            if not chain_cfg.get("enabled"):
                continue
            engine = DistributionEngine(
                chain_name=chain_name,
                config=chain_cfg,
                ratios=config["distribution"]["ratios"],
                retry_cfg=config["retry"],
                repo=repo,
                signer=signer,
                gas_estimator=gas_estimator,
            )
            engines[chain_name] = engine

        # Creer le watcher qui va appeler le moteur
        eth_engine = engines.get("ethereum")
        if eth_engine is None:
            print("[MCAD] Aucune chaine Ethereum activee. Arret.")
            return

        wallet_a = signer.address

        async def on_incoming(montant: Decimal, tx_hash: str):
            print(f"\n[MCAD] Reception detectee : {montant} ETH (tx={tx_hash[:16]}...)")
            await eth_engine.handle_incoming(montant, tx_hash)

        watcher = EVMWatcher(ws_url, wallet_a, on_incoming)

        print(f"[MCAD] Surveillance active sur {wallet_a}")
        print(f"[MCAD] En attente de transactions entrantes...\n")

        # Lancer le watcher indefiniment
        try:
            await watcher.start()
        except KeyboardInterrupt:
            print("\n[MCAD] Arret demande.")
            await watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
