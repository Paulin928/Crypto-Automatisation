# MCAD - Guide de restauration

Ce guide explique comment reprendre le projet MCAD sur un nouvel ordinateur
ou un nouvel environnement (Codespaces, VS Code local, PyCharm, etc.).

## Prerequis

- Python 3.12 (obligatoire, pas 3.14)
- Git
- Un editeur : VS Code, PyCharm, ou tout autre IDE

## Etape 1 - Cloner le depot

git clone https://github.com/Paulain928/Crypto-Automatisation.git
cd Crypto-Automatisation

## Etape 2 - Creer un environnement virtuel

python -m venv venv

Activer le venv :
- Windows : venv\Scripts\activate
- macOS / Linux : source venv/bin/activate
- Codespaces : pas besoin, le venv est deja pret

## Etape 3 - Installer les dependances

pip install --upgrade pip
pip install -r requirements.txt

## Etape 4 - Recreer les fichiers secrets (NON versionnes)

Ces fichiers sont dans .gitignore et ne sont PAS sur GitHub.

### 4.1 - Creer le dossier data

mkdir -p data

### 4.2 - Recreer .env

cp .env.example .env

Puis editer .env et remplir :
- MCAD_KEYSTORE_PASSWORD : mot de passe de chiffrement
- INFURA_SEPOLIA_WS : URL WebSocket Infura
- WALLET_A_PRIVATE_KEY : cle privee du Wallet A (66 caracteres avec 0x)

### 4.3 - Recreer data/wallets.json (Ethereum)

Option A - Regenerer (les anciens fonds seront perdus) :
python generate_wallets.py

Option B - Restaurer depuis une sauvegarde.

### 4.4 - Recreer data/wallets_sol.json (Solana)

python generate_wallets_sol.py

## Etape 5 - Verifier l'installation

python -c "from engine.distribution import DistributionEngine; from engine.gas import GasEstimator; from engine.signer import EVMSigner; from storage.repository import JobRepository; from watchers.evm import EVMWatcher; from watchers.sol import SolWatcher; print('Tous les modules importent correctement')"

## Etape 6 - Lancer les tests

python test_infura.py
python check_balance.py
python check_balance_sol.py

## Etape 7 - Lancer le robot

python main.py

## Notes importantes

- Ne jamais commit .env ni data/*.json sur GitHub
- Les cles privees doivent etre sauvegardees dans un gestionnaire de mots de passe
  (Bitwarden, 1Password, KeepassXC) avant de fermer Codespaces
- Sur un nouveau Codespace, data/ est vide : il faut recreer les wallets
- Si pip install web3 echoue avec coincurve, utiliser coincurve-cp314-fix
