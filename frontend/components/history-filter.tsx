"use client";

import { useRouter } from "next/navigation";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function HistoryFilter({ value }: { value: string }) {
  const router = useRouter();
  return (
    <Tabs
      value={value}
      onValueChange={(v) => router.push(v === "all" ? "/history" : `/history?outcome=${v}`)}
    >
      <TabsList>
        <TabsTrigger value="all">All</TabsTrigger>
        <TabsTrigger value="hit">Outcome correct</TabsTrigger>
        <TabsTrigger value="miss">Outcome wrong</TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
