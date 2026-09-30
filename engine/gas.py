"""Estimation des frais de gas par chaine."""

from decimal import Decimal
from web3 import AsyncWeb3


class GasEstimator:
    """Estime le gas pour une transaction simple (transfert natif)."""

    # Cout fixe d'une transaction native simple sur Ethereum : 21000 gas
    NATIVE_TRANSFER_GAS = 21_000

    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3

    async def estimate_native_transfer(self) -> Decimal:
        """Retourne le cout en ETH (Decimal) d'un transfert natif."""
        gas_price = await self.w3.eth.gas_price  # en wei
        total_wei = self.NATIVE_TRANSFER_GAS * gas_price
        return Decimal(self.w3.from_wei(total_wei, 'ether'))

    async def get_balance_eth(self, address: str) -> Decimal:
        """Retourne le solde en ETH d'une adresse."""
        balance_wei = await self.w3.eth.get_balance(address)
        return Decimal(self.w3.from_wei(balance_wei, 'ether'))
