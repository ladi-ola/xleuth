"""Xleuth oracle-service: reads live basket index prices from
data-ingestion's stream/DB, signs them as EIP-712 PriceUpdate messages, and
pushes them to IndexOracleConsumer on Polygon Amoy.
"""