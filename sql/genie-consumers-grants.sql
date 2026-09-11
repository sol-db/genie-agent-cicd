-- UC read access for the Genie One audience.
-- Sharing an agent (the bundle `permissions` block) does NOT grant its data —
-- without these, analysts see the agent but get empty / permission-denied answers.
--
-- Scope these grants to the PRODUCTION / gold tables promoted agents read.
-- Keeping them off raw/dev tables is a useful backstop: a draft agent that a
-- developer shares out-of-band still returns nothing if it reads tables the
-- consumer group can't SELECT. Run once per catalog/schema, not per agent.
-- Row filters / column masks already on these tables still apply per user.

GRANT USE CATALOG ON CATALOG main                     TO `genie-consumers`;
GRANT USE SCHEMA  ON SCHEMA  main.monetization         TO `genie-consumers`;
GRANT SELECT      ON TABLE   main.monetization.gold_daily_revenue    TO `genie-consumers`;
GRANT SELECT      ON TABLE   main.monetization.gold_iap_transactions TO `genie-consumers`;
