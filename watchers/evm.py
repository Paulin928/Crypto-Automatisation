"""Watcher Ethereum : detecte les receptions sur le Wallet A via les nouveaux blocs."""
import asyncio
import json
import os
from decimal import Decimal

from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider

from watchers.base import ChainWatcher


class EVMWatcher(ChainWatcher):
    """Surveille une adresse Ethereum via WebSocket (nouveaux blocs)."""

    def __init__(
        self,
        rpc_url: str,
        watched_address: str,
        on_incoming_cb,
        repo=None,
        start_block_lookback: int = 100,
    ):
        super().__init__("ethereum", rpc_url, watched_address)
        self.on_incoming_cb = on_incoming_cb
        self.repo = repo
        self.start_block_lookback = start_block_lookback
        self._running = False
        self._seen_tx_hashes = set()
        self._last_block = 0

    async def start(self):
        self._running = True
        retry_delay = 5

        while self._running:
            try:
                print(f"[EVMWatcher] Connexion a {self.rpc_url[:50]}...")
                async with AsyncWeb3(WebSocketProvider(self.rpc_url)) as w3:
                    print(f"[EVMWatcher] Connecte. Surveillance de {self.watched_address}")

                    # Recuperer le bloc actuel
                    current_block = await w3.eth.block_number
                    print(f"[EVMWatcher] Bloc actuel : {current_block}")

                    # Catch-up : scanner les N derniers blocs
                    await self._sync_history(w3, current_block)

                    # Puis surveiller les nouveaux blocs
                    self._last_block = current_block
                    retry_delay = 5

                    # Boucle principale : verifier chaque nouveau bloc
                    while self._running:
                        try:
                            current = await w3.eth.block_number
                        except Exception as e:
                            print(f"[EVMWatcher] Erreur bloc_number : {e}")
                            break

                        if current > self._last_block:
                            for n in range(self._last_block + 1, current + 1):
                                await self._scan_block(w3, n)
                            self._last_block = current

                        await asyncio.sleep(2)

            except Exception as e:
                print(f"[EVMWatcher] Erreur : {e}")
                print(f"[EVMWatcher] Reconnexion dans {retry_delay} s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def stop(self):
        self._running = False

    async def _sync_history(self, w3, current_block: int):
        """Rattrape les TX recentes des N derniers blocs."""
        from_block = max(0, current_block - self.start_block_lookback)
        print(f"[EVMWatcher] Catch-up : blocs {from_block} -> {current_block} ({self.start_block_lookback} blocs)")

        deja_traitees = 0
        a_traiter = 0

        for n in range(from_block, current_block + 1):
            try:
                block = await w3.eth.get_block(n, full_transactions=True)
            except Exception as e:
                print(f"[EVMWatcher] Erreur get_block({n}) : {e}")
                continue

            for tx in block.transactions:
                tx_hash = tx["hash"].hex() if hasattr(tx["hash"], "hex") else str(tx["hash"])
                if tx_hash in self._seen_tx_hashes:
                    continue

                to_addr = tx.get("to")
                if to_addr is None:
                    continue
                if to_addr.lower() != self.watched_address.lower():
                    continue
                if tx.get("value", 0) == 0:
                    continue

                # Verifier la DB
                already = False
                if self.repo is not None:
                    try:
                        already = await self.repo.is_tx_processed("ethereum", tx_hash)
                    except Exception:
                        pass

                if already:
                    self._seen_tx_hashes.add(tx_hash)
                    deja_traitees += 1
                    continue

                # Nouvelle TX a traiter
                a_traiter += 1
                self._seen_tx_hashes.add(tx_hash)
                montant_eth = Decimal(w3.from_wei(tx["value"], "ether"))
                print(f"[EVMWatcher] Catch-up TX : {montant_eth} ETH (tx={tx_hash[:20]}..., bloc={n})")

                try:
                    await self.on_incoming_cb(montant_eth, tx_hash)
                except Exception as e:
                    print(f"[EVMWatcher] Erreur callback : {e}")

        print(f"[EVMWatcher] Catch-up termine : {deja_traitees} deja traitees, {a_traiter} nouvelles")

    async def _scan_block(self, w3: AsyncWeb3, block_number: int):
        """Inspecte toutes les tx d'un bloc et notifie les receptions."""
        try:
            block = await w3.eth.get_block(block_number, full_transactions=True)
        except Exception as e:
            print(f"[EVMWatcher] Erreur get_block({block_number}) : {e}")
            return

        for tx in block.transactions:
            tx_hash = tx["hash"].hex() if hasattr(tx["hash"], "hex") else str(tx["hash"])
            if tx_hash in self._seen_tx_hashes:
                continue
            self._seen_tx_hashes.add(tx_hash)

            to_addr = tx.get("to")
            if to_addr is None:
                continue
            if to_addr.lower() != self.watched_address.lower():
                continue
            if tx.get("value", 0) == 0:
                continue

            # Double check DB
            if self.repo is not None:
                try:
                    if await self.repo.is_tx_processed("ethereum", tx_hash):
                        self._seen_tx_hashes.add(tx_hash)
                        continue
                except Exception as e:
                    print(f"[EVMWatcher] Erreur check DB : {e}")

            montant_eth = Decimal(w3.from_wei(tx["value"], "ether"))
            print(f"\n[EVMWatcher] RECEPTION detectee : {montant_eth} ETH")
            print(f"[EVMWatcher] tx_hash : {tx_hash}")
            print(f"[EVMWatcher] bloc    : {block_number}")
            print(f"[EVMWatcher] from    : {tx.get('from')}")

            try:
                await self.on_incoming_cb(montant_eth, tx_hash)
            except Exception as e:
                print(f"[EVMWatcher] Erreur callback : {e}")

    async def on_incoming(self, tx):
        pass


async def run_watcher_test():
    """Test autonome : ecoute les receptions pendant 600 s."""
    load_dotenv()
    ws_url = os.getenv("INFURA_SEPOLIA_WS")

    with open("data/wallets.json") as f:
        wallets = json.load(f)
    wallet_a = wallets[0]["address"]

    async def on_incoming(montant, tx_hash):
        print(f">>> CALLBACK : {montant} ETH recus, tx={tx_hash}")

    watcher = EVMWatcher(ws_url, wallet_a, on_incoming)
    print(f"[TEST] Ecoute du wallet {wallet_a}")
    print("[TEST] Le watcher tourne 600 s.\n")

    try:
        await asyncio.wait_for(watcher.start(), timeout=600)
    except asyncio.TimeoutError:
        print("\n[TEST] Fin du test (600 s ecoulees).")
        await watcher.stop()


if __name__ == "__main__":
    asyncio.run(run_watcher_test())
