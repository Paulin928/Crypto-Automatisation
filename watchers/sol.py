"""Watcher Solana : detecte les receptions sur le Wallet A via logsSubscribe."""
import asyncio
from decimal import Decimal

from solana.rpc.websocket_api import connect
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions

from watchers.base import ChainWatcher


class SolWatcher(ChainWatcher):
    """Surveille une adresse Solana via logsSubscribe."""

    def __init__(self, rpc_ws_url: str, rpc_http_url: str, watched_address: str, on_incoming_cb):
        super().__init__("solana", rpc_ws_url, watched_address)
        self.rpc_ws_url = rpc_ws_url
        self.rpc_http_url = rpc_http_url
        self.on_incoming_cb = on_incoming_cb
        self._running = False
        self._seen_signatures = set()

    async def start(self):
        self._running = True
        retry_delay = 5

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

    async def _get_received_amount(self, signature: str) -> Decimal:
        """Interroge RPC pour extraire le montant recu par le Wallet A."""
        try:
            async with AsyncClient(self.rpc_http_url) as client:
                resp = await client.get_transaction(
                    signature,
                    encoding="jsonParsed",
                    max_supported_transaction_version=0,
                )
                tx = resp.value
                if tx is None:
                    return None

                meta = tx.transaction.meta
                if meta is None or meta.err is not None:
                    return None

                account_keys = tx.transaction.transaction.message.account_keys
                pre_balances = meta.pre_balances
                post_balances = meta.post_balances

                for i, key in enumerate(account_keys):
                    addr = str(key.pubkey) if hasattr(key, "pubkey") else str(key)
                    if addr == self.watched_address:
                        diff = post_balances[i] - pre_balances[i]
                        if diff > 0:
                            return Decimal(diff) / Decimal(1_000_000_000)
                return None
        except Exception as e:
            print(f"[SolWatcher] Erreur get_transaction : {e}")
            return None

    async def on_incoming(self, tx):
        pass
