import { useState } from "react";
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  ExternalLink,
  FileText,
  Gavel,
  Mail,
  MapPin,
  Phone,
  UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { BankrotCaseDataset } from "@/lib/api";
import { getBankrotPayloadCount } from "@/lib/bankrotData";

type JsonObject = Record<string, unknown>;

const datasetLabels: Record<string, string> = {
  publications: "Публикации и сообщения",
  properties: "Имущество",
  property_reports: "Отчёты об имуществе",
  property_valuations: "Оценка имущества",
  sales: "Продажа имущества и торги",
  creditor_meetings: "Собрания кредиторов",
  creditor_committees: "Комитеты кредиторов",
  creditor_requirements: "Требования кредиторов",
  property_write_off: "Списание имущества",
  transfer_remaining_properties: "Передача оставшегося имущества",
  transfer_unsold_properties: "Передача непроданного имущества",
  readjustments: "Корректировки планов и отчётов",
  fund_balance_reports: "Движение денежных средств",
  debtor_bank_accounts: "Банковские счета должника",
  debtor_online_wallets: "Электронные кошельки должника",
  manager_full_info: "Сведения об управляющем",
  manager_accreditation: "Аккредитация управляющего",
  manager_documents: "Документы управляющего",
  manager_education: "Образование управляющего",
  manager_debtors: "Другие дела управляющего",
  manager_bank_accounts: "Банковские счета управляющего",
  manager_online_wallets: "Электронные кошельки управляющего",
};

const fieldLabels: Record<string, string> = {
  id: "Идентификатор",
  caseId: "Идентификатор дела",
  number: "Номер",
  debtorFileNumber: "Номер дела должника",
  name: "Наименование",
  value: "Значение",
  fullName: "Полное наименование",
  shortName: "Краткое наименование",
  unp: "УНП",
  status: "Статус",
  type: "Тип",
  category: "Категория",
  description: "Описание",
  info: "Содержание",
  additionalInfo: "Дополнительная информация",
  startDate: "Дата начала",
  endDate: "Дата окончания",
  date: "Дата",
  dateReg: "Дата регистрации",
  dateStart: "Дата начала деятельности",
  dateExclusion: "Дата исключения",
  exclusionDate: "Дата исключения",
  published: "Дата публикации",
  dateOfEvent: "Дата события",
  createDate: "Дата создания",
  procedureType: "Вид процедуры",
  proceduresHistory: "Ход процедуры",
  protectivePeriod: "Защитный период",
  sanitation: "Санация",
  liquidation: "Ликвидационное производство",
  proceedings: "Производство",
  courtDecision: "Решение суда",
  procedureStopDate: "Дата приостановления",
  procedureRestartDate: "Дата возобновления",
  procedureEndDate: "Дата завершения",
  procedureEndDateUpdated: "Уточнённая дата завершения",
  procedureEndDateUpdatedList: "История изменения срока",
  procedureStopReason: "Причина приостановления",
  debtorModel: "Должник",
  debtor: "Должник",
  manager: "Антикризисный управляющий",
  managerModel: "Антикризисный управляющий",
  declarant: "Заявитель",
  organization: "Организация",
  legalAddress: "Юридический адрес",
  actualAddress: "Фактический адрес",
  correspondenceAddress: "Адрес для корреспонденции",
  contacts: "Контакты",
  court: "Суд",
  judge: "Судья",
  rate: "Рейтинг",
  isActive: "Действующий",
  isNew: "Новая запись",
  closeReason: "Причина завершения",
  bankAccountsComment: "Комментарий по банковским счетам",
  onlineWalletComment: "Комментарий по электронным кошелькам",
  termForPresentationCreditorsClaims: "Срок предъявления требований кредиторов",
  lastJudgmentId: "Последнее судебное решение",
  document: "Документ",
  documents: "Документы",
  fileName: "Имя файла",
  fileId: "Идентификатор файла",
  documentPlace: "Раздел документа",
  groupName: "Группа",
  judgments: "Судебные решения",
  directory: "Вид судебного решения",
  message: "Публикация",
  messageType: "Тип сообщения",
  title: "Заголовок",
  subject: "Предмет",
  amount: "Сумма",
  totalAmount: "Общая сумма",
  currency: "Валюта",
  balanceCost: "Балансовая стоимость",
  estimatedCost: "Оценочная стоимость",
  startPrice: "Начальная цена",
  salePrice: "Цена продажи",
  property: "Имущество",
  properties: "Имущество",
  propertyReports: "Отчёты",
  propertyValuations: "Оценки",
  sales: "Торги",
  meetings: "Собрания",
  committees: "Комитеты",
  requirementsResults: "Требования",
  propertiesWriteOff: "Списанное имущество",
  transferredUnsoldProperty: "Переданное непроданное имущество",
  items: "Записи",
  messages: "Сообщения",
  count: "Количество",
  totalCount: "Всего записей",
  creditor: "Кредитор",
  creditorName: "Кредитор",
  meetingDate: "Дата собрания",
  place: "Место проведения",
  address: "Адрес",
  agenda: "Повестка",
  protocol: "Протокол",
  bankName: "Банк",
  bankAccount: "Банковский счёт",
  accountNumber: "Номер счёта",
  bic: "БИК",
  walletNumber: "Номер кошелька",
  paymentSystem: "Платёжная система",
  accreditation: "Аккредитация",
  education: "Образование",
  institution: "Учебное заведение",
  specialty: "Специальность",
  qualification: "Квалификация",
  certificateNumber: "Номер свидетельства",
  issueDate: "Дата выдачи",
  validFrom: "Действует с",
  validTo: "Действует до",
  stateOwnership: "Доля государственной собственности",
  idKindOfActivity: "Вид деятельности",
  postalIndex: "Почтовый индекс",
  country: "Страна",
  region: "Регион",
  area: "Район",
  locality: "Населённый пункт",
  localityType: "Тип населённого пункта",
  street: "Улица и дом",
};

const rootCaseFields = new Set(["id", "number", "startDate", "endDate", "status", "court", "judge"]);

const isObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isEmpty = (value: unknown): boolean => {
  if (value == null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (isObject(value)) return Object.values(value).every(isEmpty);
  return false;
};

const mergeObjects = (fallback: unknown, primary: unknown): unknown => {
  if (!isObject(fallback) || !isObject(primary)) return isEmpty(primary) ? fallback : primary;
  const result: JsonObject = { ...fallback };
  Object.entries(primary).forEach(([key, value]) => {
    result[key] = key in result ? mergeObjects(result[key], value) : value;
  });
  return result;
};

const stripHtml = (value: string) =>
  value
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&quot;/gi, '"')
    .replace(/&amp;/gi, "&")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const labelFor = (key: string) => {
  if (fieldLabels[key]) return fieldLabels[key];
  const words = key
    .replace(/_/g, " ")
    .replace(/([a-zа-яё])([A-ZА-ЯЁ])/g, "$1 $2")
    .trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
};

const isDateKey = (key: string) => /date|published|validFrom|validTo/i.test(key);

const formatDate = (value: string) => {
  if (value.startsWith("0001-01-01")) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const hasTime = value.includes("T") && !value.endsWith("T00:00:00");
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(hasTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
};

const formatAddress = (value: JsonObject) =>
  [
    value.postalIndex,
    [value.localityType, value.locality].filter(Boolean).join(" "),
    value.area,
    value.street,
  ]
    .filter(Boolean)
    .join(", ");

const looksLikeAddress = (value: JsonObject) =>
  "street" in value && ("locality" in value || "postalIndex" in value);

const renderPrimitive = (value: string | number | boolean, fieldKey: string) => {
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number") return value.toLocaleString("ru-RU");
  const cleaned = stripHtml(value);
  if (isDateKey(fieldKey)) return formatDate(cleaned) || "—";
  if (/^https?:\/\//i.test(cleaned)) {
    return (
      <a href={cleaned} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
        Открыть ссылку <ExternalLink className="h-3.5 w-3.5" />
      </a>
    );
  }
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleaned)) {
    return <a href={`mailto:${cleaned}`} className="text-primary hover:underline">{cleaned}</a>;
  }
  if (/^(?:\+?\d[\d\s()/-]{5,})$/.test(cleaned)) {
    return <a href={`tel:${cleaned.replace(/[^+\d]/g, "")}`} className="text-primary hover:underline">{cleaned}</a>;
  }
  return <span className="whitespace-pre-wrap break-words">{cleaned}</span>;
};

const ScalarField = ({ fieldKey, value }: { fieldKey: string; value: string | number | boolean }) => (
  <div className="min-w-0 rounded-lg border border-border/50 bg-background/50 p-3">
    <div className="mb-1 text-xs text-muted-foreground">{labelFor(fieldKey)}</div>
    <div className="text-sm font-medium leading-relaxed text-foreground">
      {renderPrimitive(value, fieldKey)}
    </div>
  </div>
);

const ContactValue = ({ value }: { value: JsonObject }) => {
  const contact = String(value.value || "");
  const type = Number(value.type);
  const Icon = type === 2 || contact.includes("@") ? Mail : Phone;
  const href = type === 2 || contact.includes("@")
    ? `mailto:${contact}`
    : `tel:${contact.replace(/[^+\d]/g, "")}`;
  return (
    <a href={href} className="flex items-center gap-2 rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-sm text-primary hover:bg-primary/5">
      <Icon className="h-4 w-4 flex-shrink-0" />
      <span className="break-all">{contact}</span>
      {typeof value.description === "string" && value.description && (
        <span className="text-xs text-muted-foreground">{value.description}</span>
      )}
    </a>
  );
};

const StructuredList = ({ values, depth }: { values: unknown[]; depth: number }) => {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? values : values.slice(0, 8);

  if (values.every((item) => typeof item !== "object" || item === null)) {
    return (
      <div className="flex flex-wrap gap-2">
        {values.map((item, index) => (
          <span key={index} className="rounded-full bg-muted px-3 py-1 text-xs text-foreground">
            {String(item)}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {visible.map((item, index) => (
        <div key={index} className="rounded-xl border border-border/60 bg-card/40 p-3 sm:p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Запись {index + 1}
          </div>
          <StructuredValue value={item} depth={depth + 1} />
        </div>
      ))}
      {values.length > 8 && (
        <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((current) => !current)}>
          {expanded ? "Свернуть список" : `Показать все записи (${values.length})`}
        </Button>
      )}
    </div>
  );
};

const StructuredObject = ({ value, depth }: { value: JsonObject; depth: number }) => {
  if (looksLikeAddress(value)) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-border/50 bg-background/50 p-3 text-sm">
        <MapPin className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
        <span>{formatAddress(value)}</span>
      </div>
    );
  }
  if ("value" in value && "type" in value && Object.keys(value).every((key) => ["value", "type", "description"].includes(key))) {
    return <ContactValue value={value} />;
  }

  const entries = Object.entries(value).filter(([, item]) => !isEmpty(item));
  const scalars = entries.filter(([, item]) => ["string", "number", "boolean"].includes(typeof item));
  const nested = entries.filter(([, item]) => !["string", "number", "boolean"].includes(typeof item));

  return (
    <div className="space-y-3">
      {scalars.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {scalars.map(([key, item]) => (
            <ScalarField key={key} fieldKey={key} value={item as string | number | boolean} />
          ))}
        </div>
      )}
      {nested.map(([key, item]) => (
        <div key={key} className={depth > 2 ? "space-y-2" : "rounded-xl border border-border/50 bg-background/30 p-3 sm:p-4"}>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
            {key.toLowerCase().includes("address") && <MapPin className="h-4 w-4 text-primary" />}
            {key.toLowerCase().includes("organization") && <Building2 className="h-4 w-4 text-primary" />}
            {key.toLowerCase().includes("manager") && <UserRound className="h-4 w-4 text-primary" />}
            {key.toLowerCase().includes("document") && <FileText className="h-4 w-4 text-primary" />}
            {labelFor(key)}
            {Array.isArray(item) && <span className="text-xs font-normal text-muted-foreground">({item.length})</span>}
          </div>
          <StructuredValue value={item} depth={depth + 1} />
        </div>
      ))}
    </div>
  );
};

const StructuredValue = ({ value, depth = 0 }: { value: unknown; depth?: number }) => {
  if (isEmpty(value)) return <div className="text-sm text-muted-foreground">Нет данных</div>;
  if (Array.isArray(value)) return <StructuredList values={value} depth={depth} />;
  if (isObject(value)) return <StructuredObject value={value} depth={depth} />;
  if (["string", "number", "boolean"].includes(typeof value)) {
    return <div className="text-sm">{renderPrimitive(value as string | number | boolean, "value")}</div>;
  }
  return null;
};

const JudgementView = ({ value }: { value: unknown }) => {
  if (!Array.isArray(value)) return <StructuredValue value={value} />;
  const groups = value.filter(isObject);
  const groupsWithItems = groups.filter((group) => Array.isArray(group.judgments) && group.judgments.length > 0);
  if (!groupsWithItems.length) return <div className="text-sm text-muted-foreground">Судебные решения не найдены</div>;

  return (
    <div className="space-y-4">
      {groupsWithItems.map((group, groupIndex) => {
        const judgments = group.judgments as unknown[];
        return (
          <div key={groupIndex} className="space-y-3">
            <div className="flex items-center gap-2 font-semibold">
              <Gavel className="h-4 w-4 text-orange-500" />
              {String(group.groupName || "Судебные решения")}
              <span className="text-xs font-normal text-muted-foreground">({judgments.length})</span>
            </div>
            {judgments.map((judgment, index) => {
              if (!isObject(judgment)) return <StructuredValue key={index} value={judgment} />;
              const directory = isObject(judgment.directory) ? judgment.directory : {};
              const judge = isObject(judgment.judge) ? judgment.judge : {};
              const court = isObject(judgment.court) ? judgment.court : {};
              const title = directory.value || judgment.type || `Решение ${index + 1}`;
              const details = Object.fromEntries(
                Object.entries(judgment).filter(([key]) => !["directory", "judge", "court", "date", "info", "documents"].includes(key))
              );
              return (
                <div key={index} className="rounded-xl border border-orange-500/20 bg-orange-500/[0.03] p-4 space-y-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="font-semibold leading-relaxed">{String(title)}</div>
                    {typeof judgment.date === "string" && (
                      <span className="flex items-center gap-1 whitespace-nowrap text-xs text-muted-foreground">
                        <CalendarDays className="h-3.5 w-3.5" /> {formatDate(judgment.date)}
                      </span>
                    )}
                  </div>
                  {(judge.fullName || court.name) && (
                    <div className="grid gap-2 text-sm sm:grid-cols-2">
                      {court.name && <div><span className="text-muted-foreground">Суд:</span> {String(court.name)}</div>}
                      {judge.fullName && <div><span className="text-muted-foreground">Судья:</span> {String(judge.fullName)}</div>}
                    </div>
                  )}
                  {typeof judgment.info === "string" && stripHtml(judgment.info) && (
                    <div className="rounded-lg bg-background/60 p-3 text-sm leading-relaxed whitespace-pre-wrap">
                      {stripHtml(judgment.info)}
                    </div>
                  )}
                  <StructuredValue value={details} />
                  {Array.isArray(judgment.documents) && judgment.documents.length > 0 && (
                    <div>
                      <div className="mb-2 text-xs font-medium text-muted-foreground">Приложенные документы</div>
                      <StructuredList values={judgment.documents} depth={1} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

const DatasetView = ({ dataset }: { dataset: BankrotCaseDataset }) => {
  const count = getBankrotPayloadCount(dataset.payload);
  return (
    <details className="group rounded-xl border border-border/60 bg-background/50">
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4">
        <div className={`rounded-lg p-2 ${dataset.fetch_error ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>
          {dataset.fetch_error ? <AlertTriangle className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-medium text-foreground">{datasetLabels[dataset.dataset_type] || labelFor(dataset.dataset_type)}</div>
          <div className="text-xs text-muted-foreground">
            {dataset.fetch_error ? "Ошибка получения" : count ? `${count} ${count === 1 ? "запись" : count < 5 ? "записи" : "записей"}` : "Нет записей"}
          </div>
        </div>
        <span className="text-xs text-muted-foreground transition-transform group-open:rotate-180">▼</span>
      </summary>
      <div className="border-t border-border/60 p-4">
        {dataset.fetch_error && <p className="mb-3 text-sm text-destructive">{dataset.fetch_error}</p>}
        {dataset.payload != null ? <StructuredValue value={dataset.payload} /> : <div className="text-sm text-muted-foreground">Данные отсутствуют</div>}
      </div>
    </details>
  );
};

export const BankrotDataView = ({
  detailData,
  listData,
  judgementsGroup,
  datasets,
}: {
  detailData: unknown;
  listData: unknown;
  judgementsGroup: unknown;
  datasets: BankrotCaseDataset[];
}) => {
  const mergedCase = mergeObjects(listData, detailData);
  const caseDetails = isObject(mergedCase)
    ? Object.fromEntries(Object.entries(mergedCase).filter(([key]) => !rootCaseFields.has(key)))
    : mergedCase;
  const visibleDatasets = datasets.filter((dataset) => dataset.fetch_error || getBankrotPayloadCount(dataset.payload) > 0);

  return (
    <div className="space-y-4">
      {!isEmpty(caseDetails) && (
        <details className="rounded-xl border border-border/60 bg-background/40" open>
          <summary className="cursor-pointer p-4 text-sm font-semibold">Сведения по делу</summary>
          <div className="border-t border-border/60 p-4">
            <StructuredValue value={caseDetails} />
          </div>
        </details>
      )}

      {!isEmpty(judgementsGroup) && (
        <details className="rounded-xl border border-border/60 bg-background/40">
          <summary className="cursor-pointer p-4 text-sm font-semibold">Судебные решения</summary>
          <div className="border-t border-border/60 p-4">
            <JudgementView value={judgementsGroup} />
          </div>
        </details>
      )}

      {visibleDatasets.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-semibold">Дополнительные разделы реестра</div>
          {visibleDatasets.map((dataset) => <DatasetView key={dataset.dataset_type} dataset={dataset} />)}
        </div>
      )}
    </div>
  );
};
