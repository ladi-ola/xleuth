"""Xleuth off-chain matching engine (Week 5).

Price-time priority limit order books (one per basket_id) built on the
`order-matching` PyPI package, with margin pre-checks against on-chain
CollateralVault/PositionManager state and on-chain position settlement via
PositionManager.updatePosition (open / increase / flatten-close).
"""
