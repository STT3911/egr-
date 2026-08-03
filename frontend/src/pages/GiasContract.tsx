import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  ExternalLink,
  FileClock,
  FileText,
  Landmark,
  Loader2,
  Package,
  ReceiptText,
  RefreshCw,
  ShoppingCart,
  WalletCards,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getGiasContract, type GiasContractDetail } from "@/lib/api";

type UnknownRecord = Record<string, unknown>;

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

const asRecord = (value: unknown): UnknownRecord =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};

const asRecords = (value: unknown): UnknownRecord[] =>
  Array.isArray(value) ? value.map(asRecord) : [];

const asText = (value: unknown) =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

const safeExternalUrl = (value: unknown) => {
  const url = asText(value);
  return /^https?:\/\//i.test(url) ? url : "";
};

const formatDate = (value?: string | number | null, includeTime = false) => {
  if (value === null || value === undefined || value === "") return "—";
  let normalized: string | number = value;
  if (typeof normalized === "number" && normalized < 10_000_000_000) {
    normalized *= 1000;
  }
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ru-BY", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
};

const formatAmount = (
  value?: number | string | null,
  currencyCode?: string | null
) => {
  if (value === null || value === undefined || value === "") return "—";
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

const formatQuantity = (value?: number | string | null) => {
  if (value === null || value === undefined || value === "") return "—";
  const quantity = Number(value);
  if (!Number.isFinite(quantity)) return String(value);
  return new Intl.NumberFormat("ru-BY", {
    maximumFractionDigits: 6,
  }).format(quantity);
};

const SummaryItem = ({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) => (
  <div className="rounded-xl border border-border/60 bg-background/60 p-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="mt-1 break-words text-sm font-semibold text-foreground">
      {value === null || value === undefined || value === "" ? "—" : value}
    </div>
  </div>
);

const PartyCard = ({
  title,
  name,
  unp,
  address,
  tone,
}: {
  title: string;
  name?: string | null;
  unp?: number | null;
  address?: string | null;
  tone: "cyan" | "violet";
}) => {
  const colorClass =
    tone === "cyan"
      ? "border-cyan-500/25 bg-cyan-500/5"
      : "border-violet-500/25 bg-violet-500/5";
  const iconClass =
    tone === "cyan"
      ? "text-cyan-600 dark:text-cyan-400"
      : "text-violet-600 dark:text-violet-400";

  return (
    <div className={`rounded-2xl border p-4 sm:p-5 ${colorClass}`}>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        <Building2 className={`h-4 w-4 ${iconClass}`} />
        {title}
      </div>
      <div className="mt-3 text-base font-semibold leading-snug text-foreground">
        {name || "Наименование не указано"}
      </div>
      {unp ? (
        <Link
          to={`/company/${unp}`}
          className={`mt-2 inline-flex items-center gap-1 text-sm font-medium ${iconClass} hover:underline`}
        >
          УНП {unp}
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      ) : (
        <div className="mt-2 text-sm text-muted-foreground">УНП не указан</div>
      )}
      {address && <div className="mt-3 text-sm leading-relaxed text-muted-foreground">{address}</div>}
    </div>
  );
};

const GiasContract = () => {
  const { contractId } = useParams();
  const [searchParams] = useSearchParams();
  const [contract, setContract] = useState<GiasContractDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadContract = useCallback(async () => {
    if (!contractId) return;
    setLoading(true);
    setError(null);
    try {
      setContract(await getGiasContract(contractId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить договор");
    } finally {
      setLoading(false);
    }
  }, [contractId]);

  useEffect(() => {
    void loadContract();
  }, [loadContract]);

  const raw = contract?.raw_detail || {};
  const documents = asRecords(raw.contractDocuments);
  const payments = asRecords(raw.payments);
  const accounts = contract?.accounts || [];
  const purchases = asRecords(raw.purchases);
  const sourceUnp = searchParams.get("fromUnp");
  const returnUnp = sourceUnp && /^\d{9}$/.test(sourceUnp) ? sourceUnp : null;
  const returnPath = returnUnp
    ? `/company/${returnUnp}`
    : contract?.customer_unp
      ? `/company/${contract.customer_unp}`
      : "/";

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background px-4">
        <div className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card/90 px-5 py-4 shadow-card">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="font-medium">Загружаем договор GIAS…</span>
        </div>
      </div>
    );
  }

  if (error || !contract) {
    return (
      <div className="grid min-h-screen place-items-center bg-background px-4">
        <Card className="glass w-full max-w-lg border-destructive/30 text-center shadow-card">
          <CardContent className="p-6 sm:p-8">
            <FileText className="mx-auto h-9 w-9 text-destructive" />
            <h1 className="mt-4 text-xl font-bold">Договор не загрузился</h1>
            <p className="mt-2 text-sm text-muted-foreground">{error || "Договор не найден"}</p>
            <div className="mt-5 flex flex-col justify-center gap-2 sm:flex-row">
              <Button type="button" onClick={() => void loadContract()}>
                <RefreshCw className="h-4 w-4" />
                Повторить
              </Button>
              <Button asChild variant="outline">
                <Link to={returnPath}>
                  <ArrowLeft className="h-4 w-4" />
                  {returnUnp ? "К досье компании" : "На главную"}
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const state = contract.state
    ? stateLabels[contract.state] || contract.state
    : "Статус не указан";
  const title =
    contract.registration_number ||
    contract.contract_number ||
    `Договор ${contract.contract_id.slice(0, 8)}`;

  return (
    <div className="relative min-h-screen overflow-hidden bg-background px-4 pb-14 pt-8 sm:pt-12">
      <div className="registry-grid pointer-events-none absolute inset-0 opacity-35" />
      <div className="ambient-orb-primary pointer-events-none absolute -right-28 top-10 h-80 w-80 opacity-50" />
      <div className="ambient-orb-accent pointer-events-none absolute -left-24 top-[36rem] h-72 w-72 opacity-35" />

      <main className="relative z-10 mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button asChild variant="outline" className="glass">
            <Link to={returnPath}>
              <ArrowLeft className="h-4 w-4" />
              {returnUnp
                ? "К досье компании"
                : contract.customer_unp
                  ? "К досье заказчика"
                  : "На главную"}
            </Link>
          </Button>
          <span className="rounded-full border border-border/70 bg-card/80 px-3 py-1.5 font-mono text-xs text-muted-foreground">
            GIAS · {contract.contract_id}
          </span>
        </div>

        <section className="relative overflow-hidden rounded-3xl border border-primary/20 bg-card/95 p-5 shadow-card sm:p-7">
          <div className="registry-grid pointer-events-none absolute inset-0 opacity-25" />
          <div className="relative">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                    <ReceiptText className="h-3.5 w-3.5" />
                    Договор GIAS
                  </span>
                  <span className="rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs text-muted-foreground">
                    {state}
                  </span>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      contract.detail_status === "fetched"
                        ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : contract.detail_status === "error"
                          ? "bg-red-500/10 text-red-700 dark:text-red-300"
                          : "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                    }`}
                  >
                    {contract.detail_status === "fetched"
                      ? "Полная карточка"
                      : contract.detail_status === "error"
                        ? "Ошибка деталей"
                        : "Детали загружаются"}
                  </span>
                </div>
                <h1 className="mt-4 text-2xl font-bold leading-tight text-foreground sm:text-3xl">
                  {title}
                </h1>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
                  {contract.title || "Предмет договора не указан"}
                </p>
              </div>
              <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 lg:min-w-64">
                <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                  Цена договора
                </div>
                <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">
                  {formatAmount(contract.price, contract.currency_code)}
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryItem label="Дата договора" value={formatDate(contract.contract_date)} />
              <SummaryItem label="Срок исполнения" value={formatDate(contract.execution_term)} />
              <SummaryItem label="Регистрационный номер" value={contract.registration_number} />
              <SummaryItem label="Номер плана" value={contract.plan_number} />
            </div>
          </div>
        </section>

        {contract.detail_status !== "fetched" && (
          <div
            className={`rounded-2xl border p-4 ${
              contract.detail_status === "error"
                ? "border-red-500/25 bg-red-500/5"
                : "border-amber-500/25 bg-amber-500/5"
            }`}
          >
            <div className="flex items-start gap-3">
              <FileClock className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
              <div>
                <div className="font-semibold text-foreground">
                  {contract.detail_status === "error"
                    ? "Полную карточку пока получить не удалось"
                    : "Полная карточка находится в очереди загрузки"}
                </div>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  Основные данные договора уже доступны. Позиции, документы и платежи
                  появятся автоматически после следующей успешной синхронизации.
                </p>
              </div>
            </div>
          </div>
        )}

        <section className="grid gap-4 lg:grid-cols-2">
          <PartyCard
            title="Заказчик"
            name={contract.customer_name}
            unp={contract.customer_unp}
            address={contract.customer_location}
            tone="cyan"
          />
          <PartyCard
            title="Поставщик"
            name={contract.provider_name}
            unp={contract.provider_unp}
            address={contract.provider_address}
            tone="violet"
          />
        </section>

        <Card className="glass border-primary/20 shadow-card">
          <CardHeader className="border-b border-border/60 bg-gradient-to-r from-primary/10 to-transparent">
            <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
              <Package className="h-5 w-5 text-primary" />
              Позиции договора
              <span className="ml-auto rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                {contract.positions.length}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {contract.positions.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                Позиции ещё не загружены.
              </div>
            ) : (
              <div className="space-y-3">
                {contract.positions.map((position) => (
                  <article
                    key={position.id}
                    className="rounded-2xl border border-border/65 bg-background/55 p-4"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap gap-2 text-xs">
                          {position.lot_number !== null && position.lot_number !== undefined && (
                            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">
                              Лот № {position.lot_number}
                            </span>
                          )}
                          {position.okpb_code && (
                            <span className="rounded-full border border-border/70 bg-card px-2.5 py-1 font-mono text-muted-foreground">
                              ОКРБ {position.okpb_code}
                            </span>
                          )}
                          {position.is_smp && (
                            <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-emerald-700 dark:text-emerald-300">
                              СМП
                            </span>
                          )}
                        </div>
                        <h3 className="mt-3 font-semibold leading-snug text-foreground">
                          {position.title || position.lot_title || "Позиция без наименования"}
                        </h3>
                        {position.okpb_name && (
                          <p className="mt-1 text-sm text-muted-foreground">{position.okpb_name}</p>
                        )}
                        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
                          <span>
                            Количество:{" "}
                            <strong className="font-semibold text-foreground">
                              {formatQuantity(position.volume)}{" "}
                              {position.unit_symbol || position.unit_name || ""}
                            </strong>
                          </span>
                          {position.country_names && position.country_names.length > 0 && (
                            <span>Страна: {position.country_names.join(", ")}</span>
                          )}
                        </div>
                      </div>
                      <div className="grid shrink-0 grid-cols-2 gap-2 border-t border-border/50 pt-3 lg:min-w-72 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                        <SummaryItem
                          label="Цена за единицу"
                          value={formatAmount(position.unit_price, contract.currency_code)}
                        />
                        <SummaryItem
                          label="Стоимость"
                          value={formatAmount(position.position_price, contract.currency_code)}
                        />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {(payments.length > 0 || accounts.length > 0) && (
          <section className="grid gap-4 lg:grid-cols-2">
            {payments.length > 0 && (
              <Card className="glass border-emerald-500/20 shadow-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <WalletCards className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                    График платежей
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {payments.map((payment, index) => (
                    <div
                      key={`${asText(payment.date)}-${index}`}
                      className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-background/55 p-3"
                    >
                      <div>
                        <div className="text-xs text-muted-foreground">Дата платежа</div>
                        <div className="mt-1 text-sm font-medium text-foreground">
                          {formatDate(
                            typeof payment.date === "number" || typeof payment.date === "string"
                              ? payment.date
                              : null
                          )}
                        </div>
                      </div>
                      <div className="text-right font-bold tabular-nums text-foreground">
                        {formatAmount(
                          typeof payment.sum === "number" || typeof payment.sum === "string"
                            ? payment.sum
                            : null,
                          contract.currency_code
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {accounts.length > 0 && (
              <Card className="glass border-sky-500/20 shadow-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Landmark className="h-5 w-5 text-sky-600 dark:text-sky-400" />
                    Банковские реквизиты
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {accounts.map((account, index) => (
                    <div
                      key={`${account.id}-${index}`}
                      className="rounded-xl border border-border/60 bg-background/55 p-3"
                    >
                      <div className="break-all font-mono text-sm font-semibold text-foreground">
                        {account.account_number || "Счёт не указан"}
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">
                        {account.bank_name || "Банк не указан"}
                      </div>
                      {account.bank_code && (
                        <div className="mt-1 font-mono text-xs text-muted-foreground">
                          БИК {account.bank_code}
                        </div>
                      )}
                      {(account.currency_name || account.currency_code) && (
                        <div className="mt-1 text-xs text-muted-foreground">
                          Валюта: {account.currency_name || account.currency_code}
                        </div>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </section>
        )}

        {(documents.length > 0 || purchases.length > 0) && (
          <section className="grid gap-4 lg:grid-cols-2">
            {documents.length > 0 && (
              <Card className="glass border-orange-500/20 shadow-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FileText className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                    Документы
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {documents.map((document, index) => {
                    const link = asRecord(document.link);
                    const url = safeExternalUrl(link.link);
                    const signatures = asRecords(link.signatureLinks);
                    const signerCount = signatures.reduce(
                      (total, signature) => total + asRecords(signature.signers).length,
                      0
                    );
                    return (
                      <div
                        key={`${asText(link.name)}-${index}`}
                        className="rounded-xl border border-border/60 bg-background/55 p-3"
                      >
                        <div className="break-words text-sm font-semibold text-foreground">
                          {asText(link.name) || `Документ ${index + 1}`}
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          {signerCount > 0 && (
                            <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-700 dark:text-emerald-300">
                              Подписантов: {signerCount}
                            </span>
                          )}
                          {url && (
                            <Button asChild size="sm" variant="outline">
                              <a href={url} target="_blank" rel="noreferrer">
                                Скачать
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}

            {purchases.length > 0 && (
              <Card className="glass border-violet-500/20 shadow-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <ShoppingCart className="h-5 w-5 text-violet-600 dark:text-violet-400" />
                    Связанные закупки
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {purchases.map((purchase, index) => {
                    const url = safeExternalUrl(purchase.auctionUrl);
                    return (
                      <div
                        key={`${asText(purchase.uuid)}-${index}`}
                        className="rounded-xl border border-border/60 bg-background/55 p-3"
                      >
                        <div className="text-sm font-semibold text-foreground">
                          {asText(purchase.tenderFormName) || "Закупка"}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          № {asText(purchase.publicPurchaseNumber) || asText(purchase.etpId) || "—"}
                          {purchase.requestDate !== undefined
                            ? ` · ${formatDate(
                                typeof purchase.requestDate === "number" ||
                                  typeof purchase.requestDate === "string"
                                  ? purchase.requestDate
                                  : null
                              )}`
                            : ""}
                        </div>
                        {url && (
                          <Button asChild size="sm" variant="outline" className="mt-3">
                            <a href={url} target="_blank" rel="noreferrer">
                              Открыть закупку
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </section>
        )}

        <Card className="glass border-border/70">
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-4">
            <SummaryItem
              label="Срок исполнения договора"
              value={formatDate(contract.real_execution_term)}
            />
            <SummaryItem
              label="Дата расторжения"
              value={formatDate(contract.termination_execution_term)}
            />
            <SummaryItem label="Тип договора" value={contract.contract_type} />
            <SummaryItem
              label="Дата подписания договора"
              value={formatDate(contract.contract_date)}
            />
            {contract.termination_reason && (
              <div className="sm:col-span-2 lg:col-span-4">
                <SummaryItem label="Причина расторжения" value={contract.termination_reason} />
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default GiasContract;
