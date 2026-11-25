import type { FormEvent } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CompanyEventTimeline, eventSources } from "@/components/CompanyEventTimeline";
import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";
import { getCompanyEvents } from "@/lib/api";

const filterClass = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

export default function CompanyEvents() {
  const { unp = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const source = params.get("source") || undefined;
  const date_from = params.get("date_from") || undefined;
  const date_to = params.get("date_to") || undefined;
  const filtered = Boolean(source || date_from || date_to);
  const filterKey = JSON.stringify([unp, source, date_from, date_to]);
  const timeline = useInfiniteQuery({
    queryKey: ["company-events", unp, source, date_from, date_to],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getCompanyEvents(unp, {
      limit: 20, source, date_from, date_to, cursor: pageParam,
    }, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
  });

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const from = String(values.get("date_from") ?? "");
    const to = String(values.get("date_to") ?? "");
    const endDate = form.elements.namedItem("date_to") as HTMLInputElement;
    endDate.setCustomValidity(from && to && from > to ? "Выберите дату окончания после даты начала." : "");
    if (!form.reportValidity()) return;

    const next = new URLSearchParams();
    for (const field of ["source", "date_from", "date_to"]) {
      const value = String(values.get(field) ?? "");
      if (value) next.set(field, value);
    }
    setParams(next);
  }

  const items = timeline.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28">
      <Header />
      <main className="mx-auto max-w-4xl space-y-5">
        <Link to={`/company/${unp}`} className="text-sm font-medium text-primary hover:underline">
          Назад к карточке
        </Link>
        <h1 className="break-words text-2xl font-semibold">
          {timeline.data?.pages[0]?.company_name || `УНП ${unp}`}
        </h1>
        <form key={filterKey} onSubmit={applyFilters} aria-label="Фильтры событий"
          onChange={(event) => (event.currentTarget.elements.namedItem("date_to") as HTMLInputElement).setCustomValidity("")}
          className="grid gap-3 rounded-xl border border-border/70 bg-card p-4 sm:grid-cols-3">
          <label className="space-y-1 text-sm font-medium">
            <span>Источник</span>
            <select name="source" defaultValue={source ?? ""} className={filterClass}>
              <option value="">Все источники</option>
              {Object.entries(eventSources).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium">
            <span>Дата с</span>
            <input type="date" name="date_from" defaultValue={date_from} className={filterClass} />
          </label>
          <label className="space-y-1 text-sm font-medium">
            <span>Дата по</span>
            <input type="date" name="date_to" defaultValue={date_to} className={filterClass} />
          </label>
          <div className="flex flex-wrap gap-2 sm:col-span-3">
            <Button type="submit" size="sm">Применить</Button>
            {filtered && <Button type="button" variant="outline" size="sm" onClick={() => setParams({})}>Сбросить</Button>}
          </div>
        </form>
        {timeline.isPending && <p role="status">Загружаем события…</p>}
        {timeline.isError && !timeline.data && (
          <div role="alert" className="space-y-2">
            <p>Не удалось загрузить события.</p>
            <Button type="button" variant="outline" onClick={() => void timeline.refetch()}>Повторить</Button>
          </div>
        )}
        {timeline.data && <CompanyEventTimeline unp={unp} items={items}
          empty={filtered ? "За выбранный период и источник событий нет." : undefined}
          footer={timeline.hasNextPage && (
            <div className="mt-4">
              {timeline.isFetchNextPageError && <p role="alert" className="mb-2 text-sm">Не удалось загрузить следующую страницу.</p>}
              <Button type="button" variant="outline" disabled={timeline.isFetchingNextPage} onClick={() => void timeline.fetchNextPage()}>
                {timeline.isFetchingNextPage ? "Загружаем…" : timeline.isFetchNextPageError ? "Повторить" : "Показать ещё"}
              </Button>
            </div>
          )}
        />}
      </main>
    </div>
  );
}
