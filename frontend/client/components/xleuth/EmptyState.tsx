import { File } from "lucide-react";

export function EmptyState({
  title,
  caption,
}: {
  title: string;
  caption: string;
}) {
  return (
    <div className="flex flex-col items-center gap-4 px-10 py-20">
      <File className="h-6 w-6 text-muted-foreground" strokeWidth={1.4} />
      <div className="flex flex-col items-center gap-1">
        <span className="text-center text-sm font-medium tracking-[-0.16px] text-muted-foreground">
          {title}
        </span>
        <span className="text-center text-[10px] text-muted-foreground">
          {caption}
        </span>
      </div>
    </div>
  );
}
