"""Corrige la casse d'une adresse Ethereum selon EIP-55."""
from web3 import Web3

adresse_invalide = "0xfFAf5811105D37fd8d960f213Ef2b0aa7785E52d"
adresse_valide = Web3.to_checksum_address(adresse_invalide)

print(f"Adresse d'origine : {adresse_invalide}")
print(f"Adresse corrigee  : {adresse_valide}")
