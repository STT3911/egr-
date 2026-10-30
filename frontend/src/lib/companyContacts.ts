import type { CompanyProfile } from "./api";

export type ContactKind = "phone" | "fax" | "email" | "website" | "other";
export type DisplayContact = {
  key: string;
  kind: ContactKind;
  value: string;
  sources: string[];
  fullName?: string;
  position?: string;
};

export type ContactProfile = Pick<CompanyProfile, "contacts" | "contacts_aggregated">;

export const CONTACT_GROUPS: { kind: ContactKind; title: string }[] = [
  { kind: "phone", title: "Телефоны" },
  { kind: "fax", title: "Факсы" },
  { kind: "email", title: "Электронная почта" },
  { kind: "website", title: "Сайты" },
  { kind: "other", title: "Другие контакты" },
];

export function contactSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    egr: "ЕГР", mart: "МАРТ", gias: "ГИАС", pvt: "ПВТ", manual: "Вручную",
  };
  return labels[source] ?? `Другой источник: ${source}`;
}

function websiteUrl(value: string): URL | null {
  if (/\s/.test(value) || [...value].some(char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)) return null;
  // Never turn source-controlled javascript:/data: strings into clickable links.
  if (/^[a-z][a-z\d+.-]*:/i.test(value) && !/^https?:\/\//i.test(value)) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`);
    return ["http:", "https:"].includes(url.protocol) && url.hostname && !url.username && !url.password
      ? url : null;
  } catch {
    return null;
  }
}

function normalized(kind: ContactKind, value: string): string {
  if (kind === "phone" || kind === "fax") {
    const digits = value.replace(/\D/g, "");
    // Match the existing server parser's Belarusian 80<code> notation.
    return (digits.startsWith("80") && digits.length >= 11 ? `375${digits.slice(2)}` : digits)
      || value.toLowerCase();
  }
  if (kind === "website") return websiteUrl(value)?.href.replace(/\/$/, "") ?? value;
  return value.toLowerCase();
}

export function contactHref(contact: DisplayContact): string | undefined {
  if (contact.kind === "website") return websiteUrl(contact.value)?.href;
  if (contact.kind === "email" && /^[^\s@?<>:#]+@[^\s@?<>:#]+\.[^\s@?<>:#]+$/.test(contact.value)) {
    return `mailto:${encodeURIComponent(contact.value)}`;
  }
  if (contact.kind === "phone") {
    const phone = normalized("phone", contact.value);
    if (/^\d{6,13}$/.test(phone)) {
      return `tel:${contact.value.startsWith("+") || phone.startsWith("375") ? "+" : ""}${phone}`;
    }
  }
  return undefined;
}

export function getCompanyContacts(profile: ContactProfile): DisplayContact[] {
  const rows = new Map<string, DisplayContact>();
  const keyFor = (kind: ContactKind, value: string) => `${kind}:${normalized(kind, value)}`;
  const add = (kind: ContactKind, value: string, sources: string[], fullName?: string | null, position?: string | null) => {
    value = value.trim();
    if (!value) return;
    const key = keyFor(kind, value);
    const existing = rows.get(key);
    const row: DisplayContact = existing ?? { key, kind, value, sources: [] };
    row.sources = [...new Set([...row.sources, ...sources.map(s => s.trim()).filter(Boolean)])];
    row.fullName ||= fullName?.trim() || undefined;
    row.position ||= position?.trim() || undefined;
    rows.set(key, row);
  };

  // These are the API's current EGR periods. Retain the original readable values
  // and the fallback for old/uncached profiles whose daily aggregate is not ready.
  for (const contact of profile.contacts ?? []) {
    for (const kind of ["phone", "fax", "email", "website"] as const) {
      const raw = contact[kind];
      if (!raw?.trim()) continue;
      const values = kind === "website" ? [raw] : raw.split(/[;,\n]+/);
      for (const value of values) add(kind, value, ["egr"]);
    }
  }
  const currentEgrKeys = new Set(rows.keys());

  for (const contact of profile.contacts_aggregated ?? []) {
    if (!contact.value?.trim()) continue;
    let kind = CONTACT_GROUPS.some(g => g.kind === contact.contact_type)
      ? contact.contact_type as ContactKind : "other" as const;
    // The collector puts EGR fax numbers in its phone column. Preserve the
    // explicit fax label when it is not also a current EGR phone number.
    if (kind === "phone" && contact.sources.length === 1 && contact.sources[0] === "egr"
      && !currentEgrKeys.has(keyFor("phone", contact.value))
      && currentEgrKeys.has(keyFor("fax", contact.value))) kind = "fax";
    const key = keyFor(kind, contact.value.trim());
    // A daily aggregate can lag behind current EGR periods. Do not reintroduce
    // expired EGR-only contacts; an observation by another source stays visible.
    const sources = contact.sources.filter(source => source !== "egr" || currentEgrKeys.has(key));
    if (contact.sources.length && !sources.length) continue;
    add(kind, contact.value, sources, contact.full_name, contact.position);
  }

  const sourceOrder = ["egr", "mart", "gias", "pvt", "manual"];
  for (const row of rows.values()) row.sources.sort((a, b) => {
    const rank = (s: string) => sourceOrder.includes(s) ? sourceOrder.indexOf(s) : sourceOrder.length;
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  return [...rows.values()].sort((a, b) =>
    CONTACT_GROUPS.findIndex(g => g.kind === a.kind) - CONTACT_GROUPS.findIndex(g => g.kind === b.kind)
    || a.value.localeCompare(b.value, "ru"));
}
