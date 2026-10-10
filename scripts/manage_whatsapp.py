"""Local operator CLI. No public endpoint for assigning roles or devices."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from djua_energy.channels.whatsapp.repository import ROLES, WhatsAppRepository
from djua_energy.database.realtime_store import _database_path_from_env


def main():
    parser = argparse.ArgumentParser(description="Administration des acces WhatsApp DJUA")
    parser.add_argument("--database", default=None, help="Chemin SQLite; sinon DJUA_DATABASE_URL")
    commands = parser.add_subparsers(dest="command", required=True)
    user = commands.add_parser("user", help="Creer ou mettre a jour un compte")
    user.add_argument("--phone", default=os.getenv("WHATSAPP_BOOTSTRAP_PHONE"), required=not os.getenv("WHATSAPP_BOOTSTRAP_PHONE"))
    user.add_argument("--role", choices=sorted(ROLES), required=True)
    user.add_argument("--customer-id")
    user.add_argument("--name", default="")
    user.add_argument("--inactive", action="store_true")
    for name in ("grant", "revoke"):
        command = commands.add_parser(name)
        command.add_argument("--phone", required=True)
        command.add_argument("--device", required=True)
        if name == "grant":
            command.add_argument("--kit")
            command.add_argument("--primary", action="store_true")
    status = commands.add_parser("status", help="Etat d'un message, sans contenu prive")
    status.add_argument("--message-id", required=True)
    args = parser.parse_args()
    repo = WhatsAppRepository(args.database or _database_path_from_env())
    if args.command == "user":
        repo.upsert_user(args.phone, args.role, args.customer_id, args.name, not args.inactive)
        print("Compte WhatsApp enregistre.")
    elif args.command == "grant":
        repo.grant_device(args.phone, args.device, args.kit, args.primary)
        print("Acces au device enregistre.")
    elif args.command == "revoke":
        repo.revoke_device(args.phone, args.device)
        print("Acces au device retire.")
    else:
        print(repo.message_status(args.message_id) or "Message introuvable.")


if __name__ == "__main__":
    main()
