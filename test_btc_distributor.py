import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from engine.btc_distributor import BtcDistributor
from engine.btc_signer import BtcSigner


async def main():
    # Signer mocke : pas d'envoi reel
    signer = AsyncMock(spec=BtcSigner)
    signer.estimate_fee.return_value = 282   # fee par tx
    signer.send_native.return_value = "deadbeef" * 8

    dist = BtcDistributor(
        signer=signer,
        wallets_b=[f"tb1qB{i}xxxxxxxxxxxxxxxxxxxxxxxxxxxxx" for i in range(1, 6)],
        ratios_4_first=[0.48, 0.20, 0.15, 0.10],
        fee_rate_sat_vb=2,
        min_satoshis=10000,
        dust_limit=546,
        dry_run=False,
    )

    worker = asyncio.create_task(dist.run_worker())

    # 3 TX qui arrivent a quelques ms d'intervalle
    await dist.handle_incoming(Decimal("0.001"), "tx_aaa")  # 100_000 sat
    await dist.handle_incoming(Decimal("0.001"), "tx_bbb")
    await dist.handle_incoming(Decimal("0.001"), "tx_ccc")

    # Attendre que tout soit traite
    await dist._queue.join()
    worker.cancel()

    print("\n=== Verifications ===")
    print("send_native appele :", signer.send_native.call_count, "fois (attendu 15)")
    print()
    print("5 premiers appels (= tx_aaa) :")
    for c in signer.send_native.call_args_list[:5]:
        print("  ", c)
    print()
    print("Dernier appel (= tx_ccc, wallet B5) :")
    print("  ", signer.send_native.call_args_list[-1])


asyncio.run(main())
