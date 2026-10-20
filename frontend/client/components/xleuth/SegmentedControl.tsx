import { cn } from "@/lib/utils";

export interface SegmentedControlOption<T extends string> {
  value: T;
  label: string;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: SegmentedControlOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-10 items-center justify-between gap-0.5 rounded-xl border-[0.4px] border-border bg-card p-0.5",
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "flex-1 self-stretch rounded-[10px] px-3 py-1 text-[10px] font-medium",
            value === option.value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
