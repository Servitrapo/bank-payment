import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute(
        """
        SELECT name, state
          FROM ir_module_module
         WHERE name IN ('account_payment_mode', 'account_payment_partner')
         ORDER BY name
        """
    )
    before = env.cr.fetchall()

    _logger.info(
        "Servitrapo migration - payment modules before merge: %s",
        before,
    )

    env.cr.execute(
        """
        SELECT 1
          FROM ir_module_module
         WHERE name = 'account_payment_partner'
        """
    )

    if env.cr.fetchone():
        _logger.info(
            "Merging obsolete account_payment_partner into account_payment_mode"
        )

        openupgrade.update_module_names(
            env.cr,
            [
                (
                    "account_payment_partner",
                    "account_payment_mode",
                )
            ],
            merge_modules=True,
        )
    else:
        _logger.info(
            "account_payment_partner already merged; no action required"
        )

    env.cr.execute(
        """
        SELECT name, state
          FROM ir_module_module
         WHERE name IN ('account_payment_mode', 'account_payment_partner')
         ORDER BY name
        """
    )
    after = env.cr.fetchall()

    _logger.info(
        "Servitrapo migration - payment modules after merge: %s",
        after,
    )
