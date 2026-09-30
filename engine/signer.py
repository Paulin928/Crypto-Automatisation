"""Signature et envoi de transactions Ethereum."""

from decimal import Decimal
from eth_account import Account
from web3 import AsyncWeb3


class EVMSigner:
    """Signe et envoie des transactions natives (ETH) sur une chaine EVM."""

    def __init__(self, w3: AsyncWeb3, private_key: str):
        self.w3 = w3
        self.account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self.account.address

    async def send_native(self, to_address: str, amount_eth: Decimal) -> str:
        """Envoie `amount_eth` ETH a `to_address`. Retourne le hash de la tx."""
        nonce = await self.w3.eth.get_transaction_count(self.address, 'pending')
        gas_price = await self.w3.eth.gas_price

        tx = {
            "nonce": nonce,
            "to": to_address,
            "value": self.w3.to_wei(amount_eth, 'ether'),
            "gas": 21_000,
            "gasPrice": gas_price,
            "chainId": await self.w3.eth.chain_id,
        }

        # Estimation du gas (au cas ou le reseau est congestionne)
        try:
            tx["gas"] = await self.w3.eth.estimate_gas(tx)
        except Exception:
            pass  # on garde 21000 par defaut

        signed = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()
