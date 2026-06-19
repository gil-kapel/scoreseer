import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-9 w-72" />
      </div>
      <Skeleton className="h-96 w-full" />
    </div>
  );
}
