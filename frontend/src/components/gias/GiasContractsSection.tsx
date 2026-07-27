import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Building2,
  CalendarDays,
  FileClock,
  Handshake,
  ReceiptText,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CompanyGiasContract } from "@/lib/api";

type RoleFilter = "all" | "customer" | "provider";

const roleMeta = {
  customer: {
    label: "Заказчик",
    className:
      "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  provider: {
    label: "Поставщик",
    className:
      "border-violet-500/25 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
} as const;

const stateLabels: Record<string, string> = {
  ACTIVE: "Действует",
  ACCEPTED: "Принят",
  CANCELLED: "Отменён",
  COMPLETED: "Исполнен",
  CREATED: "Создан",
  REPOSTED: "Размещён",
  TERMINATED: "Расторгнут",
};

const currencyCodes: Record<string, string> = {
  "933": "BYN",
  BYN: "BYN",
  "840": "USD",
  USD: "USD",
  "978": "EUR",
  EUR: "EUR",
  "643": "RUB",
  RUB: "RUB",
};

const formatDate = (value?: string | null) => {
  if (!value) return "Дата не указана";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-BY", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
};

const formatAmount = (
  value?: number | string | null,
  currencyCode?: string | null
) => {
  if (value === null || value === undefined || value === "") return "Сумма не указана";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  const currency = currencyCodes[currencyCode || ""];
  if (currency) {
    return new Intl.NumberFormat("ru-BY", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  }
  return `${new Intl.NumberFormat("ru-BY", {
    maximumFractionDigits: 2,
  }).format(amount)}${currencyCode ? ` ${currencyCode}` : ""}`;
};

export const GiasContractsSection = ({
  contracts,
}: {
  contracts: CompanyGiasContract[];
}) => {
  const [role, setRole] = useState<RoleFilter>("all");
  const [query, setQuery] = useState("");

  const counts = useMemo(
    () => ({
      all: contracts.length,
      customer: contracts.filter((contract) => contract.role === "customer").length,
      provider: contracts.filter((contract) => contract.role === "provider").length,
    }),
    [contracts]
  );

  const visibleContracts = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    return contracts.filter((contract) => {
      if (role !== "all" && contract.role !== role) return false;
      if (!needle) return true;
      return [
        contract.title,
        contract.counterparty_name,
        contract.counterparty_unp,
        contract.registration_number,
        contract.contract_number,
      ].some((value) => String(value || "").toLocaleLowerCase("ru").includes(needle));
    });
  }, [contracts, query, role]);

  return (
    <Card
      id="gias-contracts"
      className="glass overflow-hidden border-cyan-500/25 shadow-card transition-all duration-300 hover:shadow-glow"
    >
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-cyan-500/10 via-primary/5 to-transparent p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-700 dark:text-cyan-300">
              <Handshake className="h-3.5 w-3.5" />
              Связи по УНП
            </div>
            <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
              <ReceiptText className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
              Договоры GIAS
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Государственные закупки, где компания выступает заказчиком или поставщиком
            </p>
          </div>
          <div className="rounded-xl border border-border/60 bg-background/65 px-3 py-2 text-sm">
            <span className="text-muted-foreground">Найдено </span>
            <span className="font-semibold text-foreground">{contracts.length}</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4 sm:p-6">
        {contracts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-background/45 px-5 py-10 text-center">
            <FileClock className="mx-auto h-8 w-8 text-muted-foreground/70" />
            <div className="mt-3 font-semibold text-foreground">Договоры пока не найдены</div>
            <p className="mx-auto mt-1 max-w-lg text-sm leading-relaxed text-muted-foreground">
              Первичная загрузка GIAS идёт постепенно. Новые связи появятся здесь
              автоматически после обработки сторон договора.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap gap-2" role="group" aria-label="Роль компании в договоре">
                {(
                  [
                    ["all", "Все"],
                    ["customer", "Как заказчик"],
                    ["provider", "Как поставщик"],
                  ] as const
                ).map(([value, label]) => (
                  <Button
                    key={value}
                    type="button"
                    size="sm"
                    variant={role === value ? "default" : "outline"}
                    onClick={() => setRole(value)}
                    aria-pressed={role === value}
                    className={role === value ? "" : "bg-background/55"}
                  >
                    {label}
                    <span className="ml-1 rounded-full bg-current/10 px-1.5 text-[11px]">
                      {counts[value]}
                    </span>
                  </Button>
                ))}
              </div>

              <label className="relative block w-full lg:max-w-xs">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <span className="sr-only">Поиск по договорам</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Номер, предмет, контрагент"
                  className="h-10 w-full rounded-xl border border-input bg-background/70 pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </label>
            </div>

            {visibleContracts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                По заданным условиям договоров нет.
              </div>
            ) : (
              <div className="space-y-3">
                {visibleContracts.map((contract) => {
                  const meta = roleMeta[contract.role];
                  const state = contract.state
                    ? stateLabels[contract.state] || contract.state
                    : "Статус не указан";
                  return (
                    <article
                      key={contract.contract_id}
                      className="group rounded-2xl border border-border/65 bg-background/55 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/35 hover:bg-card hover:shadow-soft"
                    >
                      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${meta.className}`}
                            >
                              {meta.label}
                            </span>
                            <span className="rounded-full border border-border/70 bg-card/70 px-2.5 py-1 text-xs text-muted-foreground">
                              {state}
                            </span>
                            {contract.detail_status !== "fetched" && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs text-amber-700 dark:text-amber-300">
                                <FileClock className="h-3 w-3" />
                                Детали загружаются
                              </span>
                            )}
                          </div>

                          <h3 className="mt-3 line-clamp-2 text-base font-semibold leading-snug text-foreground">
                            {contract.title || "Предмет договора не указан"}
                          </h3>

                          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                            <div className="flex min-w-0 items-start gap-2">
                              <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                              <div className="min-w-0">
                                <div className="text-xs text-muted-foreground">Контрагент</div>
                                <div className="truncate font-medium text-foreground">
                                  {contract.counterparty_name ||
                                    (contract.counterparty_unp
                                      ? `УНП ${contract.counterparty_unp}`
                                      : "Не указан")}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                              <div>
                                <div className="text-xs text-muted-foreground">Дата договора</div>
                                <div className="font-medium text-foreground">
                                  {formatDate(contract.contract_date)}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="flex shrink-0 flex-col gap-3 border-t border-border/50 pt-3 md:min-w-48 md:border-l md:border-t-0 md:pl-4 md:pt-0">
                          <div>
                            <div className="text-xs text-muted-foreground">Сумма</div>
                            <div className="mt-0.5 text-lg font-bold tabular-nums text-foreground">
                              {formatAmount(contract.price, contract.currency_code)}
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {contract.registration_number ||
                              contract.contract_number ||
                              "Номер не указан"}
                          </div>
                          <Button asChild size="sm" variant="outline" className="justify-between">
                            <Link to={`/contracts/${contract.contract_id}`}>
                              Открыть договор
                              <ArrowUpRight className="h-4 w-4" />
                            </Link>
                          </Button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}

            {contracts.length >= 100 && (
              <p className="text-xs leading-relaxed text-muted-foreground">
                В досье показаны 100 последних договоров. Полный реестр доступен через API GIAS.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
};
