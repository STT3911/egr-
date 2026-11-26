import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCompanyEvents, type CompanyEventSource, type CompanyTimelineEvent } from "@/lib/api";

export const eventSources: Record<CompanyEventSource, string> = {
  egr: "ЕГР",
  mart: "Торговый реестр",
  license: "Лицензии",
  inspection: "Плановые проверки",
  bankrot: "Банкротство",
  gias: "ГИАС",
  belltpp: "БелТПП",
  sez: "ЕАЭС",
  pvt: "ПВТ",
};

function formatEventDate(date: string) {
  return date.split("-").reverse().join(".");
}

type TimelineProps = {
  unp: string;
  items: CompanyTimelineEvent[];
  preview?: boolean;
  empty?: string;
  footer?: ReactNode;
};

export function CompanyEventTimeline({ unp, items, preview, empty = "Событий пока нет.", footer }: TimelineProps) {
  return (
    <Card id="company-events" className="scroll-mt-24 overflow-hidden border-primary/20 bg-card/95 shadow-card" data-testid="company-event-timeline">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-primary/10 via-accent/8 to-transparent">
        <CardTitle className="text-lg sm:text-xl">Лента событий</CardTitle>
      </CardHeader>
      <CardContent className="p-4 sm:p-6">
        {items.length ? (
          <ol className="relative space-y-0 before:absolute before:bottom-3 before:left-[7px] before:top-3 before:w-px before:bg-border/70">
            {items.map((item) => (
              <li key={item.id} className="relative flex gap-3 pb-4 last:pb-0">
                <span className="relative mt-1.5 h-4 w-4 shrink-0 rounded-full border-2 border-primary/50 bg-card" aria-hidden="true" />
                <div className="min-w-0 flex-1 rounded-xl border border-border/60 bg-background/45 p-3 sm:p-4">
                  <div className="flex flex-col-reverse gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                    <h3 className="break-words font-medium text-foreground">{item.title}</h3>
                    {item.date ? (
                      <time dateTime={item.date} className="shrink-0 text-sm tabular-nums text-muted-foreground">
                        {formatEventDate(item.date)}
                      </time>
                    ) : (
                      <span className="shrink-0 text-sm text-muted-foreground">
                        {item.source === "pvt" ? "Дата вступления не указана" : "Дата не указана"}
                      </span>
                    )}
                  </div>
                  {item.details.map((detail, index) => (
                    <p key={index} className="mt-1 whitespace-pre-line break-words text-sm text-muted-foreground">{detail}</p>
                  ))}
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                    <Badge variant="outline" className="gap-1.5 border-primary/30 bg-primary/10">
                      {item.source === "egr" && <Landmark className="h-3.5 w-3.5 text-primary" aria-hidden="true" />}
                      {eventSources[item.source]}
                    </Badge>
                    {item.contract_id && (
                      <Link to={`/contracts/${item.contract_id}?fromUnp=${unp}`} className="font-medium text-primary underline-offset-4 hover:underline">
                        Открыть договор
                      </Link>
                    )}
                    {item.source_url && (
                      <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline-offset-4 hover:underline">
                        Открыть источник
                      </a>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        ) : <p className="text-sm text-muted-foreground">{empty}</p>}
        {preview && items.length > 0 && (
          <Link className="mt-4 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline" to={`/company/${unp}/events`}>
            Все события
          </Link>
        )}
        {footer}
      </CardContent>
    </Card>
  );
}

export function CompanyEventPreview({ unp }: { unp: string }) {
  const timeline = useQuery({
    queryKey: ["company-events", unp, "preview"],
    queryFn: ({ signal }) => getCompanyEvents(unp, { limit: 6 }, signal),
    retry: false,
  });

  return (
    <CompanyEventTimeline
      unp={unp}
      items={timeline.data?.items ?? []}
      preview
      empty={timeline.isPending ? "Загружаем события…" : timeline.isError ? "Не удалось загрузить события." : undefined}
      footer={timeline.isError && (
        <button type="button" className="mt-3 text-sm text-primary hover:underline" onClick={() => void timeline.refetch()}>
          Повторить
        </button>
      )}
    />
  );
}
