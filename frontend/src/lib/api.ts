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

const toQuery = (params: Record<string, string | number | undefined>) => {
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
  latest_slice_date?: string;
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

export const lookupCompanies = async (query: string) => {
  const qs = toQuery({ q: query });
  return request<CompanyLookupResponse>(`/api/v1/companies/lookup?${qs}`);
};

export const getCompanyProfile = async (unp: string) => {
  return request<CompanyProfile>(`/api/v1/companies/${encodeURIComponent(unp)}`);
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

export const getGrpTaxpayerData = async (unp: string, forceRefresh = false) => {
  const qs = forceRefresh ? "?force_refresh=true" : "";
  return request<GrpTaxpayerData>(
    `/api/v1/grp/${encodeURIComponent(unp)}${qs}`
  );
};

export const getCompanyTaxDebt = async (unp: string, limit = 100) => {
  const qs = toQuery({ limit });
  return request<CompanyTaxDebtResponse>(
    `/api/v1/companies/${encodeURIComponent(unp)}/tax-debt?${qs}`
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
