"""Watcher Solana : detecte les receptions sur le Wallet A via logsSubscribe."""
import asyncio
from decimal import Decimal

from solana.rpc.websocket_api import connect
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.rpc.config import RpcTransactionLogsFilterMentions

from watchers.base import ChainWatcher


class SolWatcher(ChainWatcher):
    """Surveille une adresse Solana via logsSubscribe."""

    def __init__(self, rpc_ws_url: str, rpc_http_url: str, watched_address: str, on_incoming_cb, repo=None):
        super().__init__("solana", rpc_ws_url, watched_address)
        self.rpc_ws_url = rpc_ws_url
        self.rpc_http_url = rpc_http_url
        self.on_incoming_cb = on_incoming_cb
        self._running = False
        self._seen_signatures = set()
        self.repo = repo  # JobRepository pour eviter les doublons

    async def start(self):
        self._running = True
        retry_delay = 5

        # Catch-up : rattraper les TX manquees avant l'ecoute live
        await self._sync_history()

        while self._running:
            try:
                print(f"[SolWatcher] Connexion a {self.rpc_ws_url[:50]}...")
                async with connect(self.rpc_ws_url) as websocket:
                    filter_obj = RpcTransactionLogsFilterMentions(
                        Pubkey.from_string(self.watched_address)
                    )
                    await websocket.logs_subscribe(filter_obj, commitment="confirmed")

                    # Premier message = ID de souscription
                    first_resp = await websocket.recv()
                    sub_id = first_resp[0].result
                    print(f"[SolWatcher] Connecte. Abonnement #{sub_id}")
                    print(f"[SolWatcher] Ecoute de {self.watched_address}")
                    retry_delay = 5

                    # Boucle principale
                    async for msg in websocket:
                        if not self._running:
                            break
                        await self._handle_message(msg)

            except Exception as e:
                print(f"[SolWatcher] Erreur : {e}")
                print(f"[SolWatcher] Reconnexion dans {retry_delay} s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def stop(self):
        self._running = False

    async def _sync_history(self):
        """Rattrape les TX recentes non encore traitees (catch-up)."""
        print(f"[SolWatcher] Sync historique pour {self.watched_address}...")
        try:
            async with AsyncClient(self.rpc_http_url) as client:
                sigs = await client.get_signatures_for_address(
                    Pubkey.from_string(self.watched_address),
                    limit=3,
                )
                if not sigs.value:
                    print("[SolWatcher] Aucune TX historique")
                    return

                print(f"[SolWatcher] {len(sigs.value)} TX historiques a verifier")

                for s in sigs.value:
                    sig_str = str(s.signature)
                    if sig_str in self._seen_signatures:
                        continue
                    if s.err is not None:
                        continue

                    # Verifier si deja traitee en DB
                    if self.repo is not None:
                        try:
                            if await self.repo.is_tx_processed("solana", sig_str):
                                self._seen_signatures.add(sig_str)
                                print(f"[SolWatcher] Sync TX deja traitee : {sig_str[:20]}...")
                                continue
                        except Exception as e:
                            print(f"[SolWatcher] Erreur check DB : {e}")

                    self._seen_signatures.add(sig_str)
                    print(f"[SolWatcher] Sync TX : {sig_str[:20]}...")

                    # Version SANS retry (rapide pour la sync)
                    montant = await self._get_amount_fast(client, sig_str)
                    if montant is None or montant == 0:
                        continue

                    print(f"[SolWatcher] Sync MONTANT RECU : {montant} SOL")
                    await self.on_incoming_cb(montant, sig_str)
        except Exception as e:
            print(f"[SolWatcher] Erreur sync : {type(e).__name__} : {e}")

    async def _get_amount_fast(self, client, sig_str):
        """Version rapide de _get_received_amount, sans retry."""
        try:
            sig_obj = Signature.from_string(sig_str)
            resp = await client.get_transaction(
                sig_obj,
                max_supported_transaction_version=0,
                commitment="confirmed",
            )
            tx = resp.value
            if tx is None:
                return None
            meta = tx.transaction.meta
            if meta is None or meta.err is not None:
                return None
            keys = tx.transaction.transaction.message.account_keys
            pre = meta.pre_balances
            post = meta.post_balances
            for i, k in enumerate(keys):
                if str(k) == self.watched_address:
                    diff = post[i] - pre[i]
                    if diff > 0:
                        return Decimal(diff) / Decimal(1_000_000_000)
            return None
        except Exception as e:
            print(f"[SolWatcher] Erreur fast get_tx : {type(e).__name__} : {e}")
            return None

    async def _handle_message(self, msg):
        """Parse une notification logsSubscribe.

        Format (observe) : msg = [LogsNotification{
            result: { context: {...}, value: RpcLogsResponse{ signature, err, logs } },
            subscription: id
        }]
        """
        try:
            # msg est une liste contenant une LogsNotification
            if not msg or not hasattr(msg, "__getitem__"):
                return
            notification = msg[0]

            # Extraire la valeur
            if not hasattr(notification, "result"):
                return
            result = notification.result
            if not hasattr(result, "value"):
                return
            value = result.value

            signature = str(value.signature)

            if signature in self._seen_signatures:
                return
            self._seen_signatures.add(signature)
            if len(self._seen_signatures) > 5000:
                self._seen_signatures = set(list(self._seen_signatures)[-2500:])

            # Ignorer les tx echouees
            if value.err is not None:
                print(f"[SolWatcher] Tx echouee ignoree : {signature[:20]}...")
                return

            print(f"\n[SolWatcher] Transaction detectee : {signature}")

            montant = await self._get_received_amount(signature)
            if montant is None or montant == 0:
                print(f"[SolWatcher] Pas de montant recu, skip")
                return

            print(f"[SolWatcher] Montant recu : {montant} SOL")
            await self.on_incoming_cb(montant, signature)

        except Exception as e:
            print(f"[SolWatcher] Erreur parsing : {e}")

    async def _get_received_amount(self, signature) -> Decimal:
        """Interroge RPC pour extraire le montant recu par le Wallet A."""
        try:
            if isinstance(signature, str):
                sig_obj = Signature.from_string(signature)
            else:
                sig_obj = signature

            # Retry : le RPC public peut retourner null juste apres la TX
            tx = None
            for attempt in range(6):
                async with AsyncClient(self.rpc_http_url) as client:
                    try:
                        resp = await client.get_transaction(
                            sig_obj,
                            max_supported_transaction_version=0,
                            commitment="confirmed",
                        )
                        tx = resp.value
                    except Exception as e:
                        print(f"[SolWatcher] get_transaction error : {type(e).__name__} : {e}")

                if tx is not None:
                    break
                print(f"[SolWatcher] get_transaction null, retry {attempt+1}/6 dans 3s...")
                await asyncio.sleep(3)

            if tx is None:
                print("[SolWatcher] get_transaction : toujours null apres 6 retries")
                return None

            meta = tx.transaction.meta
            if meta is None or meta.err is not None:
                return None

            keys = tx.transaction.transaction.message.account_keys
            pre = meta.pre_balances
            post = meta.post_balances

            for i, k in enumerate(keys):
                if str(k) == self.watched_address:
                    diff = post[i] - pre[i]
                    if diff > 0:
                        return Decimal(diff) / Decimal(1_000_000_000)
            return None
        except Exception as e:
            print(f"[SolWatcher] Erreur get_transaction : {type(e).__name__} : {e}")
            return None

    async def on_incoming(self, tx):
        pass
