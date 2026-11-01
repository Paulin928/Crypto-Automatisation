"""Persistance des jobs dans SQLite."""
import aiosqlite


class JobRepository:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT,
                    tx_hash TEXT UNIQUE,
                    montant_initial TEXT,
                    reste_final TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    step_index INTEGER,
                    status TEXT,
                    montant TEXT,
                    reste TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def create_job(self, chain, tx_hash, montant_initial) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO jobs (chain, tx_hash, montant_initial) VALUES (?,?,?)",
                (chain, tx_hash, str(montant_initial)),
            )
            await db.commit()
            return cur.lastrowid

    async def mark_step(self, job_id, idx, status, montant, reste):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO steps (job_id, step_index, status, montant, reste) VALUES (?,?,?,?,?)",
                (job_id, idx, status, str(montant), str(reste)),
            )
            await db.commit()

    async def complete_job(self, job_id, reste_final):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE jobs SET status='COMPLETED', reste_final=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(reste_final), job_id),
            )
            await db.commit()

    # ------------------------------------------------------------------ #
    # Catch-up : verification des TX deja traitees
    # ------------------------------------------------------------------ #
    async def get_processed_tx_hashes(self, chain: str) -> set:
        """Retourne tous les tx_hash deja traites (status COMPLETED)."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT tx_hash FROM jobs WHERE chain=? AND status='COMPLETED'",
                (chain,),
            )
            rows = await cur.fetchall()
            return {r[0] for r in rows}

    async def is_tx_processed(self, chain: str, tx_hash: str) -> bool:
        """Verifie si une TX a deja ete traitee (status COMPLETED)."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM jobs WHERE chain=? AND tx_hash=? AND status='COMPLETED'",
                (chain, tx_hash),
            )
            row = await cur.fetchone()
            return row is not None
