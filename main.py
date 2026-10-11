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
from watchers.btc import BtcWatcher
from watchers.btc_cli import BtcWatcherCli
from engine.btc_signer import BtcSigner
from engine.btc_signer_cli import BtcSignerCli
from engine.btc_distributor import BtcDistributor
from watchers.sol import SolWatcher
from engine.sol_signer import SolSigner
from engine.sol_distributor import SolDistributor


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

        # ============ BITCOIN ============
        btc_cfg = config["chains"].get("bitcoin")
        btc_tasks = []
        btc_watcher = None
        if btc_cfg and btc_cfg.get("enabled"):
            btc_network = btc_cfg["network"]
            btc_watcher_addr = btc_cfg["wallet_a_address"]

            if btc_network == "regtest":
                # --- Mode regtest : via Bitcoin Core CLI ---
                btc_signer = BtcSignerCli(
                    rpc_url=btc_cfg.get("rpc_url", "http://127.0.0.1:18443"),
                    rpc_user=btc_cfg.get("rpc_user", "btc"),
                    rpc_password=btc_cfg.get("rpc_password", "btcpass"),
                    wallet_name=btc_cfg.get("rpc_wallet", "faucet"),
                    fee_rate_sat_vb=btc_cfg["fee_rate_sat_vb"],
                )
                print(f"[MCAD] Signer BTC (CLI) : {btc_signer.wallet_name}")

                btc_distributor = BtcDistributor(
                    signer=btc_signer,
                    wallets_b=btc_cfg["wallets_b"],
                    ratios_4_first=config["distribution"]["ratios"][:4],
                    fee_rate_sat_vb=btc_cfg["fee_rate_sat_vb"],
                    min_satoshis=btc_cfg["min_satoshis_to_distribute"],
                    dust_limit=btc_cfg["dust_limit"],
                    dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
                )

                btc_watcher = BtcWatcherCli(
                    watched_address=btc_watcher_addr,
                    on_incoming=btc_distributor.handle_incoming,
                    rpc_url=btc_cfg.get("rpc_url", "http://127.0.0.1:18443"),
                    rpc_user=btc_cfg.get("rpc_user", "btc"),
                    rpc_password=btc_cfg.get("rpc_password", "btcpass"),
                    wallet_name=btc_cfg.get("rpc_wallet", "faucet"),
                    poll_interval=3,
                    confirmations_required=btc_cfg["confirmations_required"],
                )
            else:
                # --- Mode testnet / mainnet : via bitcoinlib + WIF ---
                btc_wif = os.getenv(btc_cfg["wallet_a_wif_env"])
                if not btc_wif:
                    raise RuntimeError(
                        f"Variable d'env {btc_cfg['wallet_a_wif_env']} manquante"
                    )

                btc_signer = BtcSigner(
                    btc_wif,
                    network=btc_network,
                    fee_rate_sat_vb=btc_cfg["fee_rate_sat_vb"],
                )
                print(f"[MCAD] Signer BTC (lib) : {btc_signer.address}")

                btc_distributor = BtcDistributor(
                    signer=btc_signer,
                    wallets_b=btc_cfg["wallets_b"],
                    ratios_4_first=config["distribution"]["ratios"][:4],
                    fee_rate_sat_vb=btc_cfg["fee_rate_sat_vb"],
                    min_satoshis=btc_cfg["min_satoshis_to_distribute"],
                    dust_limit=btc_cfg["dust_limit"],
                    dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
                )

                btc_watcher = BtcWatcher(
                    api_base=btc_cfg["api_base"],
                    watched_address=btc_watcher_addr,
                    on_incoming=btc_distributor.handle_incoming,
                    poll_interval=10,
                    confirmations_required=btc_cfg["confirmations_required"],
                )

            btc_tasks.append(asyncio.create_task(btc_distributor.run_worker()))
            btc_tasks.append(asyncio.create_task(btc_watcher.start()))
            print(f"[MCAD] Surveillance BTC active sur {btc_cfg['wallet_a_address']}")
            print(f"[MCAD] DRY_RUN BTC : {os.getenv('DRY_RUN', 'true')}")

        # ============ SOLANA ============
        sol_cfg = config["chains"].get("solana")
        sol_tasks = []
        sol_watcher = None
        if sol_cfg and sol_cfg.get("enabled"):
            import json as _json
            with open("data/wallets_sol.json") as _f:
                _sol_wallets = _json.load(_f)
            _sol_pk = _sol_wallets[0].get("private_key_b58") or _sol_wallets[0].get("private_key")

            sol_signer = SolSigner(
                private_key_str=_sol_pk,
                rpc_http_url=sol_cfg["rpc_http_url"],
                fee_lamports_per_tx=sol_cfg["fee_lamports_per_tx"],
            )
            print(f"[MCAD] Signer SOL : {sol_signer.address}")

            sol_distributor = SolDistributor(
                signer=sol_signer,
                wallets_b=sol_cfg["wallets_b"],
                ratios_4_first=config["distribution"]["ratios"][:4],
                fee_lamports_per_tx=sol_cfg["fee_lamports_per_tx"],
                min_lamports=sol_cfg["min_lamports_to_distribute"],
                dust_limit_lamports=sol_cfg["dust_limit_lamports"],
                dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
            )

            sol_watcher = SolWatcher(
                rpc_ws_url=sol_cfg["rpc_ws_url"],
                rpc_http_url=sol_cfg["rpc_http_url"],
                watched_address=sol_cfg["wallet_a_address"],
                on_incoming_cb=sol_distributor.handle_incoming,
            )

            sol_tasks.append(asyncio.create_task(sol_distributor.run_worker()))
            sol_tasks.append(asyncio.create_task(sol_watcher.start()))
            print(f"[MCAD] Surveillance SOL active sur {sol_cfg['wallet_a_address']}")
            print(f"[MCAD] DRY_RUN SOL : {os.getenv('DRY_RUN', 'true')}")

        print(f"[MCAD] Surveillance active sur {wallet_a}")
        print(f"[MCAD] En attente de transactions entrantes...\n")

        # Lancer le watcher indefiniment
        try:
            await watcher.start()
        except KeyboardInterrupt:
            print("\n[MCAD] Arret demande.")
            await watcher.stop()
            if btc_watcher is not None:
                await btc_watcher.stop()
            if sol_watcher is not None:
                await sol_watcher.stop()
            for t in btc_tasks + sol_tasks:
                t.cancel()
            if btc_tasks or sol_tasks:
                await asyncio.gather(*(btc_tasks + sol_tasks), return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
