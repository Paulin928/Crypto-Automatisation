"""BtcSigner regtest — utilise Bitcoin Core via JSON-RPC.

L'interface est identique a BtcSigner (bitcoinlib) pour que
BtcDistributor puisse utiliser les deux indistinctement.

Ne PAS utiliser pour testnet/mainnet : ce signer ne fonctionne
qu'avec un noeud Bitcoin Core local en mode regtest.
"""

import asyncio
import json
import base64
import urllib.request
from decimal import Decimal


SATS_PER_BTC = Decimal("100000000")


class BtcSignerCli:
    """Signe et envoie via bitcoin-cli (JSON-RPC) — regtest uniquement."""

    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:18443",
        rpc_user: str = "btc",
        rpc_password: str = "btcpass",
        wallet_name: str = "faucet",
        fee_rate_sat_vb: int = 2,
    ):
        self.rpc_url = rpc_url
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.wallet_name = wallet_name
        self.fee_rate_sat_vb = fee_rate_sat_vb

    # ------------------------------------------------------------------ #
    # Estimation
    # ------------------------------------------------------------------ #
    def estimate_fee(self, num_inputs: int = 1, num_outputs: int = 2) -> int:
        """Estimation simple : ~68 vB par input P2WPKH, ~31 vB par output, +11 vB."""
        vbytes = num_inputs * 68 + num_outputs * 31 + 11
        return vbytes * self.fee_rate_sat_vb

    # ------------------------------------------------------------------ #
    # Envoi
    # ------------------------------------------------------------------ #
    async def send_native(self, to_address: str, amount_sat: int) -> str:
        """Envoie `amount_sat` satoshis a `to_address`. Retourne le txid."""
        amount_btc = Decimal(amount_sat) / SATS_PER_BTC

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._send_to_address_blocking,
            to_address,
            float(amount_btc),
        )

    def _send_to_address_blocking(self, to_address: str, amount_btc: float) -> str:
        """Appel RPC sendtoaddress."""
        return self._rpc("sendtoaddress", [to_address, amount_btc])

    # ------------------------------------------------------------------ #
    # JSON-RPC bas niveau
    # ------------------------------------------------------------------ #
    def _rpc(self, method: str, params: list):
        """Envoie une requete JSON-RPC a Bitcoin Core."""
        payload = {
            "jsonrpc": "1.0",
            "id": "btc-signer-cli",
            "method": method,
            "params": params,
        }
        data = json.dumps(payload).encode("utf-8")

        # URL avec le nom du wallet : http://host:port/wallet/<name>
        url = f"{self.rpc_url}/wallet/{self.wallet_name}"

        auth = base64.b64encode(
            f"{self.rpc_user}:{self.rpc_password}".encode("utf-8")
        ).decode("ascii")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"RPC HTTPError {e.code}: {error_body}") from e

        if body.get("error"):
            raise RuntimeError(f"RPC error: {body['error']}")
        return body["result"]
