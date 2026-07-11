# Stage 6 audit remediation (Finding A-1):
#
# The original check_vat_return_lock trigger only covered INSERT/UPDATE on
# accounting_journal. Journal lines inside a filed VAT period could still be
# edited or deleted, and whole journals could be deleted, silently altering
# the figures behind a submitted VAT return.
#
# This migration:
#   1. Rewrites check_vat_return_lock() to resolve the effective journal date
#      for both accounting_journal and accounting_journalline, for INSERT,
#      UPDATE and DELETE. On UPDATE both the OLD and NEW dates are checked so
#      a journal cannot be moved out of a locked range and then edited.
#   2. Attaches the trigger to accounting_journalline and extends the
#      accounting_journal trigger to DELETE.
#   3. Applies the same OLD-date check on UPDATE to check_period_not_closed()
#      (the closed-period trigger already covered both tables and DELETE).

from django.db import migrations

HARDENED_VAT_LOCK_FN = """
    CREATE OR REPLACE FUNCTION check_vat_return_lock()
    RETURNS TRIGGER AS $$
    DECLARE
        v_old_date date;
        v_new_date date;
        v_tenant_id uuid;
        v_check_date date;
    BEGIN
        IF TG_TABLE_NAME = 'accounting_journal' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                v_old_date := OLD.date;
                v_tenant_id := OLD.tenant_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                v_new_date := NEW.date;
                v_tenant_id := NEW.tenant_id;
            END IF;
        ELSIF TG_TABLE_NAME = 'accounting_journalline' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT date, tenant_id INTO v_old_date, v_tenant_id
                FROM accounting_journal WHERE id = OLD.journal_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT date, tenant_id INTO v_new_date, v_tenant_id
                FROM accounting_journal WHERE id = NEW.journal_id;
            END IF;
        END IF;

        FOREACH v_check_date IN ARRAY ARRAY[v_old_date, v_new_date] LOOP
            IF v_check_date IS NOT NULL AND v_tenant_id IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM accounting_vatreturn
                    WHERE tenant_id = v_tenant_id
                      AND start_date <= v_check_date
                      AND end_date >= v_check_date
                ) THEN
                    RAISE EXCEPTION 'Operation blocked. The date % falls within a locked VAT return period.', v_check_date;
                END IF;
            END IF;
        END LOOP;

        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
"""

HARDENED_PERIOD_FN = """
    CREATE OR REPLACE FUNCTION check_period_not_closed()
    RETURNS TRIGGER AS $$
    DECLARE
        v_old_date date;
        v_new_date date;
        v_tenant_id uuid;
        v_check_date date;
    BEGIN
        IF TG_TABLE_NAME = 'accounting_journal' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                v_old_date := OLD.date;
                v_tenant_id := OLD.tenant_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                v_new_date := NEW.date;
                v_tenant_id := NEW.tenant_id;
            END IF;
        ELSIF TG_TABLE_NAME = 'accounting_journalline' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT date, tenant_id INTO v_old_date, v_tenant_id
                FROM accounting_journal WHERE id = OLD.journal_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT date, tenant_id INTO v_new_date, v_tenant_id
                FROM accounting_journal WHERE id = NEW.journal_id;
            END IF;
        END IF;

        FOREACH v_check_date IN ARRAY ARRAY[v_old_date, v_new_date] LOOP
            IF v_check_date IS NOT NULL AND v_tenant_id IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM accounting_accountingperiod
                    WHERE tenant_id = v_tenant_id
                      AND start_date <= v_check_date
                      AND end_date >= v_check_date
                      AND is_closed = TRUE
                ) THEN
                    RAISE EXCEPTION 'Operation blocked. The date % falls within a closed accounting period.', v_check_date;
                END IF;
            END IF;
        END LOOP;

        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
"""

# Original function bodies (from 0001 and 0006) for reverse migration
ORIGINAL_VAT_LOCK_FN = """
    CREATE OR REPLACE FUNCTION check_vat_return_lock()
    RETURNS TRIGGER AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM accounting_vatreturn
            WHERE tenant_id = NEW.tenant_id
              AND start_date <= NEW.date
              AND end_date >= NEW.date
        ) THEN
            RAISE EXCEPTION 'Operation blocked. The date % falls within a locked VAT return period.', NEW.date;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
"""

ORIGINAL_PERIOD_FN = """
    CREATE OR REPLACE FUNCTION check_period_not_closed()
    RETURNS TRIGGER AS $$
    DECLARE
        v_date date;
        v_closed_period_exists boolean;
        v_tenant_id uuid;
    BEGIN
        IF TG_TABLE_NAME = 'accounting_journal' THEN
            IF TG_OP = 'DELETE' THEN
                v_date := OLD.date;
                v_tenant_id := OLD.tenant_id;
            ELSE
                v_date := NEW.date;
                v_tenant_id := NEW.tenant_id;
            END IF;
        ELSIF TG_TABLE_NAME = 'accounting_journalline' THEN
            IF TG_OP = 'DELETE' THEN
                SELECT date, tenant_id INTO v_date, v_tenant_id FROM accounting_journal WHERE id = OLD.journal_id;
            ELSE
                SELECT date, tenant_id INTO v_date, v_tenant_id FROM accounting_journal WHERE id = NEW.journal_id;
            END IF;
        END IF;

        IF v_date IS NOT NULL AND v_tenant_id IS NOT NULL THEN
            SELECT EXISTS (
                SELECT 1 FROM accounting_accountingperiod
                WHERE tenant_id = v_tenant_id
                  AND start_date <= v_date
                  AND end_date >= v_date
                  AND is_closed = TRUE
            ) INTO v_closed_period_exists;

            IF v_closed_period_exists THEN
                RAISE EXCEPTION 'Operation blocked. The date % falls within a closed accounting period.', v_date;
            END IF;
        END IF;

        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
"""


def harden_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(HARDENED_VAT_LOCK_FN)
        cursor.execute(HARDENED_PERIOD_FN)

        # Recreate the journal-level VAT lock trigger with DELETE coverage
        cursor.execute("DROP TRIGGER IF EXISTS check_vat_return_lock_trigger ON accounting_journal;")
        cursor.execute("""
            CREATE TRIGGER check_vat_return_lock_trigger
            BEFORE INSERT OR UPDATE OR DELETE ON accounting_journal
            FOR EACH ROW
            EXECUTE FUNCTION check_vat_return_lock();
        """)

        # New line-level VAT lock trigger
        cursor.execute("DROP TRIGGER IF EXISTS check_vat_return_lock_line_trigger ON accounting_journalline;")
        cursor.execute("""
            CREATE TRIGGER check_vat_return_lock_line_trigger
            BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalline
            FOR EACH ROW
            EXECUTE FUNCTION check_vat_return_lock();
        """)


def revert_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS check_vat_return_lock_line_trigger ON accounting_journalline;")
        cursor.execute("DROP TRIGGER IF EXISTS check_vat_return_lock_trigger ON accounting_journal;")
        cursor.execute("""
            CREATE TRIGGER check_vat_return_lock_trigger
            BEFORE INSERT OR UPDATE ON accounting_journal
            FOR EACH ROW
            EXECUTE FUNCTION check_vat_return_lock();
        """)
        cursor.execute(ORIGINAL_VAT_LOCK_FN)
        cursor.execute(ORIGINAL_PERIOD_FN)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0007_vatreturn_hmrc_receipt_id_vatreturn_period_key_and_more'),
    ]

    operations = [
        migrations.RunPython(harden_triggers, revert_triggers),
    ]
