"""Watcher Bitcoin via l'API HTTP Blockstream (polling)."""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable, Optional

import aiohttp

from watchers.base import ChainWatcher


SATS_PER_BTC = Decimal("100000000")


@dataclass
class BtcUtxo:
    txid: str
    vout: int
    value_sat: int
    address: str


class BtcWatcher(ChainWatcher):
    """Surveille une adresse BTC via l'API Blockstream (REST + polling)."""

    def __init__(
        self,
        api_base: str,
        watched_address: str,
        on_incoming: Callable[[Decimal, str], Awaitable[None]],
        poll_interval: int = 10,
        confirmations_required: int = 1,
    ):
        super().__init__(
            chain_id="bitcoin",
            rpc_url=api_base,
            watched_address=watched_address,
        )
        self.api_base = api_base.rstrip("/")
        self._notify = on_incoming
        self.poll_interval = poll_interval
        self.confirmations_required = confirmations_required

        self._seen_txids: set[str] = set()
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self._running = True
        self._session = aiohttp.ClientSession()
        try:
            await self._prime_seen_txids()
            while self._running:
                try:
                    await self._poll_once()
                except Exception as e:
                    print(f"[BTC-WATCH] erreur poll : {e!r}")
                await asyncio.sleep(self.poll_interval)
        finally:
            await self._close_session()

    async def stop(self):
        self._running = False
        await self._close_session()

    async def on_incoming(self, tx):
        """Implementation requise par ChainWatcher.

        Le watcher BTC branche un callback via le constructeur et
        l'appelle directement depuis _poll_once. Cette methode ne sert
        qu'a satisfaire l'abstract method de la classe mere.
        """
        if isinstance(tx, tuple) and len(tx) == 2:
            montant, txid = tx
            await self._notify(montant, txid)

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _ensure_session(self):
        """Cree la session aiohttp si elle n'existe pas encore."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _get(self, path: str):
        await self._ensure_session()
        url = f"{self.api_base}{path}"
        async with self._session.get(url, timeout=15) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return await resp.json()

    async def _prime_seen_txids(self):
        """Marque comme 'vues' toutes les TX deja confirmees de l'adresse."""
        txs = await self._get(f"/address/{self.watched_address}/txs")
        if not txs:
            print("[BTC-WATCH] Aucune TX existante sur cette adresse")
            return
        for tx in txs:
            self._seen_txids.add(tx["txid"])
        print(
            f"[BTC-WATCH] Historique initial : {len(self._seen_txids)} TX "
            f"(ignorees au demarrage)"
        )

    async def _poll_once(self):
        txs = await self._get(f"/address/{self.watched_address}/txs")
        if not txs:
            return

        for tx in txs:
            txid = tx["txid"]
            if txid in self._seen_txids:
                continue

            status = tx.get("status", {})
            confirmed = status.get("confirmed", False)
            block_height = status.get("block_height")

            confirmations = 0
            if confirmed and block_height is not None:
                tip = await self._get("/blocks/tip/height")
                if tip is not None:
                    confirmations = tip - block_height + 1

            if confirmations < self.confirmations_required:
                continue

            recu_sat = self._sum_received(tx)
            if recu_sat <= 0:
                self._seen_txids.add(txid)
                continue

            self._seen_txids.add(txid)
            montant_btc = Decimal(recu_sat) / SATS_PER_BTC
            print(
                f"[BTC-WATCH] TX entrante : {montant_btc} BTC "
                f"(txid={txid[:16]}..., conf={confirmations})"
            )
            await self._notify(montant_btc, txid)

    def _sum_received(self, tx: dict) -> int:
        total = 0
        for vout in tx.get("vout", []):
            addr = vout.get("scriptpubkey_address")
            if addr == self.watched_address:
                total += int(vout.get("value", 0))
        return total

    async def list_utxos(self) -> list[BtcUtxo]:
        data = await self._get(f"/address/{self.watched_address}/utxo")
        if not data:
            return []
        return [
            BtcUtxo(
                txid=u["txid"],
                vout=u["vout"],
                value_sat=int(u["value"]),
                address=self.watched_address,
            )
            for u in data
        ]

    async def get_balance_sat(self) -> int:
        utxos = await self.list_utxos()
        return sum(u.value_sat for u in utxos)
