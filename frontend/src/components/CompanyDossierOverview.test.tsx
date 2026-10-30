/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CompanyDossierOverview } from "./CompanyDossierOverview";
import type { CompanyProfile } from "@/lib/api";

const profile = {
  unp: 300293950,
  current_status_name: "Действующий",
  registration_date: "2000-06-26",
  contacts: [{ phone: "212 57-44-06" }],
  contacts_aggregated: [{ contact_type: "phone", value: "212574406", sources: ["egr"] }],
  license_records: [{ license_id: 1, activity_is_active: true }],
  trade_registry_records: [{ registration_number: "1" }],
  inspection_plan_records: [],
  belltpp_own_certificates: [{ cert_number: "CERT-1" }],
  gias_contracts: [{ contract_id: "gias-1", role: "provider" }],
  leadership_observations: [],
  names: [], addresses: [], ved: [],
} as CompanyProfile;

describe("CompanyDossierOverview", () => {
  it("prioritizes non-court signals and explicitly excludes the court block", () => {
    render(<CompanyDossierOverview profile={profile} risk={null} taxDebt={{ unp: 300293950, count: 0, current_count: 0, items: [] }} />);
    expect(screen.getByText("Экспресс-сводка досье")).toBeTruthy();
    expect(screen.getByText("Критичных сигналов нет")).toBeTruthy();
    expect(screen.getByText("Сертификаты БелТПП")).toBeTruthy();
    expect(screen.getByText(/Ключевые сигналы по доступным источникам/).textContent).toContain("Судебный блок намеренно не включён");
    expect(screen.queryByText(/Судебная история/)).toBeNull();
  });

  it("surfaces tax and risk attention without inventing a court signal", () => {
    render(<CompanyDossierOverview
      profile={{ ...profile, bankrot_cases: [{ case_id: 7 }] }}
      risk={{ score: 72, level: "high", factors: [{ code: "x", title: "Риск-фактор", severity: "high", weight: 10 }], categories: [], trust_signals: [], coverage: { score: 50, checked_sources: 1, total_sources: 2 } } as never}
      taxDebt={{ unp: 300293950, count: 2, current_count: 1, items: [] }}
    />);
    expect(screen.getByText("Требует внимания")).toBeTruthy();
    expect(screen.getByText(/текущая задолженность/)).toBeTruthy();
    expect(screen.getByText(/банкрот/)).toBeTruthy();
    expect(screen.getByText("Риск-фактор")).toBeTruthy();
  });
});
