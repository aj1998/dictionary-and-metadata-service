import { cn } from "@/lib/utils";
import { StatTile, type StatTileProps } from "@/components/StatTile";

export interface StatTileRowProps {
  tiles: [StatTileProps, StatTileProps, StatTileProps];
  className?: string;
}

export function StatTileRow({ tiles, className }: StatTileRowProps) {
  return (
    <div className={cn("flex gap-3", className)}>
      {tiles.map((tile, i) => (
        <StatTile key={i} {...tile} className="flex-1" />
      ))}
    </div>
  );
}
