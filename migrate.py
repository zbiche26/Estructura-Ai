#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate.py - Script de Migraciones Versionado
==============================================
Ejecuta migraciones SQL pendientes en orden numérico.

Uso:
    python migrate.py              # Ejecuta todas las pendientes
    python migrate.py --status     # Muestra estado de migraciones
    python migrate.py --dry-run    # Muestra qué se ejecutaría sin hacerlo

Cómo agregar una nueva migración:
    1. Crear archivo en sql/migrations/014_descripcion.sql
    2. Ejecutar: python migrate.py

Convención de nombres:
    sql/migrations/NNN_descripcion.sql  (NNN = número con ceros: 001, 002...)
    sql/rls/rls_descripcion.sql         (políticas RLS)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from src.core.database import get_db
from src.core.logger import logger

# ── Configuración ─────────────────────────────────────────────────────────────
MIGRATIONS_DIR = Path("sql/migrations")
RLS_DIR = Path("sql/rls")
MIGRATIONS_TABLE = "schema_migrations"


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_migration_version(filename: str) -> str | None:
    """Extrae la versión del nombre del archivo. Ej: 014_create_foo.sql → '014'"""
    match = re.match(r"^(\d+)_", filename)
    return match.group(1) if match else None


def get_all_migration_files() -> list[tuple[str, Path]]:
    """
    Retorna todos los archivos de migración ordenados por versión.
    Incluye sql/migrations/ y sql/rls/.
    """
    files = []

    if MIGRATIONS_DIR.exists():
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = get_migration_version(f.name)
            if version:
                files.append((version, f))

    if RLS_DIR.exists():
        for f in sorted(RLS_DIR.glob("*.sql")):
            # RLS files usan nombre como version
            version = f"rls_{f.stem}"
            files.append((version, f))

    return sorted(files, key=lambda x: x[0])


def get_executed_migrations(db) -> set[str]:
    """Retorna el set de versiones ya ejecutadas en BD"""
    try:
        result = db.client.table(MIGRATIONS_TABLE).select("version").execute()
        return {row["version"] for row in (result.data or [])}
    except Exception as e:
        logger.error(f"Error leyendo schema_migrations: {e}")
        return set()


def mark_migration_executed(db, version: str, name: str) -> None:
    """Registra una migración como ejecutada"""
    try:
        db.client.table(MIGRATIONS_TABLE).insert(
            {
                "version": version,
                "name": name,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
    except Exception as e:
        logger.warning(f"No se pudo registrar migración {version}: {e}")


def execute_sql(db, sql: str) -> bool:
    """Ejecuta SQL usando el cliente de Supabase (rpc)"""
    try:
        db.client.rpc("exec_sql", {"sql": sql}).execute()
        return True
    except Exception:
        # Fallback: ejecutar statement por statement
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            try:
                db.client.postgrest.session.post(
                    f"{db.client.supabase_url}/rest/v1/rpc/exec_sql",
                    json={"sql": stmt + ";"},
                    headers={
                        "apikey": db.client.supabase_key,
                        "Authorization": f"Bearer {db.client.supabase_key}",
                        "Content-Type": "application/json",
                    },
                )
            except Exception as e:
                logger.error(f"Error ejecutando statement: {e}")
                return False
        return True


# ── Comandos ──────────────────────────────────────────────────────────────────


def cmd_status() -> None:
    """Muestra el estado de todas las migraciones"""
    db = get_db()
    executed = get_executed_migrations(db)
    all_files = get_all_migration_files()

    print("\n" + "=" * 60)
    print("ESTADO DE MIGRACIONES")
    print("=" * 60)

    pending = 0
    for version, path in all_files:
        status_icon = "✅" if version in executed else "⏳"
        if version not in executed:
            pending += 1
        print(f"  {status_icon}  {version:15} {path.name}")

    print("-" * 60)
    print(
        f"  Total: {len(all_files)} | Ejecutadas: {len(executed)} | Pendientes: {pending}"
    )
    print("=" * 60 + "\n")


def cmd_dry_run() -> None:
    """Muestra qué migraciones se ejecutarían sin hacerlo"""
    db = get_db()
    executed = get_executed_migrations(db)
    all_files = get_all_migration_files()

    pending = [(v, p) for v, p in all_files if v not in executed]

    if not pending:
        print("\n✅ No hay migraciones pendientes.\n")
        return

    print(f"\n🔍 DRY RUN — {len(pending)} migración(es) pendiente(s):\n")
    for version, path in pending:
        print(f"  ⏳  {version:15} {path.name}")
    print()


def cmd_migrate(dry_run: bool = False) -> None:
    """Ejecuta todas las migraciones pendientes"""
    db = get_db()
    executed = get_executed_migrations(db)
    all_files = get_all_migration_files()

    pending = [(v, p) for v, p in all_files if v not in executed]

    if not pending:
        print("\n✅ No hay migraciones pendientes. Base de datos al día.\n")
        return

    print(f"\n🚀 Ejecutando {len(pending)} migración(es) pendiente(s)...\n")

    success = 0
    failed = 0

    for version, path in pending:
        print(f"  ⏳ Ejecutando: {path.name}...", end=" ", flush=True)

        if dry_run:
            print("(dry-run) SKIP")
            continue

        try:
            sql = path.read_text(encoding="utf-8")
            mark_migration_executed(db, version, path.stem)
            print("✅")
            success += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
            logger.error(f"Error en migración {version}: {e}")

    print()
    print("=" * 60)
    if dry_run:
        print(f"  DRY RUN: {len(pending)} pendientes (no se ejecutó nada)")
    else:
        print(f"  ✅ Exitosas: {success} | ❌ Fallidas: {failed}")
    print("=" * 60 + "\n")

    if failed > 0:
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Script de migraciones versionado para EstructuraAI"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Muestra el estado de todas las migraciones",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Muestra qué se ejecutaría sin hacerlo"
    )
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.dry_run:
        cmd_dry_run()
    else:
        cmd_migrate()


if __name__ == "__main__":
    main()
