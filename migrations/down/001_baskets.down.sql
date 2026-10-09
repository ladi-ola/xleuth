-- Rollback for 001_baskets.sql. Drops audit table first (FK), then baskets.
DROP TABLE IF EXISTS basket_events;
DROP TABLE IF EXISTS baskets;
