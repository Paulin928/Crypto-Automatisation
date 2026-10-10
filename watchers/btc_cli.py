"""Watcher Bitcoin regtest via Bitcoin Core JSON-RPC.

Detecte les TX entrantes vers l'adresse surveillee, emet un event
`on_incoming(montant_btc: Decimal, tx_hash: str)` par TX confirmee.
"""

import asyncio
import base64
import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable, Optional

from watchers.base import ChainWatcher


SATS_PER_BTC = Decimal("100000000")


@dataclass
class BtcUtxo:
    txid: str
    vout: int
    value_sat: int
    address: str


class BtcWatcherCli(ChainWatcher):
    """Surveille une adresse BTC regtest via Bitcoin Core JSON-RPC."""

    def __init__(
        self,
        watched_address: str,
        on_incoming: Callable[[Decimal, str], Awaitable[None]],
        rpc_url: str = "http://127.0.0.1:18443",
        rpc_user: str = "btc",
        rpc_password: str = "btcpass",
        wallet_name: str = "faucet",
        poll_interval: int = 3,
        confirmations_required: int = 1,
    ):
        super().__init__(
            chain_id="bitcoin-regtest",
            rpc_url=rpc_url,
            watched_address=watched_address,
        )
        self.on_incoming_cb = on_incoming
        self.rpc_url = rpc_url
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.wallet_name = wallet_name
        self.poll_interval = poll_interval
        self.confirmations_required = confirmations_required

        self._seen_txids: set[str] = set()
        self._running = False

    async def start(self):
        self._running = True
        await self._prime_seen_txids()
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                print(f"[BTC-WATCH-CLI] erreur poll : {e!r}")
            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        self._running = False

    async def on_incoming(self, tx):
        """Implementation requise par ChainWatcher (relais)."""
        if isinstance(tx, tuple) and len(tx) == 2:
            montant, txid = tx
            await self.on_incoming_cb(montant, txid)

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    async def _prime_seen_txids(self):
        """Marque comme deja vues les TX recues avant le demarrage."""
        try:
            txs = await asyncio.get_running_loop().run_in_executor(
                None, self._list_received_blocking
            )
            for tx in txs:
                self._seen_txids.add(tx["txid"])
            print(f"[BTC-WATCH-CLI] Historique initial : {len(self._seen_txids)} TX ignorees")
        except Exception as e:
            print(f"[BTC-WATCH-CLI] Erreur prime : {e!r}")

    async def _poll_once(self):
        txs = await asyncio.get_running_loop().run_in_executor(
            None, self._list_received_blocking
        )
        for tx in txs:
            txid = tx["txid"]
            if txid in self._seen_txids:
                continue

            confirmations = tx.get("confirmations", 0)
            if confirmations < self.confirmations_required:
                continue

            amount_btc = Decimal(str(tx["amount"]))
            if amount_btc <= 0:
                self._seen_txids.add(txid)
                continue

            self._seen_txids.add(txid)
            print(
                f"[BTC-WATCH-CLI] TX entrante : {amount_btc} BTC "
                f"(txid={txid[:16]}..., conf={confirmations})"
            )
            await self.on_incoming_cb(amount_btc, txid)

    def _list_received_blocking(self) -> list:
        """Appelle listtransactions et filtre sur l'adresse surveillee."""
        # listtransactions "*" <count> <skip> <include_watchonly>
        txs = self._rpc(
            "listtransactions",
            ["*", 100, 0, True],
            wallet=self.wallet_name,
        )
        # Filtre : uniquement les receptions vers notre adresse
        result = []
        for tx in txs:
            if tx.get("category") != "receive":
                continue
            if tx.get("address") != self.watched_address:
                continue
            if "txid" not in tx:
                continue
            result.append(tx)
        return result

    def _rpc(self, method: str, params: list, wallet: Optional[str] = None):
        url = self.rpc_url
        if wallet:
            url += f"/wallet/{wallet}"
        payload = {
            "jsonrpc": "1.0",
            "id": "btc-watch-cli",
            "method": method,
            "params": params,
        }
        auth = base64.b64encode(
            f"{self.rpc_user}:{self.rpc_password}".encode()
        ).decode()
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
        if body.get("error"):
            raise RuntimeError(f"RPC error: {body['error']}")
        return body["result"]

    async def get_balance_sat(self) -> int:
        """Solde non utilise en regtest (le noeud gere)."""
        return 0
