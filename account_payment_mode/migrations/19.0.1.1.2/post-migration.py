import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr

    # The OCA Redsys provider used in Odoo 18 was renamed by the upgrade
    # service to payment_redsys_oca because Odoo 19 provides payment_redsys.
    cr.execute(
        """
        SELECT id, name, state
          FROM ir_module_module
         WHERE name IN ('payment_redsys', 'payment_redsys_oca')
         ORDER BY name
        """
    )
    modules_before = cr.fetchall()
    _logger.info(
        "Servitrapo Redsys migration - modules before migration: %s",
        modules_before,
    )

    cr.execute(
        """
        SELECT id
          FROM payment_provider
         WHERE code = 'redsys'
         ORDER BY id
         LIMIT 1
        """
    )
    row = cr.fetchone()

    if not row:
        _logger.info(
            "No historical Redsys provider found; skipping provider migration"
        )
    else:
        historical_provider_id = row[0]

        # Odoo 19 renamed redsys_terminal to redsys_merchant_terminal.
        # Keep the legacy column untouched and create/copy the native field.
        cr.execute(
            """
            ALTER TABLE payment_provider
            ADD COLUMN IF NOT EXISTS redsys_merchant_terminal varchar
            """
        )
        cr.execute(
            """
            UPDATE payment_provider
               SET redsys_merchant_terminal = redsys_terminal
             WHERE id = %s
               AND COALESCE(redsys_merchant_terminal, '') = ''
               AND COALESCE(redsys_terminal, '') <> ''
            """,
            (historical_provider_id,),
        )

        # Find the placeholder provider referenced by the native Odoo XML ID.
        cr.execute(
            """
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'payment'
               AND name = 'payment_provider_redsys'
               AND model = 'payment.provider'
             LIMIT 1
            """
        )
        native_xmlid_row = cr.fetchone()
        native_placeholder_id = (
            native_xmlid_row[0] if native_xmlid_row else None
        )

        if (
            native_placeholder_id
            and native_placeholder_id != historical_provider_id
        ):
            # Before deleting the native placeholder, make sure that it has
            # no business/history references. Payment-method relations are
            # intentionally excluded here because they are migrated below.
            cr.execute(
                """
                SELECT
                    (SELECT COUNT(*)
                       FROM payment_transaction
                      WHERE provider_id = %s)
                  + (SELECT COUNT(*)
                       FROM payment_token
                      WHERE provider_id = %s)
                  + (SELECT COUNT(*)
                       FROM account_payment_method_line
                      WHERE payment_provider_id = %s)
                  + (SELECT COUNT(*)
                       FROM payment_country_rel
                      WHERE payment_id = %s)
                  + (SELECT COUNT(*)
                       FROM payment_currency_rel
                      WHERE payment_provider_id = %s)
                  + (SELECT COUNT(*)
                       FROM payment_provider_pos_payment_method_rel
                      WHERE payment_provider_id = %s)
                """,
                (
                    native_placeholder_id,
                    native_placeholder_id,
                    native_placeholder_id,
                    native_placeholder_id,
                    native_placeholder_id,
                    native_placeholder_id,
                ),
            )
            blocking_refs = cr.fetchone()[0]

            if blocking_refs:
                raise RuntimeError(
                    "Native Redsys placeholder still has protected references; "
                    "migration aborted"
                )

            # Preserve the standard Odoo 19 payment-method relations already
            # attached to the native placeholder (card, bizum, ...).
            cr.execute(
                """
                INSERT INTO payment_method_payment_provider_rel
                    (payment_provider_id, payment_method_id)
                SELECT %s, payment_method_id
                  FROM payment_method_payment_provider_rel
                 WHERE payment_provider_id = %s
                ON CONFLICT DO NOTHING
                """,
                (historical_provider_id, native_placeholder_id),
            )

            # Redirect the canonical Odoo XML ID to the historical provider.
            cr.execute(
                """
                UPDATE ir_model_data
                   SET res_id = %s
                 WHERE module = 'payment'
                   AND name = 'payment_provider_redsys'
                   AND model = 'payment.provider'
                """,
                (historical_provider_id,),
            )

            cr.execute(
                """
                DELETE FROM payment_method_payment_provider_rel
                 WHERE payment_provider_id = %s
                """,
                (native_placeholder_id,),
            )

            cr.execute(
                """
                DELETE FROM payment_provider
                 WHERE id = %s
                """,
                (native_placeholder_id,),
            )

        # Merge the obsolete OCA module into the native Odoo 19 module.
        cr.execute(
            """
            SELECT 1
              FROM ir_module_module
             WHERE name = 'payment_redsys_oca'
            """
        )
        if cr.fetchone():
            openupgrade.update_module_names(
                cr,
                [('payment_redsys_oca', 'payment_redsys')],
                merge_modules=True,
            )

        # After the module merge, associate the historical provider with the
        # native payment_redsys module. The native XML data will later assign
        # the Odoo 19 redirect view while preserving credentials and history.
        cr.execute(
            """
            UPDATE payment_provider
               SET module_id = (
                   SELECT id
                     FROM ir_module_module
                    WHERE name = 'payment_redsys'
                    LIMIT 1
               )
             WHERE id = %s
            """,
            (historical_provider_id,),
        )

    cr.execute(
        """
        SELECT id, name, state, latest_version
          FROM ir_module_module
         WHERE name IN ('payment_redsys', 'payment_redsys_oca')
         ORDER BY name
        """
    )
    modules_after = cr.fetchall()

    _logger.info(
        "Servitrapo Redsys migration - modules after migration: %s",
        modules_after,
    )
