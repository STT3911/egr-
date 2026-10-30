import { describe, expect, it } from "vitest";
import { contactHref, contactSourceLabel, getCompanyContacts, type DisplayContact } from "./companyContacts";

describe("company contacts from all sources", () => {
  it("shows Dubrava's distinct EGR and MART emails without silently correcting either", () => {
    const rows = getCompanyContacts({
      contacts: [{ phone: "212 57-44-06", email: "dubravaga@gmail.ru" }],
      contacts_aggregated: [
        { contact_type: "phone", value: "212574406", sources: ["egr"] },
        { contact_type: "email", value: "dubravaga@gmail.ru", sources: ["egr"] },
        { contact_type: "email", value: "dubravacompany@gmail.ru", sources: ["mart"] },
        { contact_type: "email", value: "dubravacompany@gmail.com", sources: ["mart"] },
      ],
    });
    expect(rows).toHaveLength(4);
    expect(rows[0]).toMatchObject({ value: "212 57-44-06", sources: ["egr"] });
    expect(rows.find(r => r.value === "dubravacompany@gmail.com")?.sources).toEqual(["mart"]);
    expect(rows.find(r => r.value === "dubravaga@gmail.ru")?.sources).toEqual(["egr"]);
  });

  it("merges duplicate observations and keeps every source and contact-person metadata", () => {
    const rows = getCompanyContacts({ contacts: [{ email: "Office@Example.by" }], contacts_aggregated: [
      { contact_type: "email", value: "office@example.by", sources: ["pvt", "egr"] },
      { contact_type: "email", value: "OFFICE@example.by", sources: ["gias", "mart", "manual"], full_name: "Иван", position: "Отдел продаж" },
    ] });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ value: "Office@Example.by", sources: ["egr", "mart", "gias", "pvt", "manual"], fullName: "Иван", position: "Отдел продаж" });
  });

  it("works without EGR contacts and without aggregates in older API responses", () => {
    expect(getCompanyContacts({ contacts: [], contacts_aggregated: [
      { contact_type: "phone", value: "+375 29 123-45-67", sources: ["mart"] },
    ] })[0].sources).toEqual(["mart"]);
    expect(getCompanyContacts({ contacts: [{ phone: "1234567", fax: "7654321", website: "example.by" }] })
      .map(r => r.kind)).toEqual(["phone", "fax", "website"]);
  });

  it("does not reintroduce expired EGR contacts from the daily aggregate", () => {
    const rows = getCompanyContacts({ contacts: [], contacts_aggregated: [
      { contact_type: "phone", value: "1234567", sources: ["egr"] },
      { contact_type: "email", value: "old@example.by", sources: ["egr", "mart"] },
    ] });
    expect(rows).toHaveLength(1);
    expect(rows[0].sources).toEqual(["mart"]);
  });

  it("does not lose a fresh EGR contact while the aggregate is stale", () => {
    const rows = getCompanyContacts({ contacts: [{ phone: "7654321" }], contacts_aggregated: [
      { contact_type: "phone", value: "1234567", sources: ["egr"] },
    ] });
    expect(rows.map(r => r.value)).toEqual(["7654321"]);
  });

  it("preserves fax labels and splits explicitly separated EGR contacts", () => {
    const rows = getCompanyContacts({ contacts: [{ phone: "1234567; 2234567", fax: "7654321" }], contacts_aggregated: [
      { contact_type: "phone", value: "1234567", sources: ["egr"] },
      { contact_type: "phone", value: "7654321", sources: ["egr"] },
    ] });
    expect(rows.map(r => r.kind)).toEqual(["phone", "phone", "fax"]);
  });

  it("matches the server's 80 phone notation but does not invent missing country codes", () => {
    const rows = getCompanyContacts({ contacts: [{ phone: "80 (29) 123-45-67" }], contacts_aggregated: [
      { contact_type: "phone", value: "+375291234567", sources: ["mart"] },
      { contact_type: "phone", value: "291234567", sources: ["gias"] },
    ] });
    expect(rows).toHaveLength(2);
    expect(rows[0].sources).toEqual(["gias"]);
    expect(rows[1].sources).toEqual(["egr", "mart"]);
  });

  it("handles blank contacts, unknown sources and future contact types without fabricating EGR provenance", () => {
    const rows = getCompanyContacts({ contacts: [], contacts_aggregated: [
      { contact_type: "phone", value: "  ", sources: ["mart"] },
      { contact_type: "telegram", value: "@example", sources: ["new_registry"] },
      { contact_type: "other", value: "Отдел продаж", sources: [] },
    ] });
    expect(rows).toHaveLength(2);
    expect(rows.every(r => r.kind === "other")).toBe(true);
    expect(contactSourceLabel("new_registry")).toBe("Другой источник: new_registry");
    expect(getCompanyContacts({ contacts: [] })).toEqual([]);
  });
});

describe("contact link safety", () => {
  const row = (kind: DisplayContact["kind"], value: string): DisplayContact => ({ key: value, kind, value, sources: [] });
  it("supports safe phone, email and website links", () => {
    expect(contactHref(row("phone", "212 57-44-06"))).toBe("tel:212574406");
    expect(contactHref(row("email", "office@example.by"))).toBe("mailto:office%40example.by");
    expect(contactHref(row("website", "example.by"))).toBe("https://example.by/");
    expect(contactHref(row("website", "http://example.by/path"))).toBe("http://example.by/path");
  });
  it.each(["javascript:alert(1)", "data:text/html,test", "ftp://example.by", "https://user:pass@example.by", "https://example.by\n"]) (
    "does not activate an unsafe website: %s", value => expect(contactHref(row("website", value))).toBeUndefined(),
  );
  it("does not create links from notes or malformed emails", () => {
    expect(contactHref(row("other", "javascript:alert(1)"))).toBeUndefined();
    expect(contactHref(row("email", "a@example.by?bcc=evil@example.by"))).toBeUndefined();
    expect(contactHref(row("phone", "справочная"))).toBeUndefined();
  });
});
