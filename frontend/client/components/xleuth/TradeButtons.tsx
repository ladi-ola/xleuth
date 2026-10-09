export function TradeButtons({
  onSell,
  onBuy,
}: {
  onSell: () => void;
  onBuy: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-16 z-20 mx-auto flex w-full max-w-md justify-center gap-3 bg-neutral-950 px-4 py-3">
      <button
        onClick={onSell}
        className="flex-1 rounded-xl border-[0.2px] border-destructive bg-destructive/10 px-4 py-3 text-base font-semibold text-destructive"
      >
        Sell
      </button>
      <button
        onClick={onBuy}
        className="flex-1 rounded-xl border-[0.2px] border-success bg-success/10 px-4 py-3 text-base font-semibold text-success"
      >
        Buy
      </button>
    </div>
  );
}
