export const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "";

export type CompanyLookupResult = {
  unp: number;
  name: string;
  full_name_ru?: string;
  short_name_ru?: string;
  full_name_by?: string;
  matched_name?: string;
  matched_historical_name?: boolean;
  status?: string;
  address?: string;
  matched_type?: "phone" | "email" | "address";
  matched_value?: string;
};

export type CompanyGiasContract = {
  contract_id: string;
  role: "customer" | "provider";
  counterparty_unp?: number | null;
  counterparty_name?: string | null;
  registration_number?: string | null;
  contract_number?: string | null;
  title?: string | null;
  state?: string | null;
  price?: number | string | null;
  currency_code?: string | null;
  contract_date?: string | null;
  source_updated_at?: string | null;
  detail_status?: "pending" | "fetched" | "error" | string;
};

export type CompanyGiasBankAccount = {
  contract_id: string;
  account_number?: string | null;
  bank_code?: string | null;
  bank_name?: string | null;
  currency_code?: string | null;
  currency_name?: string | null;
  source_updated_at?: string | null;
};

export type CompanyProfile = {
  unp: number;
  current_status_code?: number;
  current_status_name?: string;
  registration_date?: string;
  liquidation_date?: string;
  current_name_ru?: string;
  current_short_name_ru?: string;
  current_name_by?: string;
  place_location_address?: string;
  // Координаты места нахождения (геокодинг адреса через OSM, хранятся в БД).
  latitude?: number;
  longitude?: number;
  names: {
    full_name_ru?: string;
    short_name_ru?: string;
    full_name_by?: string;
    valid_from?: string;
    valid_to?: string;
  }[];
  addresses: {
    full_address?: string;
    postal_code?: number;
    region?: string;
    district?: string;
    valid_from?: string;
    valid_to?: string;
  }[];
  ved: {
    ved_code?: string;
    ved_name?: string;
    valid_from?: string;
    valid_to?: string;
  }[];
  contacts: {
    email?: string;
    website?: string;
    phone?: string;
    fax?: string;
  }[];
  pvt_resident?: {
    name?: string;
    profile_url?: string;
    description?: string;
    source_url?: string;
    city?: string;
    legal_address?: string;
    phone?: string;
    website?: string;
    activity_directions?: string[];
    list_description?: string;
    last_seen_at?: string;
  } | null;
  bankrot_cases?: {
    case_id: number;
    number?: string;
    start_date?: string;
    end_date?: string;
    status?: number;
    procedure_type?: number;
    court?: string;
    judge?: string;
    manager_name?: string;
    updated_at?: string;
  }[];
  trade_registry_records?: {
    registration_number?: string;
    legal_name?: string;
    legal_address?: string;
    object_type?: string;
    object_name?: string;
    internet_shop_domain?: string;
    trade_network_name?: string;
    object_region?: string;
    object_district?: string;
    object_locality?: string;
    object_street?: string;
    object_building?: string;
    object_office?: string;
    object_contacts?: string;
    format_type?: string;
    location_type?: string;
    assortment_type?: string;
    trade_object_type?: string;
    trade_area?: string;
    retail_trade?: string;
    wholesale_trade?: string;
    goods_groups?: string;
    inclusion_date?: string;
    source_date?: string;
    source_file?: string;
    last_seen_at?: string;
  }[];
  eaeu_sez_resident_records?: {
    item_id: number;
    country?: string;
    full_name?: string;
    short_name?: string;
    legal_address?: string;
    firm_name?: string;
    registration_agency?: string;
    sez_name?: string;
    project_name?: string;
    registry_entry_date?: string;
    certificate?: string;
    source_url?: string;
    last_seen_at?: string;
  }[];
  license_records?: {
    license_id: number;
    generated_number?: string;
    holder_name?: string;
    activity_type_name?: string;
    activity_date_start?: string;
    activity_date_end?: string;
    activity_is_active?: boolean;
    last_seen_at?: string;
  }[];
  inspection_plan_records?: {
    plan_period: string;
    plan_year?: number;
    plan_half?: number;
    source_region?: string;
    plan_title?: string;
    plan_item_no?: number;
    approving_authority?: string;
    controller_unp?: number;
    controller_authority?: string;
    executor_phone?: string;
    start_month?: string;
    start_month_no?: number;
    source_file?: string;
    last_seen_at?: string;
  }[];
  belltpp_own_certificates?: {
    holder_name?: string;
    cert_number: string;
    blank_number?: string;
    issue_date?: string;
    valid_until?: string;
    verify_url?: string;
    products?: {
      row_no?: number;
      name?: string;
      code?: string;
    }[];
    last_seen_at?: string;
  }[];
  leadership_observations?: {
    person_name: string;
    position: string;
    organization_name: string;
    event_date?: string;
    exam_type?: string;
    source_name: string;
    source_title?: string;
    source_url: string;
    match_method?: string;
    match_confidence?: number;
  }[];
  gias_contracts?: CompanyGiasContract[];
  gias_bank_accounts?: CompanyGiasBankAccount[];
};

export type GiasContractPosition = {
  id: string;
  public_number?: string | null;
  title?: string | null;
  lot_number?: number | null;
  lot_title?: string | null;
  okpb_code?: string | null;
  okpb_name?: string | null;
  volume?: number | string | null;
  unit_code?: string | null;
  unit_name?: string | null;
  unit_symbol?: string | null;
  position_type?: string | null;
  unit_price?: number | string | null;
  position_price?: number | string | null;
  countries?: string[] | null;
  country_names?: string[] | null;
  is_smp?: boolean | null;
};

export type GiasContractAccount = {
  id: number;
  company_id?: string | null;
  company_unp?: number | null;
  account_number?: string | null;
  bank_code?: string | null;
  bank_name?: string | null;
  currency_code?: string | null;
  currency_name?: string | null;
  source_created_at?: string | null;
  source_updated_at?: string | null;
};

export type GiasContractDetail = {
  contract_id: string;
  base_contract_id?: string | null;
  chain_uuid?: string | null;
  customer_company_id?: string | null;
  provider_company_id?: string | null;
  customer_unp?: number | null;
  provider_unp?: number | null;
  customer_name?: string | null;
  customer_location?: string | null;
  provider_name?: string | null;
  provider_address?: string | null;
  provider_country_name?: string | null;
  state?: string | null;
  state_asfr?: string | null;
  title?: string | null;
  price?: number | string | null;
  currency_code?: string | null;
  plan_number?: string | null;
  contract_number?: string | null;
  registration_number?: string | null;
  contract_type?: string | null;
  ets_id?: string | null;
  contract_date?: string | null;
  execution_term?: string | null;
  real_execution_term?: string | null;
  termination_execution_term?: string | null;
  termination_reason?: string | null;
  has_smp?: boolean | null;
  source_created_at?: string | null;
  source_updated_at?: string | null;
  detail_status: "pending" | "fetched" | "error" | string;
  detail_fetched_at?: string | null;
  detail_last_error?: string | null;
  positions: GiasContractPosition[];
  accounts: GiasContractAccount[];
  raw_detail?: Record<string, unknown> | null;
};

export type BankrotCaseDataset = {
  dataset_type: string;
  endpoint: string;
  http_method: string;
  payload: unknown;
  fetch_error?: string | null;
  fetched_at?: string | null;
  updated_at?: string | null;
};

export type BankrotCaseDetail = NonNullable<CompanyProfile["bankrot_cases"]>[number] & {
  debtor_unp?: number | null;
  manager_id?: number | null;
  last_judgment_id?: number | null;
  list_data?: Record<string, unknown> | null;
  detail_data?: Record<string, unknown> | null;
  judgements_group?: unknown;
  fetch_error?: string | null;
  datasets: BankrotCaseDataset[];
};

export type CompanyBankrotResponse = {
  unp: number;
  cases: BankrotCaseDetail[];
};

export type ReferenceItem = {
  code: string | number;
  name: string;
  extra?: Record<string, string | number | null>;
};

type ApiError = {
  detail?: string;
  message?: string;
};

const toQuery = (params: Record<string, string | number | boolean | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      search.append(key, String(value));
    }
  });
  return search.toString();
};

const request = async <T>(path: string, init?: RequestInit) => {
  const headers = new Headers(init?.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as ApiError;
    const message = data.detail || data.message || "Request failed";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
};

const adminRequest = async <T>(path: string, init?: RequestInit) => {
  return request<T>(path, {
    ...init,
    credentials: "include",
  });
};

export type GrpTaxpayerData = {
  unp: number;
  full_name?: string;
  short_name?: string;
  registration_date?: string;
  inspectorate_code?: string;
  inspectorate_name?: string;
  status_code?: string;
  status_date?: string;
  address?: string;
  fetched_at?: string;
  updated_at?: string;
  http_status?: number;
  last_error?: string;
  raw?: Record<string, unknown>;
};

export type CompanyTaxDebtItem = {
  debtor_unp: number;
  imns_code: string;
  imns_name?: string;
  debt_date: string;
  repayment_date: string;
  slice_date: string;
};

export type CompanyTaxDebtResponse = {
  unp: number;
  count: number;
  returned_count?: number;
  current_count?: number;
  has_current_debt?: boolean;
  latest_slice_date?: string;
  latest_global_slice_date?: string;
  items: CompanyTaxDebtItem[];
};

export type CompanyLookupResponse = {
  query: string;
  count: number;
  results: CompanyLookupResult[];
};

export type AdminCompanyItem = {
  unp: number;
  name?: string;
  short_name?: string;
  address?: string;
  status?: string;
  registration_date?: string;
};

export type AdminCompaniesResponse = {
  total: number;
  limit: number;
  offset: number;
  items: AdminCompanyItem[];
};

export type AdminSession = {
  username: string;
};

export type TradeRegistryImportStats = {
  rows?: number;
  valid?: number;
  invalid?: number;
  matched?: number;
  missing_unp_in_db?: number;
  egr_checked?: number;
  egr_saved?: number;
  egr_not_found?: number;
  egr_errors?: number;
  duplicate_registry_keys?: number;
  deleted_old_records?: number;
  written?: number;
  encoding?: string | null;
  source_date?: string | null;
};

export type TradeRegistryImportRun = {
  id: string;
  status: "queued" | "running" | "success" | "failed" | string;
  original_filename: string;
  source_date?: string | null;
  stats: TradeRegistryImportStats;
  error?: string | null;
  celery_task_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
};

export type TradeRegistryImportsResponse = {
  items: TradeRegistryImportRun[];
};

export type AdminDataSourceStatus = {
  key: string;
  name: string;
  updated_at?: string | null;
  source_date?: string | null;
  status: string;
  records_count: number;
  details: Record<string, string | number | null>;
  error?: string | null;
};

export type AdminDataSourcesResponse = {
  updated_at: string;
  items: AdminDataSourceStatus[];
};

export const lookupCompanies = async (query: string) => {
  const qs = toQuery({ q: query });
  return request<CompanyLookupResponse>(`/api/v1/companies/lookup?${qs}`);
};

export const getCompanyProfile = async (unp: string) => {
  return request<CompanyProfile>(`/api/v1/companies/${encodeURIComponent(unp)}`);
};

export const getGiasContract = async (contractId: string) => {
  return request<GiasContractDetail>(
    `/api/v1/gias/contracts/${encodeURIComponent(contractId)}`
  );
};

export const getCompanyBankruptcy = async (unp: string) => {
  return request<CompanyBankrotResponse>(
    `/api/v1/companies/${encodeURIComponent(unp)}/bankruptcy`
  );
};

export const getRawCompanyData = async (unp: string) => {
  return request<Record<string, unknown>>(
    `/api/v1/companies/${encodeURIComponent(unp)}/raw`
  );
};

export const compareCompanyApis = async (unp: string) => {
  return request<Record<string, unknown>>(
    `/api/v1/companies/${encodeURIComponent(unp)}/compare`
  );
};

export const getGrpTaxpayerData = async (unp: string) => {
  return request<GrpTaxpayerData>(
    `/api/v1/grp/${encodeURIComponent(unp)}`
  );
};

export type CompanyGeocode = {
  unp: number;
  latitude: number | null;
  longitude: number | null;
  cached: boolean;
  address: string | null;
};

// Ленивый геокодинг: сервер геокодит адрес через OSM, кэширует в БД и возвращает
// координаты. Используется, когда в профиле координат ещё нет.
export const geocodeCompany = async (unp: string) => {
  return request<CompanyGeocode>(
    `/api/v1/companies/${encodeURIComponent(unp)}/geocode`
  );
};

export const getCompanyTaxDebt = async (unp: string, limit = 100) => {
  const qs = toQuery({ limit });
  return request<CompanyTaxDebtResponse>(
    `/api/v1/companies/${encodeURIComponent(unp)}/tax-debt?${qs}`
  );
};

export type CompanyRelatedByContact = {
  unp: number;
  name: string | null;
  matched_type: "phone" | "email";
  matched_value: string;
};

export type CompanyRelatedByAddress = {
  unp: number;
  name: string | null;
  address: string | null;
};

export type CompanyRelatedResponse = {
  unp: number;
  by_contact: CompanyRelatedByContact[];
  by_address: CompanyRelatedByAddress[];
};

// Связанные компании: по общему телефону/email и по тому же текущему адресу
// (здание, без учёта квартиры/офиса). Публичный эндпоинт, та же чувствительность
// данных, что и у самой карточки компании.
export const getCompanyRelated = async (unp: string) => {
  return request<CompanyRelatedResponse>(
    `/api/v1/companies/${encodeURIComponent(unp)}/related`
  );
};

export type CompanyRiskFactor = {
  code: string;
  title: string;
  weight: number;
  detail: string;
  category?: "legal" | "fiscal" | "compliance" | "behavioral" | "trust";
  severity?: "critical" | "high" | "medium" | "low" | "positive";
  source?: string;
  observed_at?: string | null;
};

export type CompanyRiskCategory = {
  code: "legal" | "fiscal" | "compliance" | "behavioral";
  title: string;
  score: number;
  raw_score: number;
  cap: number;
  level: "high" | "medium" | "low";
  factor_count: number;
};

export type CompanyRiskSource = {
  code: string;
  title: string;
  weight: number;
  earned_weight?: number;
  available: boolean;
  fresh?: boolean;
  status?: "fresh" | "stale" | "missing";
  checked_at: string | null;
};

export type CompanyRiskCoverage = {
  score: number;
  level: "high" | "medium" | "low";
  checked_sources: number;
  total_sources: number;
  sources: CompanyRiskSource[];
  missing_sources: string[];
  stale_sources?: string[];
};

export type CompanyRisk = {
  unp: number;
  score: number;
  level: "high" | "medium" | "low";
  decision?: "stop" | "manual_review" | "review" | "incomplete" | "clear";
  decision_label?: string;
  summary?: string;
  critical_flags?: string[];
  categories?: CompanyRiskCategory[];
  factors: CompanyRiskFactor[];
  trust_signals: CompanyRiskFactor[];
  coverage?: CompanyRiskCoverage;
  scope?: {
    title: string;
    assessed: string[];
    not_assessed: string[];
    note: string;
  };
  computed_at: string;
};

// Риск-профиль контрагента: оценка 0–100 с объяснимыми факторами. Публичный
// эндпоинт (та же чувствительность, что у карточки компании).
export const getCompanyRisk = async (unp: string) => {
  return request<CompanyRisk>(
    `/api/v1/companies/${encodeURIComponent(unp)}/risk`
  );
};

export const syncGrpTaxpayerData = async (onlyMissing = true, limit = 5000) => {
  const qs = toQuery({ only_missing: onlyMissing ? 1 : 0, limit });
  return request<{ queued: boolean; task_id: string; limit: number; only_missing: boolean }>(
    `/api/v1/grp/sync?${qs}`,
    { method: "POST" }
  );
};

export const listReferenceTypes = async () => {
  return request<string[]>(`/api/v1/references`);
};

export const getReferenceData = async (type: string) => {
  return request<ReferenceItem[]>(
    `/api/v1/references/${encodeURIComponent(type)}`
  );
};

export const getReferenceItem = async (type: string, code: string | number) => {
  return request<ReferenceItem>(
    `/api/v1/references/${encodeURIComponent(type)}/${encodeURIComponent(
      String(code)
    )}`
  );
};

export const searchReference = async (type: string, query: string) => {
  const qs = toQuery({ query });
  return request<ReferenceItem[]>(
    `/api/v1/references/${encodeURIComponent(type)}/search?${qs}`
  );
};

export const adminLogin = async (username: string, password: string) => {
  return adminRequest<AdminSession>("/api/v1/admin/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
};

export const adminLogout = async () => {
  return adminRequest<{ ok: boolean }>("/api/v1/admin/logout", {
    method: "POST",
  });
};

export const getAdminSession = async () => {
  return adminRequest<AdminSession>("/api/v1/admin/me");
};

export const listAdminDataSources = async () => {
  return adminRequest<AdminDataSourcesResponse>("/api/v1/admin/data-sources");
};

export const getAdminCompanies = async (query = "", offset = 0, limit = 25) => {
  const qs = toQuery({ q: query, offset, limit });
  return adminRequest<AdminCompaniesResponse>(`/api/v1/admin/companies?${qs}`);
};

const getFilenameFromDisposition = (disposition: string | null) => {
  if (!disposition) {
    return "company-fill-result.xlsx";
  }

  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/"/g, ""));
  }

  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] || "company-fill-result.xlsx";
};

export const fillCompanyFile = async (file: File) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/admin/fill-company-file`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(data.detail || data.message || "File processing failed");
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("spreadsheetml.sheet")) {
    const message = await response.text().catch(() => "");
    throw new Error(message || "Server did not return an Excel file");
  }

  return {
    blob: await response.blob(),
    filename: getFilenameFromDisposition(response.headers.get("Content-Disposition")),
  };
};

export type CompanyRelationNode = {
  unp: number;
  name: string | null;
  depth: number;
  relation_count: number;
};

export type CompanyRelationEdge = {
  source_unp: number;
  target_unp: number;
  type: "phone" | "email" | "address";
  value: string | null;
};

export type CompanyRelationGraph = {
  root_unp: number;
  depth: number;
  nodes: CompanyRelationNode[];
  edges: CompanyRelationEdge[];
  stats: {
    companies: number;
    connections: number;
    phones: number;
    emails: number;
    addresses: number;
  };
  truncated: boolean;
};

export const getCompanyRelationGraph = async (unp: string) => {
  return request<CompanyRelationGraph>(
    `/api/v1/companies/${encodeURIComponent(unp)}/relations/graph?depth=2&max_nodes=40`
  );
};

export const downloadCompanyReport = async (unp: string) => {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/companies/${encodeURIComponent(unp)}/report.xlsx`,
    { headers: { Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" } }
  );
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(data.detail || data.message || "Не удалось сформировать отчёт");
  }
  return {
    blob: await response.blob(),
    filename: getFilenameFromDisposition(response.headers.get("Content-Disposition")),
  };
};

export const createTradeRegistryImport = async (file: File) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/admin/trade-registry/imports`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(data.detail || data.message || "Trade registry import failed");
  }

  return response.json() as Promise<TradeRegistryImportRun>;
};

export const listTradeRegistryImports = async (limit = 10) => {
  const qs = toQuery({ limit });
  return adminRequest<TradeRegistryImportsResponse>(`/api/v1/admin/trade-registry/imports?${qs}`);
};

export const getTradeRegistryImport = async (id: string) => {
  return adminRequest<TradeRegistryImportRun>(`/api/v1/admin/trade-registry/imports/${encodeURIComponent(id)}`);
};

// ---------------------------------------------------------------------------
// Auth (пользователи-подписчики) + подписки на события компаний
// ---------------------------------------------------------------------------
export type AuthUser = {
  id: string;
  email: string | null;
  telegram_id: number | null;
};

export type TelegramLinkResponse = {
  linked: boolean;
  telegram_id: number | null;
  expires_in: number | null;
  command: string | null;
  bot_url: string | null;
};

export type SubscriptionItem = {
  id: string;
  unp: number;
  event_types: string[];
  source: string;
  created_at?: string | null;
};

export type SubscriptionEventItem = {
  id: number;
  unp: number;
  company_name?: string | null;
  event_type: string;
  old_value?: string | null;
  new_value?: string | null;
  occurred_at?: string | null;
  read_at?: string | null;
  processed_at?: string | null;
};

export type SubscriptionEventsResponse = {
  count: number;
  total_count: number;
  unread_count: number;
  next_before_id?: number | null;
  items: SubscriptionEventItem[];
};

// Человекочитаемые названия типов событий (совпадают с бэкендом)
export const EVENT_TYPE_LABELS: Record<string, string> = {
  status_changed: "Смена статуса",
  liquidation_started: "Ликвидация / реорганизация",
  bankruptcy: "Банкротство",
  locked_supplier: "Недобросовестный поставщик",
  tax_debt: "Налоговая задолженность",
  name_changed: "Смена наименования",
  address_changed: "Смена юр. адреса",
  director_changed: "Смена руководителя / учредителей",
  license_changed: "Лицензия (выдача / отзыв)",
  ved_changed: "Изменение видов деятельности (ВЭД)",
  registry_appearance: "Появление в реестрах (МАРТ/ПВТ/ЕАЭС)",
  new_registration: "Новая регистрация",
};

export const registerUser = async (email: string, password: string) =>
  adminRequest<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const loginUser = async (email: string, password: string) =>
  adminRequest<AuthUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const logoutUser = async () =>
  adminRequest<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" });

export const getCurrentUser = async () =>
  adminRequest<AuthUser>("/api/v1/auth/me");

export const createTelegramLink = async () =>
  adminRequest<TelegramLinkResponse>("/api/v1/auth/telegram-link", {
    method: "POST",
  });

export const disconnectTelegram = async () =>
  adminRequest<{ ok: boolean; linked: boolean }>("/api/v1/auth/telegram-link", {
    method: "DELETE",
  });

export const listSubscriptions = async () =>
  adminRequest<{ items: SubscriptionItem[] }>("/api/v1/subscriptions/");

export const createSubscription = async (unp: number, eventTypes: string[]) =>
  adminRequest<SubscriptionItem>("/api/v1/subscriptions/", {
    method: "POST",
    body: JSON.stringify({ unp, event_types: eventTypes }),
  });

export const deleteSubscription = async (id: string) =>
  adminRequest<{ ok: boolean }>(`/api/v1/subscriptions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const getSubscriptionEventTypes = async () =>
  request<{ event_types: string[] }>("/api/v1/subscriptions/event-types");

export const listSubscriptionEvents = async ({
  limit = 100,
  includeRead = true,
  newestFirst = true,
  beforeId,
  eventType,
  unp,
}: {
  limit?: number;
  includeRead?: boolean;
  newestFirst?: boolean;
  beforeId?: number;
  eventType?: string;
  unp?: number;
} = {}) => {
  const qs = toQuery({
    limit,
    include_read: includeRead,
    newest_first: newestFirst,
    before_id: beforeId,
    event_type: eventType,
    unp,
  });
  return adminRequest<SubscriptionEventsResponse>(`/api/v1/subscriptions/events?${qs}`);
};

export const acknowledgeSubscriptionEvents = async ({
  ids = [],
  upToId,
  all = false,
}: {
  ids?: number[];
  upToId?: number;
  all?: boolean;
}) =>
  adminRequest<{ acknowledged: number }>("/api/v1/subscriptions/events/ack", {
    method: "POST",
    body: JSON.stringify({ ids, up_to_id: upToId, all }),
  });
