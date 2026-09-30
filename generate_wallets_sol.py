"""Genere 1 wallet A + 5 wallets B pour Solana Devnet.

ATTENTION : usage DEVNET uniquement.
"""
import json
from solders.keypair import Keypair


def generate_wallet(label):
    kp = Keypair()
    return {
        "label": label,
        "address": str(kp.pubkey()),
        "private_key": str(kp),  # format array de 64 bytes
    }


def main():
    print("\n=== GENERATION DES WALLETS SOLANA DEVNET ===\n")

    wallets = []
    wa = generate_wallet("A")
    wallets.append(wa)
    print(f"WALLET A (reception)")
    print(f"  Adresse     : {wa['address']}")
    print(f"  Cle privee  : {wa['private_key'][:50]}...")
    print()

    for i in range(1, 6):
        wb = generate_wallet(f"B{i}")
        wallets.append(wb)
        print(f"WALLET B{i} (destination)")
        print(f"  Adresse     : {wb['address']}")
        print()

    with open("data/wallets_sol.json", "w") as f:
        json.dump(wallets, f, indent=2)

    print("=" * 60)
    print("Wallets sauvegardes dans data/wallets_sol.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
