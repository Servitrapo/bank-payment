import logging

from openupgradelib import openupgrade


_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr

    # The backup columns are created by the post-migration only when a
    # historical Redsys provider exists.
    cr.execute(
        """
        SELECT COUNT(*)
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'payment_provider'
           AND column_name IN (
               'servitrapo_mig_redsys_merchant_code',
               'servitrapo_mig_redsys_terminal',
               'servitrapo_mig_redsys_secret_key'
           )
        """
    )
    backup_column_count = cr.fetchone()[0]

    if backup_column_count != 3:
        _logger.info(
            "No Servitrapo Redsys credential backup found; "
            "end-migration has nothing to restore"
        )
        return

    cr.execute(
        """
        SELECT id,
               servitrapo_mig_redsys_merchant_code,
               servitrapo_mig_redsys_terminal,
               servitrapo_mig_redsys_secret_key
          FROM payment_provider
         WHERE code = 'redsys'
         ORDER BY id
         LIMIT 1
        """
    )
    row = cr.fetchone()

    if not row:
        raise RuntimeError(
            "Servitrapo Redsys end-migration: "
            "historical Redsys provider is missing"
        )

    (
        provider_id,
        merchant_code,
        merchant_terminal,
        secret_key,
    ) = row

    _logger.info(
        "Servitrapo Redsys end-migration starting: provider=%s, "
        "merchant_backup_present=%s, terminal_backup_present=%s, "
        "secret_backup_present=%s",
        provider_id,
        bool(merchant_code),
        bool(merchant_terminal),
        bool(secret_key),
    )

    cr.execute(
        """
        UPDATE payment_provider
           SET redsys_merchant_code = %s,
               redsys_merchant_terminal = %s,
               redsys_secret_key = %s
         WHERE id = %s
        """,
        (
            merchant_code,
            merchant_terminal,
            secret_key,
            provider_id,
        ),
    )

    cr.execute(
        """
        SELECT
            redsys_merchant_code IS NOT NULL
                AND redsys_merchant_code <> '',
            redsys_merchant_terminal IS NOT NULL
                AND redsys_merchant_terminal <> '',
            redsys_secret_key IS NOT NULL
                AND redsys_secret_key <> ''
          FROM payment_provider
         WHERE id = %s
        """,
        (provider_id,),
    )

    (
        merchant_present,
        terminal_present,
        secret_present,
    ) = cr.fetchone()

    _logger.info(
        "Servitrapo Redsys end-migration verification: provider=%s, "
        "merchant_present=%s, terminal_present=%s, secret_present=%s",
        provider_id,
        merchant_present,
        terminal_present,
        secret_present,
    )

    # If a value existed before migration, it MUST exist afterwards.
    failures = []

    if merchant_code and not merchant_present:
        failures.append("merchant_code")

    if merchant_terminal and not terminal_present:
        failures.append("merchant_terminal")

    if secret_key and not secret_present:
        failures.append("secret_key")

    if failures:
        raise RuntimeError(
            "Servitrapo Redsys end-migration failed to preserve: "
            + ", ".join(failures)
        )

    # Cleanup only after successful verification.
    cr.execute(
        """
        ALTER TABLE payment_provider
            DROP COLUMN IF EXISTS servitrapo_mig_redsys_merchant_code,
            DROP COLUMN IF EXISTS servitrapo_mig_redsys_terminal,
            DROP COLUMN IF EXISTS servitrapo_mig_redsys_secret_key
        """
    )

    _logger.info(
        "Servitrapo Redsys end-migration completed successfully "
        "for provider %s",
        provider_id,
    )
