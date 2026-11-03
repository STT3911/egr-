import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { CompanyEgrEvent, CompanyProfile } from "@/lib/api";

type TimelineItem = {
  key: string;
  date?: string | null;
  title: string;
  detail?: string;
  source: string;
};

const sourceStyles: Record<string, string> = {
  ЕГР: "border-primary/25 bg-primary/10 text-primary",
  МАРТ: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  Лицензии: "border-violet-500/25 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  Банкротство: "border-red-500/25 bg-red-500/10 text-red-700 dark:text-red-300",
  ГИАС: "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  БелТПП: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  ЕАЭС: "border-cyan-500/25 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  Проверки: "border-orange-500/25 bg-orange-500/10 text-orange-700 dark:text-orange-300",
};

function normalizeEventDate(value?: string | null): string | undefined {
  const raw = value?.trim() ?? "";
  const dotted = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(raw);
  const iso = dotted
    ? `${dotted[3]}-${dotted[2].padStart(2, "0")}-${dotted[1].padStart(2, "0")}`
    : raw;
  const parts = /^(\d{4})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01])(?:T\d{2}:\d{2}.*)?)?)?$/.exec(iso);
  if (!parts || parts[1] === "0000") return undefined;
  const date = parts.slice(1).filter(Boolean).join("-");
  if (parts[3] && new Date(date).toISOString().slice(0, 10) !== date) return undefined;
  return date;
}

function formatDate(value?: string | null) {
  return value ? value.split("-").reverse().join(".") : "Дата события не указана";
}

function eventItems(profile: CompanyProfile): TimelineItem[] {
  const items: TimelineItem[] = [];
  const add = (item: Omit<TimelineItem, "key">, suffix: string) => {
    const date = normalizeEventDate(item.date);
    items.push({ ...item, date, key: `${item.source}-${date ?? "unknown"}-${suffix}-${items.length}` });
  };

  (profile.events ?? []).forEach((event: CompanyEgrEvent, index) => {
    const detail = [
      event.document_number && `Документ №${event.document_number}`,
      event.decision_authority,
      event.notes,
    ].filter(Boolean).join("\n");
    add({
      date: event.event_date,
      title: event.event_type || "Регистрационное событие",
      detail: detail || undefined,
      source: "ЕГР",
    }, `egr-${event.event_record_id ?? index}`);
  });

  profile.names?.filter(item => item.valid_from).forEach((item, index) => add({
    date: item.valid_from,
    title: "Начало действия наименования",
    detail: item.full_name_ru || item.short_name_ru,
    source: "ЕГР",
  }, `name-${index}`));

  profile.addresses?.filter(item => item.valid_from).forEach((item, index) => add({
    date: item.valid_from,
    title: "Начало действия адреса",
    detail: item.full_address,
    source: "ЕГР",
  }, `address-${index}`));

  profile.trade_registry_records?.forEach((item, index) => add({
    date: item.inclusion_date,
    title: "Запись в торговом реестре",
    detail: item.object_name || item.object_type || item.legal_name,
    source: "МАРТ",
  }, `trade-${item.registration_number ?? index}`));

  profile.license_records?.forEach((item, index) => add({
    date: item.activity_date_start,
    title: "Начало действия лицензии",
    detail: [item.generated_number, item.activity_type_name].filter(Boolean).join("\n") || undefined,
    source: "Лицензии",
  }, `license-${item.license_id}-${index}`));

  profile.inspection_plan_records?.forEach((item, index) => add({
    date: item.plan_year && item.start_month_no
      ? `${item.plan_year}-${String(item.start_month_no).padStart(2, "0")}`
      : item.plan_year?.toString(),
    title: "Плановая проверка",
    detail: [item.plan_title, item.controller_authority].filter(Boolean).join("\n") || undefined,
    source: "Проверки",
  }, `inspection-${item.plan_item_no ?? index}`));

  profile.bankrot_cases?.forEach((item, index) => add({
    date: item.start_date,
    title: "Дело о банкротстве",
    detail: [item.number, item.court].filter(Boolean).join("\n") || undefined,
    source: "Банкротство",
  }, `bankrot-${item.case_id}-${index}`));

  profile.gias_contracts?.forEach((item, index) => add({
    date: item.contract_date,
    title: "Контракт в ГИАС",
    detail: [item.title, item.state].filter(Boolean).join("\n") || undefined,
    source: "ГИАС",
  }, `gias-${item.contract_id}-${index}`));

  profile.belltpp_own_certificates?.forEach((item, index) => add({
    date: item.issue_date,
    title: "Сертификат БелТПП",
    detail: item.cert_number,
    source: "БелТПП",
  }, `belltpp-${item.cert_number}-${index}`));

  profile.eaeu_sez_resident_records?.forEach((item, index) => add({
    date: item.registry_entry_date,
    title: "Запись в реестре СЭЗ",
    detail: item.sez_name || item.project_name || item.full_name,
    source: "ЕАЭС",
  }, `sez-${item.item_id}-${index}`));

  return items
    .sort((left, right) => (right.date || "").localeCompare(left.date || ""));
}

export function CompanyEventTimeline({ profile, full = false }: { profile: CompanyProfile; full?: boolean }) {
  const [page, setPage] = useState(0);
  const items = eventItems(profile);
  const pageSize = full ? 20 : 6;
  const pageCount = Math.ceil(items.length / pageSize);
  const currentPage = Math.min(page, Math.max(0, pageCount - 1));

  return (
    <Card id="company-events" className="scroll-mt-24 overflow-hidden border-primary/20 bg-card/95 shadow-card" data-testid="company-event-timeline">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-primary/10 via-accent/8 to-transparent">
        <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
          Лента событий
          <Badge variant="outline" className="ml-auto border-primary/25 bg-primary/10 text-primary">
            {items.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 sm:p-6">
        {items.length ? (
          <div className="relative space-y-0">
            <div className="absolute bottom-3 left-[7px] top-3 w-px bg-border/70" aria-hidden="true" />
            {items.slice(currentPage * pageSize, (currentPage + 1) * pageSize).map((item) => {
              return (
                <div key={item.key} className="relative flex gap-3 pb-5 last:pb-0">
                  <div className="relative z-10 mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 border-primary/50 bg-card">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  </div>
                  <div className="min-w-0 flex-1 rounded-xl border border-border/60 bg-background/45 p-3">
                    <div className="flex flex-wrap items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-foreground">{item.title}</div>
                        {item.detail && <div className="mt-1 whitespace-pre-line break-words text-sm text-muted-foreground">{item.detail}</div>}
                      </div>
                      <div className="text-right text-xs text-muted-foreground">{formatDate(item.date)}</div>
                    </div>
                    <Badge variant="outline" className={`mt-2 ${sourceStyles[item.source] ?? "border-border/60 text-muted-foreground"}`}>
                      {item.source}
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-xl border border-dashed border-border/70 p-4 text-sm text-muted-foreground">
            Событий пока нет.
          </div>
        )}
        {!full && items.length > 0 && (
          <Link className="mt-4 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline"
            to={`/company/${profile.unp}/events`}>
            Все события
          </Link>
        )}
        {full && pageCount > 1 && (
          <nav aria-label="Страницы ленты" className="mt-4 flex flex-wrap items-center gap-3 text-sm">
            <button type="button" className="rounded-lg border px-3 py-2 disabled:opacity-40"
              disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Назад</button>
            <span aria-live="polite">{currentPage + 1} из {pageCount}</span>
            <button type="button" className="rounded-lg border px-3 py-2 disabled:opacity-40"
              disabled={currentPage + 1 === pageCount} onClick={() => setPage(currentPage + 1)}>Далее</button>
          </nav>
        )}
      </CardContent>
    </Card>
  );
}
