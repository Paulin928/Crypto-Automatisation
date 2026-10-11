"""Test unitaire du SolDistributor avec un signer mocke.

Ne depend d'aucun reseau Solana.
"""
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from engine.sol_distributor import SolDistributor
from engine.sol_signer import SolSigner


async def main():
    # Signer mocke
    signer = AsyncMock(spec=SolSigner)
    signer.estimate_fee.return_value = 5000
    signer.send_native.return_value = "5XYZ" + "a" * 60  # fausse signature

    dist = SolDistributor(
        signer=signer,
        wallets_b=[f"walletB{i}" + "x" * 36 for i in range(1, 6)],
        ratios_4_first=[0.48, 0.20, 0.15, 0.10],
        fee_lamports_per_tx=5000,
        min_lamports=1_000_000,
        dust_limit_lamports=5000,
        dry_run=False,
    )

    worker = asyncio.create_task(dist.run_worker())

    # Simule 1 SOL recu (1_000_000_000 lamports)
    await dist.handle_incoming(Decimal("1.0"), "sig_test_1sol")

    # Attendre que la queue soit vide
    await dist._queue.join()
    worker.cancel()

    print("\n=== Verifications ===")
    print(f"send_native appele : {signer.send_native.call_count} fois (attendu 5)")
    print()
    print("Appels send_native :")
    for call in signer.send_native.call_args_list:
        addr, amt = call.args
        pct = amt / 1_000_000_000 * 100
        print(f"  -> {addr[:16]}... : {amt} lamports ({pct:.4f}%)")

    print()
    print("=== Attendu ===")
    print(f"  B1 : 480000000 lamports (48.00%)")
    print(f"  B2 : 200000000 lamports (20.00%)")
    print(f"  B3 : 150000000 lamports (15.00%)")
    print(f"  B4 : 100000000 lamports (10.00%)")
    print(f"  B5 : 69975000 lamports (7% - 25000 frais)")


asyncio.run(main())
