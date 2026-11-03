/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CompanyEventTimeline } from "./CompanyEventTimeline";
import type { CompanyProfile } from "@/lib/api";

afterEach(cleanup);

const profile = {
  unp: 300293950,
  names: [{ full_name_ru: "ООО «ЮНИОПТ»", valid_from: "2020-01-01" }],
  addresses: [],
  ved: [],
  contacts: [],
  events: [{
    event_record_id: 12,
    event_type: "Изменение наименования",
    event_date: "2026-10-11",
    document_number: "42",
    decision_authority: "Мингорисполком",
  }],
  trade_registry_records: [{ registration_number: "MART-1", inclusion_date: "2026-09-01", object_name: "Интернет-магазин" }],
  license_records: [],
  bankrot_cases: [],
  gias_contracts: [],
  belltpp_own_certificates: [],
  eaeu_sez_resident_records: [],
} as CompanyProfile;

describe("CompanyEventTimeline", () => {
  it("orders actual dates and keeps events without a date at the end", () => {
    const { container } = render(<MemoryRouter><CompanyEventTimeline profile={{
      ...profile,
      events: [{ event_record_id: 13, event_type: "Событие без даты", document_date: "2026-10-30" }],
      license_records: [{ license_id: 5, last_seen_at: "2026-10-31" }],
      eaeu_sez_resident_records: [{ item_id: 1, registry_entry_date: "2.10.2026" }],
    }} /></MemoryRouter>);
    const text = container.textContent ?? "";
    expect(text.indexOf("02.10.2026")).toBeLessThan(text.indexOf("01.09.2026"));
    expect(text.indexOf("01.09.2026")).toBeLessThan(text.indexOf("Событие без даты"));
    expect(screen.getAllByText("Дата события не указана")).toHaveLength(2);
    expect(screen.queryByText("30.10.2026")).toBeNull();
    expect(screen.queryByText("31.10.2026")).toBeNull();
  });

  it("shows dated EGR events and source labels", () => {
    render(<MemoryRouter><CompanyEventTimeline profile={profile} /></MemoryRouter>);
    expect(screen.getByTestId("company-event-timeline")).toBeTruthy();
    expect(screen.getAllByText("Изменение наименования").length).toBeGreaterThan(0);
    expect(screen.getByText("Документ №42 Мингорисполком")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Все события" }).getAttribute("href")).toBe("/company/300293950/events");
    expect(screen.getAllByText("ЕГР").length).toBeGreaterThan(0);
    expect(screen.getByText("Запись в торговом реестре")).toBeTruthy();
    expect(screen.getByText("МАРТ")).toBeTruthy();
  });
});
