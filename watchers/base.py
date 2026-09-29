"""Module de base pour tous les watchers."""
from abc import ABC, abstractmethod


class ChainWatcher(ABC):
    def __init__(self, chain_id: str, rpc_url: str, watched_address: str):
        self.chain_id = chain_id
        self.rpc_url = rpc_url
        self.watched_address = watched_address

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self): ...

    @abstractmethod
    async def on_incoming(self, tx): ...
