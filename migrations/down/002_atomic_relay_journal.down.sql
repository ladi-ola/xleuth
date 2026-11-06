-- Only for disposable test databases after ALL pending transactions are
-- reconciled. Never drop this table on a hosted deployment without approval.
DROP TABLE IF EXISTS atomic_relay_journal;
