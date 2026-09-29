"""Genere 1 wallet A + 5 wallets B pour testnet Sepolia.

ATTENTION : usage TESTNET uniquement. Ne jamais utiliser pour du vrai argent.
"""
from eth_account import Account
import json

Account.enable_unaudited_hdwallet_features()

def generate_wallet(label):
    acct = Account.create()
    return {
        "label": label,
        "address": acct.address,
        "private_key": acct.key.hex(),
    }

def main():
    print("\n=== GENERATION DES WALLETS TESTNET SEPOLIA ===\n")
    print("ATTENTION : usage testnet uniquement.\n")

    wallets = []
    # Wallet A (reception)
    wa = generate_wallet("A")
    wallets.append(wa)
    print(f"WALLET A (reception)")
    print(f"  Adresse     : {wa['address']}")
    print(f"  Cle privee  : {wa['private_key']}")
    print()

    # 5 wallets B
    for i in range(1, 6):
        wb = generate_wallet(f"B{i}")
        wallets.append(wb)
        print(f"WALLET B{i} (destination)")
        print(f"  Adresse     : {wb['address']}")
        print(f"  Cle privee  : {wb['private_key']}")
        print()

    # Sauvegarde dans un fichier local (ignore par git)
    with open("data/wallets.json", "w") as f:
        json.dump(wallets, f, indent=2)

    print("=" * 60)
    print("Wallets sauvegardes dans data/wallets.json")
    print("Ce fichier est dans .gitignore et ne sera JAMAIS pousse sur GitHub.")
    print("=" * 60)

if __name__ == "__main__":
    main()
