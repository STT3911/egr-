export const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "";

export type CompanyLookupResult = {
  unp: number;
  name: string;
  status?: string;
  address?: string;
};

export type CompanyProfile = {
  unp: string;
  name: string;
  status?: string;
  status_code?: string;
  address?: string;
  registration_date?: string;
  last_update?: string;
  oked?: string;
  oked_name?: string;
  opf?: string;
  opf_name?: string;
  region?: string;
  district?: string;
  city?: string;
  inspectorate?: string;
  kfv?: string;
  kfv_name?: string;
  kfsp?: string;
  kfsp_name?: string;
  medium?: string;
  medium_name?: string;
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

const request = async <T>(path: string) => {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as ApiError;
    const message = data.detail || data.message || "Request failed";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
};

export type CompanyLookupResponse = {
  query: string;
  count: number;
  results: CompanyLookupResult[];
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
